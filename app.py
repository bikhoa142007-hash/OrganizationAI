"""Streamlit demo for the OrganizationAI Sprint 1 vertical slice."""
from pathlib import Path

from src.ai_pipeline.adapters import ApprovalPipelineAdapter
from src.ai_pipeline.orchestrator import EvaluationOrchestrator
from src.ai_pipeline.providers.mock import MockVLMProvider
from src.backend.application.workflow import ApprovalWorkflow
from src.backend.repositories.approval import ApprovalRepository
from src.frontend.service import FrontendService, audit_rows, validate_plan_form
from src.verify.harness import CHECKER, ENGINE, MAKER, VerifyHarness, demo_configuration

DB_PATH = Path(".wp5-demo.sqlite")


def build_service():
    repository = ApprovalRepository(DB_PATH)
    workflow = ApprovalWorkflow(repository, demo_configuration(),
                                {MAKER: {"MAKER"}, CHECKER: {"CHECKER"}, ENGINE: {"EVALUATOR"}},
                                evaluator_id=ENGINE)
    pipeline = ApprovalPipelineAdapter(workflow, EvaluationOrchestrator(MockVLMProvider()))
    return FrontendService(workflow, pipeline, maker_id=MAKER, checker_id=CHECKER,
                           evaluator_id=ENGINE), repository


def run_app():
    try:
        import streamlit as st
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install requirements.txt, then run: python -m streamlit run app.py") from exc
    st.set_page_config(page_title="OrganizationAI", page_icon="✅", layout="wide")
    st.title("OrganizationAI – Marketing Plan Approval")
    st.caption("Maker → AI evaluation → deterministic decision → Checker review")
    page = st.sidebar.radio("View", ("Home", "Submit Plan", "Evaluation Result", "Human Review", "Audit Log", "Verify"))
    service, repository = build_service()
    try:
        if page == "Home":
            st.write("Evaluate a marketing plan with auditable AI evidence and deterministic policy.")
            st.markdown("1. Enter and save a plan  \n2. Submit it for evaluation  \n3. Review the result or Checker escalation")
        elif page == "Submit Plan":
            with st.form("plan"):
                plan_id = st.text_input("Plan ID", value="DEMO-PLAN")
                title = st.text_input("Title")
                objective = st.text_area("Objective")
                summary = st.text_area("Summary")
                department = st.text_input("Department", value="demo-marketing")
                start_date = st.date_input("Start date")
                end_date = st.date_input("End date")
                budget = st.number_input("Budget (minor units)", min_value=0, value=10000)
                upload = st.file_uploader("Campaign image", type=["png", "jpg", "jpeg", "webp"])
                submitted = st.form_submit_button("Save, submit and evaluate")
            if submitted:
                payload = {"title": title, "maker_id": MAKER, "checker_id": CHECKER, "department": department,
                           "objective": objective, "summary": summary, "start_date": start_date.isoformat(),
                           "end_date": end_date.isoformat(), "budget_minor_units": str(budget), "currency": "VND"}
                validation = validate_plan_form(payload, 1 if upload else 0)
                if not validation["valid"]:
                    st.error("Please fix the highlighted fields.")
                    st.json(validation["errors"])
                else:
                    draft = service.save_draft(plan_id, payload)
                    uploaded = service.upload(plan_id, upload.getvalue(), upload.type or "image/png", draft["revision"])
                    result = service.submit_and_evaluate(plan_id, uploaded["revision"])
                    st.session_state["last_result"] = service.result_view(result)
                    st.success("Evaluation completed. Open Evaluation Result.")
        elif page == "Evaluation Result":
            result = st.session_state.get("last_result")
            if not result:
                st.info("Submit a plan first.")
            else:
                st.header(result["outcome"])
                st.write(result["explanation"])
                if result["escalation_category"]:
                    st.warning(result["escalation_category"])
                    for question in result["escalation_questions"]:
                        st.write(question)
                st.json({key: result[key] for key in ("confidence", "provider", "model_version", "timestamp", "plan_id", "version", "approval_round", "correlation_id")})
                st.dataframe(result["rule_checks"], use_container_width=True)
                st.json(result["evidence"])
        elif page == "Human Review":
            plan_id = st.text_input("Plan ID", value="DEMO-PLAN")
            action = st.selectbox("Checker action", ("APPROVED", "REJECTED"))
            reason = st.text_area("Reason (mandatory for rejection)")
            override_reason = st.text_area("Override reason (required when changing recommendation)")
            if st.button("Record Checker decision"):
                try:
                    history = service.history(plan_id)
                    decision = service.human_decide(plan_id, history["plan"]["current_round"], action,
                                                    reason=reason or None, override_reason=override_reason or None,
                                                    revision=history["plan"]["revision"])
                    st.success(f"Recorded {decision['action']}.")
                except Exception as exc:
                    st.error(str(exc))
        elif page == "Audit Log":
            plan_id = st.text_input("Plan ID", value="DEMO-PLAN")
            try:
                st.dataframe(audit_rows(service.history(plan_id)), use_container_width=True)
            except Exception as exc:
                st.info(f"No audit history yet: {exc}")
        elif page == "Verify":
            st.write("Five TEST_ONLY fixtures run through the actual workflow and provider adapter.")
            if st.button("Run all 5 Verify cases"):
                st.session_state["verify_rows"] = VerifyHarness().run_all()
            rows = st.session_state.get("verify_rows")
            if rows:
                st.dataframe(rows, use_container_width=True)
                st.success("All Verify cases passed.") if all(row["passed"] for row in rows) else st.error("A Verify case failed; inspect its error.")
    finally:
        repository.close()


if __name__ == "__main__":
    run_app()
