"""Integration tests with a real Redis broker and result backend.

These tests use testcontainers to start a Redis instance, configure Celery
to use it as both broker and result backend in eager mode — verifying that
real Redis serialization/deserialization works correctly.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from celery import Celery
from django.tasks.base import TaskResultStatus

from django_tasks_celery.backend import CeleryBackend
from django_tasks_celery.register import _django_task_registry
from tests.tasks import async_task, context_task, failing_task, simple_task


@pytest.fixture(scope="module")
def redis_url():
    """Start a Redis container for the module and return its URL."""
    from testcontainers.redis import RedisContainer

    with RedisContainer() as redis:
        yield f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0"


@pytest.fixture(scope="module")
def redis_celery_app(redis_url):
    """Celery app using real Redis for broker and result backend."""
    app = Celery("test_redis")
    app.config_from_object(
        {
            "broker_url": redis_url,
            "result_backend": redis_url,
            "task_always_eager": True,
            "task_eager_propagates": True,
            "task_store_eager_result": True,
            "result_extended": True,
        },
    )
    app.finalize()
    return app


@pytest.fixture(autouse=True)
def _clear_registry():
    _django_task_registry.clear()
    yield
    _django_task_registry.clear()


@pytest.fixture
def backend(redis_celery_app):
    backend = CeleryBackend(alias="default", params={"QUEUES": ["default", "high", "low"]})
    with patch.object(backend, "_get_celery_app", return_value=redis_celery_app):
        yield backend


class TestRedisEnqueue:
    def test_enqueue_and_get_result(self, backend):
        """Full round-trip through real Redis: enqueue → store → retrieve."""
        result = backend.enqueue(simple_task, args=(3, 7), kwargs={})
        assert result.status == TaskResultStatus.READY

        task_result = backend.get_result(result.id)
        assert task_result.status == TaskResultStatus.SUCCESSFUL
        assert task_result.return_value == 10

    def test_kwargs(self, backend):
        result = backend.enqueue(simple_task, args=(), kwargs={"x": 5, "y": 3})
        task_result = backend.get_result(result.id)
        assert task_result.return_value == 8

    def test_failing_task(self, backend):
        with pytest.raises(ValueError, match="Something went wrong"):
            backend.enqueue(failing_task, args=(), kwargs={})

    def test_async_task(self, backend):
        result = backend.enqueue(async_task, args=(21,), kwargs={})
        task_result = backend.get_result(result.id)
        assert task_result.return_value == 42

    def test_context_task(self, backend):
        result = backend.enqueue(context_task, args=(99,), kwargs={})
        task_result = backend.get_result(result.id)
        assert task_result.status == TaskResultStatus.SUCCESSFUL


class TestRedisGetResult:
    def test_result_metadata(self, backend):
        """Redis result backend should populate all metadata fields."""
        result = backend.enqueue(simple_task, args=(10, 20), kwargs={})

        task_result = backend.get_result(result.id)
        assert task_result.status == TaskResultStatus.SUCCESSFUL
        assert task_result.return_value == 30
        assert task_result.args == [10, 20]
        assert task_result.kwargs == {}
        assert task_result.finished_at is not None
        assert task_result.task is simple_task
