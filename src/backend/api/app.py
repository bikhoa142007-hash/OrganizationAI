"""Minimal demo-only HTTP transport. No policy decision logic in routes."""
from collections import deque
from math import ceil
from threading import BoundedSemaphore, Lock
from time import monotonic
from typing import Annotated, Callable
from uuid import uuid4

from fastapi import FastAPI, Depends, File, Form, Header, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from src.ai_pipeline.adapters import ApprovalPipelineAdapter
from src.ai_pipeline.orchestrator import EvaluationOrchestrator
from src.ai_pipeline.providers.mock import MockVLMProvider
from src.ai_pipeline.task_config import configured_task_components
from src.backend.application.auth_workflow_ai import (
    create_authenticated_provider,
    unconfigured_approval_configuration,
)
from src.backend.application.workflow import ApplicationError
from src.backend.api.auth import get_auth_db
from src.backend.api.auth_rate_limit import AuthAttemptLimiter
from src.backend.demo import PRINCIPALS, ENGINE, configuration, CHECKER
from .dependencies import Settings, open_workflow
from .errors import error_response
from .schemas import Draft, Submission, Mutation, HumanDecisionRequest, PlanResponse, HistoryResponse, ErrorResponse, SubmissionResponse, EvaluationResponse, VerifyResponse, DTO
from .auth import router as auth_router
from .auth_workflow import router as auth_workflow_router
from .auth_sla import router as auth_sla_router
from .approval_configuration import router as approval_configuration_router
from .internal_notes import router as internal_notes_router
from .workflow_dashboard import router as workflow_dashboard_router
from .workflow_retry import router as workflow_retry_router
from .public_judge import router as public_judge_router


