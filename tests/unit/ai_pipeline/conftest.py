import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_local_vlm_env(monkeypatch):
    """Keep deployment LOCAL_VLM_* settings from leaking into unit tests."""
    for name in list(os.environ):
        if name.startswith("LOCAL_VLM_"):
            monkeypatch.delenv(name, raising=False)