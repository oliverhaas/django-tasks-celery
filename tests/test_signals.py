"""Tests for task signal dispatching."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from celery import Celery

from django_tasks_celery.backend import CeleryBackend
from django_tasks_celery.compat import TaskResultStatus, task_enqueued, task_finished, task_started
from django_tasks_celery.register import _django_task_registry
from tests.tasks import failing_task, simple_task


@pytest.fixture
def backend():
    return CeleryBackend(alias="default", params={"QUEUES": ["default", "high", "low"]})


@pytest.fixture
def celery_app():
    app = Celery("test_signals")
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


class TestSignals:
    def test_enqueue_signal(self, backend, celery_app):
        received = []

        def handler(sender, task_result, **kwargs):
            received.append(("enqueued", task_result.status))

        task_enqueued.connect(handler)
        try:
            with patch.object(backend, "_get_celery_app", return_value=celery_app):
                backend.enqueue(simple_task, args=(1, 2), kwargs={})
            assert ("enqueued", TaskResultStatus.READY) in received
        finally:
            task_enqueued.disconnect(handler)

    def test_started_and_finished_signals(self, backend, celery_app):
        received = []

        def started_handler(sender, task_result, **kwargs):
            received.append(("started", task_result.status))

        def finished_handler(sender, task_result, **kwargs):
            received.append(("finished", task_result.status))

        task_started.connect(started_handler)
        task_finished.connect(finished_handler)
        try:
            with patch.object(backend, "_get_celery_app", return_value=celery_app):
                backend.enqueue(simple_task, args=(1, 2), kwargs={})
            # In eager mode with apply_async, the task runs synchronously
            assert ("started", TaskResultStatus.RUNNING) in received
            assert ("finished", TaskResultStatus.SUCCESSFUL) in received
        finally:
            task_started.disconnect(started_handler)
            task_finished.disconnect(finished_handler)

    def test_failure_signal(self, backend, celery_app):
        received = []

        def finished_handler(sender, task_result, **kwargs):
            received.append(("finished", task_result.status, task_result.errors))

        task_finished.connect(finished_handler)
        try:
            with (
                patch.object(backend, "_get_celery_app", return_value=celery_app),
                pytest.raises(ValueError, match="Something went wrong"),
            ):
                backend.enqueue(failing_task, args=(), kwargs={})
            assert len(received) == 1
            assert received[0][0] == "finished"
            assert received[0][1] == TaskResultStatus.FAILED
            assert len(received[0][2]) == 1
        finally:
            task_finished.disconnect(finished_handler)
