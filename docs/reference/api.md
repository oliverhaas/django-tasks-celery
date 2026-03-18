# API Reference

## `CeleryBackend`

::: django_tasks_celery.CeleryBackend

The main backend class. Subclasses Django's `BaseTaskBackend`.

### Class attributes

| Attribute | Value | Description |
|-----------|-------|-------------|
| `supports_defer` | `True` | Tasks can be deferred with `run_after`. |
| `supports_async_task` | `True` | Coroutine task functions are supported. |
| `supports_priority` | `True` | Task priority is mapped to AMQP priority. |
| `supports_get_result` | Dynamic | `True` when a Celery result backend is configured. |

### Methods

#### `enqueue(task, args, kwargs) -> TaskResult`

Validates and dispatches the task to Celery via `apply_async()`. Sends the `task_enqueued` signal.

#### `get_result(result_id) -> TaskResult`

Retrieves task result from Celery's result backend. Requires `CELERY_RESULT_EXTENDED = True` for full task reference resolution.

#### `validate_task(task)`

Validates the task and registers it with Celery. This runs automatically at task import time (via `Task.__post_init__`), ensuring worker-side discovery.

#### `check(**kwargs) -> Iterable[CheckMessage]`

Runs Django system checks (E002, W001, W002).

## `map_priority(django_priority) -> int`

Maps Django priority range (-100 to 100) to Celery/AMQP priority range (0 to 255).

```python
from django_tasks_celery.backend import map_priority

map_priority(-100)  # 0 (lowest)
map_priority(0)     # 128 (default)
map_priority(100)   # 255 (highest)
```

## Signals

All Django task signals are supported:

- **`task_enqueued`** — Sent in the calling process when `enqueue()` completes.
- **`task_started`** — Sent in the worker when task execution begins. `TaskResult` includes `worker_ids`.
- **`task_finished`** — Sent in the worker when task execution completes (success or failure). `TaskResult` includes `return_value` on success.
