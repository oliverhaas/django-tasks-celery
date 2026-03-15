"""Task registration: bridge Django @task functions into Celery's task registry."""

from __future__ import annotations

import asyncio
import inspect
import traceback
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from celery import _state, current_task

from django_tasks_celery.compat import (
    Task,
    TaskContext,
    TaskError,
    TaskResult,
    TaskResultStatus,
    task_finished,
    task_started,
)

if TYPE_CHECKING:
    from django_tasks_celery.backend import CeleryBackend

_django_task_registry: dict[str, Task[..., Any]] = {}


def ensure_celery_task(task: Task[..., Any], celery_app: Any, backend: CeleryBackend) -> None:
    """Register a Django @task as a Celery task if not already registered."""
    celery_name = task.module_path
    if celery_name in _django_task_registry:
        return
    _django_task_registry[celery_name] = task
    run_fn = _make_run_fn(task, backend)
    _register_shared(celery_name, run_fn)


def _register_shared(celery_name: str, run_fn: Any) -> None:
    """Register task with all current and future Celery apps."""

    def _register(app: Any) -> None:
        if celery_name in app.tasks:
            return
        app._task_from_fun(run_fn, name=celery_name, serializer="json")

    _state.connect_on_app_finalize(_register)
    for app in _state._get_active_apps():
        if app.finalized:
            with app._finalize_mutex:
                _register(app)


def _make_run_fn(task: Task[..., Any], backend: CeleryBackend) -> Any:
    """Create a wrapper function that bridges Celery execution to Django task signals."""

    def run(*args: Any, **kwargs: Any) -> Any:
        result_id = current_task.request.id if current_task else "unknown"
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
            worker_ids=[],
        )

        task_started.send(sender=type(backend), task_result=task_result)

        try:
            call_args: tuple[Any, ...] = args
            if task.takes_context:
                context = TaskContext(task_result=task_result)
                call_args = (context, *args)

            fn = task.func
            if inspect.iscoroutinefunction(fn):
                return_value = asyncio.run(fn(*call_args, **kwargs))
            else:
                return_value = fn(*call_args, **kwargs)

            task_result = replace(
                task_result,
                status=TaskResultStatus.SUCCESSFUL,
                finished_at=datetime.now(UTC),
            )
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
