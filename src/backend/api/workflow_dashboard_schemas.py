from datetime import datetime

from pydantic import BaseModel, Field


class WorkflowDashboardCounts(BaseModel):
    draft: int = Field(ge=0, description="Plans in DRAFT.")
    pending_ai: int = Field(ge=0, description="Pending plans in AI_PENDING or AI_PROCESSING.")
    human_review: int = Field(ge=0, description="Pending plans routed to human review.")
    approved: int = Field(ge=0, description="Plans in APPROVED.")
    rejected: int = Field(ge=0, description="Plans in REJECTED.")


class WorkflowDashboardResponse(BaseModel):
    as_of: datetime
    principal_scope: str
    counts: WorkflowDashboardCounts
    active_assignments: int = Field(ge=0)
