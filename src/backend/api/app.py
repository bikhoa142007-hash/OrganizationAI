"""Minimal demo-only HTTP transport. No policy decision logic in routes."""
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, Depends, File, Form, Header, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from starlette.exceptions import HTTPException

from src.ai_pipeline.adapters import ApprovalPipelineAdapter
from src.ai_pipeline.orchestrator import EvaluationOrchestrator
from src.ai_pipeline.providers.mock import MockVLMProvider
from src.backend.application.workflow import ApplicationError
from src.backend.demo import PRINCIPALS, ENGINE, configuration, CHECKER
from .dependencies import Settings, open_workflow
from .errors import error_response
from .schemas import Draft, Submission, Mutation, HumanDecisionRequest, PlanResponse, HistoryResponse, ErrorResponse, SubmissionResponse, EvaluationResponse, VerifyResponse, DTO


def create_app(settings=None):
    settings = settings or Settings.from_environment()
    settings.validate()
    verify_runs = {}
    app = FastAPI(title='OrganizationAI demo API', version='1.0',
                  description='Synthetic demo authentication only. Production requests fail closed.',
                  responses={code: {'model': ErrorResponse} for code in (401, 403, 404, 409, 422, 503)})
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False,
                       allow_methods=['GET', 'POST', 'PUT'],
                       allow_headers=['Content-Type', 'X-Demo-Actor', 'Idempotency-Key', 'X-Correlation-ID'])

    @app.middleware('http')
    async def request_context(request, call_next):
        request.state.correlation_id = 'http-' + uuid4().hex
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
        return error_response('VALIDATION_ERROR', 'Invalid request fields: ' + fields, request.state.correlation_id)

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
        allowed = {'title', 'objective', 'summary', 'department', 'checker_id', 'start_date', 'end_date',
                   'budget_minor_units', 'currency', 'target_audience', 'channels', 'kpi_expected', 'notes'}
        if not set(body.payload) <= allowed:
            raise ApplicationError('VALIDATION_ERROR', 'Unknown or server-owned payload field.', meta['correlation_id'])
        checker = body.payload.get('checker_id')
        if checker and (checker != CHECKER or 'CHECKER' not in PRINCIPALS.get(checker, ())):
            raise ApplicationError('FORBIDDEN', 'Checker is outside the configured demo assignment.', meta['correlation_id'])
        return service.save_draft(auth, plan_id, body.payload, expected_revision=body.expected_revision, **meta)

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
        if suite not in ('general', 'escalation'):
            raise ApplicationError('VALIDATION_ERROR', 'Unknown Verify suite.', meta['correlation_id'])
        scope = (auth, meta['idempotency_key'])
        if scope in verify_runs:
            if verify_runs[scope]['suite'] != suite:
                raise ApplicationError('CONFLICT', 'Verify intent reused for another suite.', meta['correlation_id'])
            return verify_runs[scope]
        from src.verify.runner import run_suite
        result = {'run_id': meta['idempotency_key'], 'suite': suite, 'rows': run_suite('verify' if suite == 'general' else 'ground-truth')}
        verify_runs[scope] = result
        return result

    return app


app = create_app()
