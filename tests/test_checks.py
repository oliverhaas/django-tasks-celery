"""Tests for system checks."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from celery import Celery
from django.core import checks

from django_tasks_celery.backend import CeleryBackend


@pytest.fixture
def backend():
    return CeleryBackend(alias="default", params={"QUEUES": ["default"]})


class TestSystemChecks:
    def test_no_errors_with_valid_config(self, backend):
        app = Celery("test_checks")
        app.config_from_object(
            {
                "broker_url": "memory://",
                "result_backend": "cache+memory://",
            },
        )
        app.finalize()
        with patch.object(backend, "_get_celery_app", return_value=app):
            messages = list(backend.check())
        errors = [m for m in messages if m.level >= checks.ERROR]
        assert len(errors) == 0

    def test_warning_when_result_backend_disabled(self, backend):
        # Create a real Celery app without a result backend
        app = Celery("test_no_result")
        app.config_from_object(
            {
                "broker_url": "memory://",
                "result_backend": "disabled://",
            },
        )
        app.finalize()
        with patch.object(backend, "_get_celery_app", return_value=app):
            messages = list(backend.check())
        warnings = [m for m in messages if m.id == "django_tasks_celery.W001"]
        assert len(warnings) == 1

    def test_error_when_celery_app_fails(self, backend):
        with patch.object(backend, "_get_celery_app", side_effect=Exception("bad config")):
            messages = list(backend.check())
        errors = [m for m in messages if m.id == "django_tasks_celery.E002"]
        assert len(errors) == 1
