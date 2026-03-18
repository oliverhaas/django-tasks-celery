"""Integration tests using a real Celery worker (celery_worker fixture).

These tests start an actual Celery worker in a background thread and verify
that tasks are dispatched, executed, and results are retrieved correctly —
no eager mode, no mocking.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from django_tasks_celery.backend import CeleryBackend
from django_tasks_celery.compat import TaskResultStatus
from django_tasks_celery.register import _django_task_registry, ensure_celery_task
from tests.tasks import async_task, context_task, failing_task, simple_task

# ── Celery pytest plugin configuration ──────────────────────────────────


@pytest.fixture(scope="session")
def celery_config():
    return {
        "broker_url": "memory://",
        "result_backend": "cache+memory://",
        "task_always_eager": False,
        "task_eager_propagates": False,
        "result_extended": True,
    }


@pytest.fixture(scope="session")
def celery_worker_parameters():
    return {
        "perform_ping_check": False,
    }


# ── Our fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def backend():
    return CeleryBackend(
        alias="default",
        params={"QUEUES": ["default", "high", "low"]},
    )


@pytest.fixture(autouse=True)
def _patch_app_and_clear_registry(backend, celery_app):
    """Ensure our backend resolves to the test celery_app and clear registry between tests."""
    _django_task_registry.clear()
    # Re-register tasks on this test's celery_app
    for task in [simple_task, failing_task, async_task, context_task]:
        ensure_celery_task(task, celery_app, backend)
    with patch.object(backend, "_get_celery_app", return_value=celery_app):
        yield
    _django_task_registry.clear()


# ── Tests ───────────────────────────────────────────────────────────────


class TestWorkerEnqueue:
    def test_enqueue_and_get_result(self, backend, celery_app, celery_worker):
        """Task is executed by worker and result can be retrieved."""
        result = backend.enqueue(simple_task, args=(3, 7), kwargs={})
        assert result.status == TaskResultStatus.READY
        assert result.id is not None

        # Wait for the worker to process
        celery_result = celery_app.AsyncResult(result.id)
        return_value = celery_result.get(timeout=10)
        assert return_value == 10

        # Verify get_result maps to SUCCESSFUL
        task_result = backend.get_result(result.id)
        assert task_result.status == TaskResultStatus.SUCCESSFUL

    def test_enqueue_with_kwargs(self, backend, celery_app, celery_worker):
        """Task works with keyword arguments."""
        result = backend.enqueue(simple_task, args=(), kwargs={"x": 5, "y": 3})

        celery_result = celery_app.AsyncResult(result.id)
        return_value = celery_result.get(timeout=10)
        assert return_value == 8

    def test_failing_task(self, backend, celery_app, celery_worker):
        """Failed task is reflected in get_result."""
        result = backend.enqueue(failing_task, args=(), kwargs={})

        celery_result = celery_app.AsyncResult(result.id)
        with pytest.raises(ValueError, match="Something went wrong"):
            celery_result.get(timeout=10)

        task_result = backend.get_result(result.id)
        assert task_result.status == TaskResultStatus.FAILED
        assert len(task_result.errors) == 1
        assert "ValueError" in task_result.errors[0].exception_class_path

    def test_async_task(self, backend, celery_app, celery_worker):
        """Async task functions execute correctly in the worker."""
        result = backend.enqueue(async_task, args=(21,), kwargs={})

        celery_result = celery_app.AsyncResult(result.id)
        return_value = celery_result.get(timeout=10)
        assert return_value == 42

    def test_context_task(self, backend, celery_app, celery_worker):
        """Tasks with takes_context=True receive a TaskContext."""
        result = backend.enqueue(context_task, args=(99,), kwargs={})

        celery_result = celery_app.AsyncResult(result.id)
        return_value = celery_result.get(timeout=10)
        assert return_value["item_id"] == 99


class TestWorkerSignals:
    def test_enqueued_signal_fires(self, backend, celery_app, celery_worker):
        """task_enqueued signal fires in the calling thread."""
        from django_tasks_celery.compat import task_enqueued

        received = []

        def on_enqueued(sender, task_result, **kwargs):
            received.append(task_result.status)

        task_enqueued.connect(on_enqueued)
        try:
            result = backend.enqueue(simple_task, args=(1, 2), kwargs={})
            celery_app.AsyncResult(result.id).get(timeout=10)
            assert TaskResultStatus.READY in received
        finally:
            task_enqueued.disconnect(on_enqueued)


class TestWorkerGetResult:
    def test_pending_result(self, backend, celery_worker):
        """get_result for a nonexistent ID returns READY (Celery PENDING)."""
        task_result = backend.get_result("nonexistent-task-id")
        assert task_result.status == TaskResultStatus.READY

    def test_result_has_finished_at(self, backend, celery_app, celery_worker):
        """Successful result has finished_at timestamp."""
        result = backend.enqueue(simple_task, args=(1, 1), kwargs={})
        celery_app.AsyncResult(result.id).get(timeout=10)

        task_result = backend.get_result(result.id)
        assert task_result.status == TaskResultStatus.SUCCESSFUL
        assert task_result.finished_at is not None

    def test_result_has_task_reference(self, backend, celery_app, celery_worker):
        """get_result returns TaskResult with task reference when using extended results."""
        result = backend.enqueue(simple_task, args=(2, 3), kwargs={})
        celery_app.AsyncResult(result.id).get(timeout=10)

        task_result = backend.get_result(result.id)
        assert task_result.task is simple_task

    def test_result_has_return_value(self, backend, celery_app, celery_worker):
        """get_result populates return_value from Celery result metadata."""
        result = backend.enqueue(simple_task, args=(10, 20), kwargs={})
        celery_app.AsyncResult(result.id).get(timeout=10)

        task_result = backend.get_result(result.id)
        assert task_result.status == TaskResultStatus.SUCCESSFUL
        assert task_result.return_value == 30

    def test_result_has_args_kwargs(self, backend, celery_app, celery_worker):
        """get_result should return the original args and kwargs."""
        result = backend.enqueue(simple_task, args=(5, 3), kwargs={})
        celery_app.AsyncResult(result.id).get(timeout=10)

        task_result = backend.get_result(result.id)
        assert task_result.args == [5, 3]
        assert task_result.kwargs == {}

    def test_result_has_worker_id(self, backend, celery_app, celery_worker):
        """get_result should include the worker hostname."""
        result = backend.enqueue(simple_task, args=(1, 1), kwargs={})
        celery_app.AsyncResult(result.id).get(timeout=10)

        task_result = backend.get_result(result.id)
        assert len(task_result.worker_ids) == 1
        assert isinstance(task_result.worker_ids[0], str)

    def test_context_attempt_is_one(self, backend, celery_app, celery_worker):
        """context.attempt should be 1 after first worker execution, not 0."""
        result = backend.enqueue(context_task, args=(99,), kwargs={})
        return_value = celery_app.AsyncResult(result.id).get(timeout=10)
        assert return_value["attempt"] == 1