class _PublicJudgeRequestGate:
    """Process-local public Judge quota; do not trust forwarded client-IP headers."""

    def __init__(
        self,
        *,
        max_requests: int = 30,
        window_seconds: int = 60,
        max_concurrent: int = 1,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_requests < 1 or window_seconds < 1 or max_concurrent < 1:
            raise ValueError("Public Judge request limits must be positive.")
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._clock = clock
        self._attempts: deque[float] = deque()
        self._lock = Lock()
        self._active = BoundedSemaphore(max_concurrent)

    def try_acquire(self) -> int | None:
        now = self._clock()
        with self._lock:
            while self._attempts and now - self._attempts[0] >= self._window_seconds:
                self._attempts.popleft()
            if len(self._attempts) >= self._max_requests:
                return max(1, ceil(self._window_seconds - (now - self._attempts[0])))
            self._attempts.append(now)
            if not self._active.acquire(blocking=False):
                return 1
        return None

    def release(self) -> None:
        self._active.release()


def create_app(settings=None, *, auth_workflow_provider=None, auth_workflow_configuration=None,
               auth_workflow_media_provider=None, auth_workflow_strategy_provider=None):
    settings = settings or Settings.from_environment()
    settings.validate()
    auth_workflow_provider = auth_workflow_provider or create_authenticated_provider(settings.app_env)
    configured_media, configured_strategy, media_policy, strategy_rubric = configured_task_components()
    auth_workflow_media_provider = auth_workflow_media_provider or configured_media
    auth_workflow_strategy_provider = auth_workflow_strategy_provider or configured_strategy
    media_settings = getattr(auth_workflow_media_provider, "settings", None)
    strategy_settings = getattr(auth_workflow_strategy_provider, "settings", None)
    auth_workflow_configuration = auth_workflow_configuration or unconfigured_approval_configuration(
        auth_workflow_provider,
        media_policy=media_policy,
        strategy_rubric=strategy_rubric,
        media_model_snapshot=media_settings.public_snapshot() if media_settings else None,
        strategy_model_snapshot=strategy_settings.public_snapshot() if strategy_settings else None,
        visual_model_snapshot=auth_workflow_provider.get_model_metadata(),
    )
    verify_runs = {}
    app = FastAPI(title='OrganizationAI API', version='1.0',
                  description='PostgreSQL authentication and authenticated Maker-Checker workflow, plus a separate SQLite synthetic approval demo. Demo-actor routes are available only in APP_ENV=demo.',
                  responses={code: {'model': ErrorResponse} for code in (401, 403, 404, 409, 422, 429, 503)})
    app.state.allowed_origins = tuple(settings.cors_origins)
    app.state.auth_attempt_limiter = AuthAttemptLimiter()
    app.state.auth_workflow_provider = auth_workflow_provider
    app.state.auth_workflow_media_provider = auth_workflow_media_provider
    app.state.auth_workflow_strategy_provider = auth_workflow_strategy_provider
    app.state.auth_workflow_configuration = auth_workflow_configuration
    app.state.public_judge_request_gate = _PublicJudgeRequestGate()
    app.include_router(auth_router)
    app.include_router(auth_workflow_router)
    app.include_router(auth_sla_router)
    app.include_router(approval_configuration_router)
    app.include_router(workflow_dashboard_router)
    app.include_router(internal_notes_router)
    app.include_router(workflow_retry_router)
    if settings.app_env == 'demo':
        app.include_router(public_judge_router)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=True,
                       allow_methods=['GET', 'POST', 'PUT'],
                       allow_headers=['Content-Type', 'X-Demo-Actor', 'Idempotency-Key', 'X-Correlation-ID'])

    @app.middleware('http')
    async def request_context(request, call_next):
        request.state.correlation_id = 'http-' + uuid4().hex
        is_public_judge_post = (
            settings.app_env == 'demo'
            and request.method == 'POST'
            and request.url.path.startswith('/api/public/judge/')
        )
        if is_public_judge_post:
            retry_after = app.state.public_judge_request_gate.try_acquire()
            if retry_after is None:
                try:
                    response = await call_next(request)
                finally:
                    app.state.public_judge_request_gate.release()
            else:
                response = error_response(
                    'RATE_LIMITED',
                    'Public Judge is busy. Wait before starting another run.',
                    request.state.correlation_id,
                    429,
                )
                response.headers['Retry-After'] = str(retry_after)
        else:
            response = await call_next(request)
        response.headers['X-Correlation-ID'] = request.state.correlation_id
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(ApplicationError)
    async def application_error(request, exc):
        return error_response(exc.code, exc.message, request.state.correlation_id)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        fields = ', '.join('.'.join(str(x) for x in e['loc']) for e in exc.errors())
        return error_response('VALIDATION_ERROR', 'Trường không hợp lệ hoặc không được phép: ' + fields, request.state.correlation_id)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response('NOT_FOUND' if exc.status_code == 404 else 'VALIDATION_ERROR',
                              'Request could not be processed.', request.state.correlation_id, exc.status_code)

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        return error_response('UNAVAILABLE', 'Request could not be completed.', request.state.correlation_id)

    async def actor(request: Request, x_demo_actor: Annotated[str | None, Header()] = None):
        if settings.app_env != 'demo' or x_demo_actor not in PRINCIPALS or x_demo_actor == ENGINE:
            raise ApplicationError('UNAUTHENTICATED', 'Demo authentication is unavailable or actor is unknown.', request.state.correlation_id)
        return x_demo_actor

    async def workflow(auth=Depends(actor)):
        service = open_workflow(settings)
        try:
            yield service
        finally:
            service.repository.close()

    async def intent(request: Request, idempotency_key: Annotated[str, Header(min_length=1, max_length=200)]):
        return dict(idempotency_key=idempotency_key, correlation_id=request.state.correlation_id)

    @app.get('/api/health')
    async def health():
        return {'status': 'ok', 'environment': settings.app_env}

    @app.get('/api/health/ready')
    def readiness(session: Session = Depends(get_auth_db)):
        session.execute(text('SELECT 1'))
        return {'status': 'ok', 'environment': settings.app_env, 'auth_database': 'postgresql'}

    @app.get('/api/config')
    async def config(auth=Depends(actor)):
        return dict(environment=settings.app_env, actor=auth, roles=sorted(PRINCIPALS[auth]),
                    actors=[{'id': k, 'roles': sorted(v)} for k, v in PRINCIPALS.items() if k != ENGINE],
                    checker_id=CHECKER, department='DEMO-DEPT-01', currency='VND',
                    policy=configuration().to_dict(), provider='MOCK_VLM', mock_mode=settings.mock_mode,
                    capabilities={'stop': False, 'retry_evaluation': False, 'request_changes': False})

    @app.get('/api/plans', response_model=list[PlanResponse])
    async def plans(auth=Depends(actor), service=Depends(workflow), offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)):
        return service.list_plans(auth, offset=offset, limit=limit)

    @app.put('/api/plans/{plan_id}/draft', response_model=PlanResponse)
    async def draft(plan_id: str, body: Draft, auth=Depends(actor), service=Depends(workflow), meta=Depends(intent)):
        return service.save_draft(auth, plan_id, body.payload.model_dump(exclude_unset=True),
                                  expected_revision=body.expected_revision, **meta)

    @app.get('/api/reviews', response_model=list[PlanResponse])
    async def reviews(auth=Depends(actor), service=Depends(workflow), offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)):
        return service.list_reviews(auth, offset=offset, limit=limit)

    @app.get('/api/plans/{plan_id}', response_model=HistoryResponse)
    async def detail(plan_id: str, auth=Depends(actor), service=Depends(workflow)):
        return service.get_plan(auth, plan_id)

    @app.post('/api/plans/{plan_id}/attachments', response_model=PlanResponse)
    async def upload(plan_id: str, file: Annotated[UploadFile, File()], expected_revision: Annotated[int, Form(ge=0)],
                     auth=Depends(actor), service=Depends(workflow), meta=Depends(intent)):
        content = await file.read(service.configuration.policy.max_attachment_bytes + 1)
        await file.close()
        return service.upload_attachment(auth, plan_id, content, file.content_type,
                                         expected_revision=expected_revision, **meta)

    @app.get('/api/plans/{plan_id}/attachments/{attachment_id}')
    async def attachment(plan_id: str, attachment_id: str, auth=Depends(actor), service=Depends(workflow)):
        media_type, content = service.get_attachment(auth, plan_id, attachment_id)
        return Response(content, media_type=media_type, headers={'Content-Disposition': 'attachment'})

    @app.post('/api/plans/{plan_id}/submit', response_model=SubmissionResponse)
    async def submit(plan_id: str, body: Submission, auth=Depends(actor), service=Depends(workflow), meta=Depends(intent)):
        return service.submit_plan(auth, plan_id, **body.model_dump(), **meta)

    @app.post('/api/plans/{plan_id}/rounds/{number}/evaluate', response_model=EvaluationResponse)
    async def evaluate(plan_id: str, number: int, body: Mutation, auth=Depends(actor), service=Depends(workflow), meta=Depends(intent)):
        return service.run_evaluation(auth, plan_id, number, body.expected_revision,
                                      ApprovalPipelineAdapter(service, EvaluationOrchestrator(MockVLMProvider(settings.mock_mode))),
                                      **meta)

    @app.post('/api/plans/{plan_id}/rounds/{number}/decision')
    async def human_decision(plan_id: str, number: int, body: HumanDecisionRequest,
                             auth=Depends(actor), service=Depends(workflow), meta=Depends(intent)):
        return service.decide_round(auth, plan_id, number, **body.model_dump(), **meta)

    @app.get('/api/plans/{plan_id}/rounds/{number}/observation')
    async def observation(plan_id: str, number: int, auth=Depends(actor), service=Depends(workflow)):
        return service.get_verify_observation(auth, plan_id, number)

    @app.post('/api/verify/{suite}', response_model=VerifyResponse)
    async def verify(suite: str, body: DTO, auth=Depends(actor), meta=Depends(intent)):
        if suite not in ('general', 'escalation', 'regression'):
            raise ApplicationError('VALIDATION_ERROR', 'Unknown Verify suite.', meta['correlation_id'])
        scope = (auth, meta['idempotency_key'])
        if scope in verify_runs:
            if verify_runs[scope]['suite'] != suite:
                raise ApplicationError('CONFLICT', 'Verify intent reused for another suite.', meta['correlation_id'])
            return verify_runs[scope]
        from src.verify.runner import run_suite
        result = {'run_id': meta['idempotency_key'], 'suite': suite, 'rows': run_suite(suite)}
        verify_runs[scope] = result
        return result

    return app


app = create_app()
