"""Integration tests with a real Redis broker and result backend.

These tests use testcontainers to start a Redis instance, configure Celery
to use it as both broker and result backend, and run tasks through a real
worker — the closest we can get to a production setup.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.tasks.base import TaskResultStatus

from django_tasks_celery.backend import CeleryBackend
from django_tasks_celery.register import _django_task_registry, ensure_celery_task
from tests.tasks import async_task, context_task, failing_task, simple_task

pytestmark = pytest.mark.redis


@pytest.fixture(scope="session")
def redis_url():
    """Start a Redis container and return its URL."""
    from testcontainers.redis import RedisContainer

    with RedisContainer() as redis:
        yield f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0"


@pytest.fixture(scope="session")
def celery_config(redis_url):
    return {
        "broker_url": redis_url,
        "result_backend": redis_url,
        "task_always_eager": False,
        "task_eager_propagates": False,
        "result_extended": True,
    }


@pytest.fixture(scope="session")
def celery_worker_parameters():
    return {
        "perform_ping_check": False,
    }


@pytest.fixture
def backend():
    return CeleryBackend(
        alias="default",
        params={"QUEUES": ["default", "high", "low"]},
    )


@pytest.fixture(autouse=True)
def _patch_app_and_register(backend, celery_app):
    """Wire up the test celery_app and register tasks."""
    _django_task_registry.clear()
    for task in [simple_task, failing_task, async_task, context_task]:
        ensure_celery_task(task, celery_app, backend)
    with patch.object(backend, "_get_celery_app", return_value=celery_app):
        yield
    _django_task_registry.clear()


class TestRedisEnqueue:
    def test_enqueue_and_get_result(self, backend, celery_app, celery_worker):
        """Full round-trip: enqueue → Redis broker → worker → Redis result backend."""
        result = backend.enqueue(simple_task, args=(3, 7), kwargs={})
        assert result.status == TaskResultStatus.READY

        celery_result = celery_app.AsyncResult(result.id)
        return_value = celery_result.get(timeout=10)
        assert return_value == 10

        task_result = backend.get_result(result.id)
        assert task_result.status == TaskResultStatus.SUCCESSFUL
        assert task_result.return_value == 10

    def test_kwargs(self, backend, celery_app, celery_worker):
        result = backend.enqueue(simple_task, args=(), kwargs={"x": 5, "y": 3})
        assert celery_app.AsyncResult(result.id).get(timeout=10) == 8

    def test_failing_task(self, backend, celery_app, celery_worker):
        result = backend.enqueue(failing_task, args=(), kwargs={})

        with pytest.raises(ValueError, match="Something went wrong"):
            celery_app.AsyncResult(result.id).get(timeout=10)

        task_result = backend.get_result(result.id)
        assert task_result.status == TaskResultStatus.FAILED
        assert len(task_result.errors) == 1

    def test_async_task(self, backend, celery_app, celery_worker):
        result = backend.enqueue(async_task, args=(21,), kwargs={})
        assert celery_app.AsyncResult(result.id).get(timeout=10) == 42

    def test_context_task(self, backend, celery_app, celery_worker):
        result = backend.enqueue(context_task, args=(99,), kwargs={})
        return_value = celery_app.AsyncResult(result.id).get(timeout=10)
        assert return_value["item_id"] == 99
        assert return_value["attempt"] == 1


class TestRedisGetResult:
    def test_result_metadata(self, backend, celery_app, celery_worker):
        """Redis result backend should populate all metadata fields."""
        result = backend.enqueue(simple_task, args=(10, 20), kwargs={})
        celery_app.AsyncResult(result.id).get(timeout=10)

        task_result = backend.get_result(result.id)
        assert task_result.status == TaskResultStatus.SUCCESSFUL
        assert task_result.return_value == 30
        assert task_result.args == [10, 20]
        assert task_result.kwargs == {}
        assert task_result.finished_at is not None
        assert task_result.task is simple_task
        assert len(task_result.worker_ids) == 1
