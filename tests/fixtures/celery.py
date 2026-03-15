"""Celery app fixtures for testing."""

from __future__ import annotations

import pytest
from celery import Celery


@pytest.fixture
def celery_app() -> Celery:
    """Create a Celery app configured for eager (synchronous) execution."""
    app = Celery("test")
    app.config_from_object(
        {
            "broker_url": "memory://",
            "result_backend": "cache+memory://",
            "task_always_eager": True,
            "task_eager_propagates": True,
            "result_extended": True,
        },
    )
    app.finalize()
    return app
