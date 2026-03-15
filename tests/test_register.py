"""Tests for task registration logic."""

from __future__ import annotations

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
