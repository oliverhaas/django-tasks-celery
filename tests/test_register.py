"""Tests for task registration logic."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from celery import Celery

from django_tasks_celery.backend import CeleryBackend
from django_tasks_celery.register import _django_task_registry, ensure_celery_task
from tests.tasks import async_task, simple_task


@pytest.fixture
def backend():
    return CeleryBackend(alias="default", params={"QUEUES": ["default", "high", "low"]})


@pytest.fixture
def celery_app():
    app = Celery("test_register")
    app.config_from_object(
        {
            "broker_url": "memory://",
            "result_backend": "cache+memory://",
            "task_always_eager": True,
            "task_eager_propagates": True,
        },
    )
    app.finalize()
    return app


@pytest.fixture(autouse=True)
def _clear_registry():
    _django_task_registry.clear()
    yield
    _django_task_registry.clear()


class TestEnsureCeleryTask:
    def test_registers_task(self, celery_app, backend):
        ensure_celery_task(simple_task, celery_app, backend)
        assert simple_task.module_path in _django_task_registry

    def test_idempotent(self, celery_app, backend):
        ensure_celery_task(simple_task, celery_app, backend)
        ensure_celery_task(simple_task, celery_app, backend)
        assert simple_task.module_path in _django_task_registry

    def test_registers_in_celery_app(self, celery_app, backend):
        ensure_celery_task(simple_task, celery_app, backend)
        assert simple_task.module_path in celery_app.tasks

    def test_registers_async_task(self, celery_app, backend):
        ensure_celery_task(async_task, celery_app, backend)
        assert async_task.module_path in celery_app.tasks

    def test_registers_on_non_finalized_app(self, backend):
        """Tasks can be registered on a non-finalized Celery app."""
        app = Celery("test_not_finalized")
        app.config_from_object(
            {
                "broker_url": "memory://",
                "result_backend": "cache+memory://",
            },
        )
        # Don't finalize yet
        ensure_celery_task(simple_task, app, backend)
        # Finalize to trigger pending registrations
        app.finalize()
        assert simple_task.module_path in app.tasks


class TestAutoRegistration:
    """Tasks should be auto-registered with Celery during validate_task (worker discovery)."""

    def test_validate_task_registers_with_celery(self, celery_app, backend):
        """validate_task() should register the task with Celery so workers discover tasks
        at import time, not only when enqueue() is called."""
        with patch.object(backend, "_get_celery_app", return_value=celery_app):
            backend.validate_task(simple_task)
        assert simple_task.module_path in celery_app.tasks

    def test_validate_task_registration_survives_celery_app_error(self, backend):
        """If the Celery app isn't available during validate_task, it should not crash."""
        with patch.object(backend, "_get_celery_app", side_effect=RuntimeError("no app")):
            # Should not raise — validation still works, registration is best-effort
            backend.validate_task(simple_task)
