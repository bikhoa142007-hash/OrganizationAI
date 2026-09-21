"""Frontend application services and presentation helpers.

The module intentionally has no Streamlit import so validation and view models
remain usable in automated tests and other hosts.
"""

from .service import FrontendService, validate_plan_form

__all__ = ["FrontendService", "validate_plan_form"]
