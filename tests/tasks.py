"""Sample task definitions for tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.tasks import task

if TYPE_CHECKING:
    from django.tasks.base import TaskContext


@task
def simple_task(x: int, y: int) -> int:
    return x + y


@task(queue_name="high", priority=10)
def high_priority_task(message: str) -> str:
    return f"processed: {message}"


@task(takes_context=True)
def context_task(context: TaskContext, item_id: int) -> dict:
    return {"item_id": item_id, "attempt": context.attempt}


@task
def failing_task() -> None:
    raise ValueError("Something went wrong")


async def _async_work(n: int) -> int:
    return n * 2


@task
async def async_task(n: int) -> int:
    return await _async_work(n)
