"""Task registration: bridge Django @task functions into Celery's task registry."""

from __future__ import annotations

import inspect
import logging
import threading
import traceback
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from asgiref.sync import async_to_sync
from celery import _state, current_task
from django.tasks.base import Task, TaskContext, TaskError, TaskResult, TaskResultStatus
from django.tasks.signals import task_finished, task_started

if TYPE_CHECKING:
    from django_tasks_celery.backend import CeleryBackend

logger = logging.getLogger(__name__)

_django_task_registry: dict[str, Task[..., Any]] = {}
_registry_lock = threading.Lock()


def ensure_celery_task(task: Task[..., Any], celery_app: Any, backend: CeleryBackend) -> None:
    """Register a Django @task as a Celery task if not already registered."""
    celery_name = task.module_path
    with _registry_lock:
        if celery_name in _django_task_registry:
            return
        _django_task_registry[celery_name] = task
        run_fn = _make_run_fn(task, backend)
        _register_on_app(celery_name, run_fn, celery_app)
        _register_on_future_apps(celery_name, run_fn)


def _register_on_app(celery_name: str, run_fn: Any, app: Any) -> None:
    """Register task on a specific Celery app."""
    if celery_name in app.tasks:
        return
    if app.finalized:
        with app._finalize_mutex:
            if celery_name not in app.tasks:
                app._task_from_fun(run_fn, name=celery_name, serializer="json")
    else:
        app._task_from_fun(run_fn, name=celery_name, serializer="json")


def _register_on_future_apps(celery_name: str, run_fn: Any) -> None:
    """Register task on any future Celery apps via connect_on_app_finalize."""

    def _register(app: Any) -> None:
        if celery_name in app.tasks:
            return
        app._task_from_fun(run_fn, name=celery_name, serializer="json")

    _state.connect_on_app_finalize(_register)


def _make_run_fn(task: Task[..., Any], backend: CeleryBackend) -> Any:
    """Create a wrapper function that bridges Celery execution to Django task signals."""

    def run(*args: Any, **kwargs: Any) -> Any:
        result_id = current_task.request.id if current_task else "unknown"
        worker_hostname = current_task.request.hostname if current_task else None
        worker_ids = [worker_hostname] if worker_hostname else []
        now = datetime.now(UTC)

        task_result = TaskResult(
            task=task,
            id=result_id,
            status=TaskResultStatus.RUNNING,
            enqueued_at=None,
            started_at=now,
            finished_at=None,
            last_attempted_at=now,
            args=list(args),
            kwargs=dict(kwargs),
            backend=backend.alias,
            errors=[],
            worker_ids=worker_ids,
        )

        task_started.send(sender=type(backend), task_result=task_result)

        try:
            call_args: tuple[Any, ...] = args
            if task.takes_context:
                context = TaskContext(task_result=task_result)
                call_args = (context, *args)

            fn = task.func
            if inspect.iscoroutinefunction(fn):
                return_value = async_to_sync(fn)(*call_args, **kwargs)
            else:
                return_value = fn(*call_args, **kwargs)

            task_result = replace(
                task_result,
                status=TaskResultStatus.SUCCESSFUL,
                finished_at=datetime.now(UTC),
            )
            object.__setattr__(task_result, "_return_value", return_value)
            task_finished.send(sender=type(backend), task_result=task_result)
            return return_value

        except Exception as exc:
            tb = traceback.format_exc()
            error = TaskError(
                exception_class_path=f"{type(exc).__module__}.{type(exc).__qualname__}",
                traceback=tb,
            )
            task_result = replace(
                task_result,
                status=TaskResultStatus.FAILED,
                finished_at=datetime.now(UTC),
                errors=[error],
            )
            task_finished.send(sender=type(backend), task_result=task_result)
            raise

    run.__name__ = task.func.__name__
    run.__qualname__ = task.func.__qualname__
    return run
