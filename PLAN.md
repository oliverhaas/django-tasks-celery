# django-tasks-celery Implementation Plan

## Overview

Celery backend for Django 6.0's `django.tasks` framework. Implements `BaseTaskBackend` so that `@task` / `enqueue()` dispatches to Celery workers. Standalone package — works with vanilla Celery 5.4+, does not require celery-asyncio.

Based on:
- **celery-asyncio's `CeleryBackend`** — the most complete implementation, targets Django 6.0 API. Primary reference for task registration, signal handling, result retrieval, and async support.
- **matiasb's PR #64** — simpler prototype, useful for `enqueue_on_commit` pattern and priority mapping.
- **django-tasks-rq** — reference for project structure, packaging, system checks, and compat layer.
- **django-cachex** — tooling, CI, pre-commit, linting configuration.

---

## Project Structure

```
django-tasks-celery/
├── django_tasks_celery/
│   ├── __init__.py              # Version, exports CeleryBackend
│   ├── backend.py               # CeleryBackend(BaseTaskBackend) — core implementation
│   ├── register.py              # Task registration logic (connect_on_app_finalize)
│   ├── results.py               # Celery result → Django TaskResult mapping
│   ├── compat.py                # Handle both django.tasks (6.0+) and django-tasks (backport)
│   └── py.typed                 # PEP 561 marker
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Pytest config, Celery app fixture, Django settings
│   ├── test_backend.py          # CeleryBackend enqueue/get_result/validate tests
│   ├── test_register.py         # Task registration tests
│   ├── test_results.py          # State mapping, TaskResult construction tests
│   ├── test_signals.py          # task_enqueued/started/finished signal tests
│   ├── test_priority.py         # Priority mapping tests
│   ├── test_checks.py           # System check tests
│   ├── tasks.py                 # Sample task definitions for tests
│   ├── fixtures/
│   │   ├── celery.py            # Celery app fixtures (eager mode for unit tests)
│   │   ├── containers.py        # Testcontainers (Redis) for integration tests
│   │   └── settings.py          # Django settings fixtures
│   └── settings/
│       ├── base.py              # Base Django test settings
│       └── urls.py              # Empty URL config
│
├── docs/
│   ├── index.md
│   ├── getting-started/
│   │   ├── installation.md
│   │   └── quickstart.md
│   ├── user-guide/
│   │   └── configuration.md
│   └── reference/
│       ├── api.md
│       └── changelog.md
│
├── .github/workflows/
│   ├── ci.yml                   # Lint + test matrix (Python × Django × Celery)
│   ├── publish.yml              # PyPI publishing
│   └── tag.yml                  # Release tagging
│
├── pyproject.toml
├── .pre-commit-config.yaml
├── mkdocs.yml
├── .gitignore
├── .python-version              # 3.14
├── LICENSE                      # MIT
└── README.md
```

This is a small, focused package — the core is `backend.py` (~200 lines), `register.py` (~60 lines), and `results.py` (~80 lines).

---

## Architecture

### Task Registration

When `validate_task()` is called (first enqueue of a task), register the Django `@task` function as a Celery task. Follow celery-asyncio's approach:

```python
# register.py
from celery import _state

_django_task_registry: dict[str, object] = {}

def ensure_celery_task(task, celery_app, backend):
    """Register a Django @task as a Celery task if not already registered."""
    celery_name = task.module_path  # e.g. "myapp.tasks.send_email"
    if celery_name in _django_task_registry:
        return
    _django_task_registry[celery_name] = task
    run_fn = make_run_fn(task, backend)
    register_shared(celery_name, run_fn)

def register_shared(celery_name, run_fn):
    """Register task with all current and future Celery apps."""
    def _register(app):
        if celery_name in app.tasks:
            return
        app._task_from_fun(run_fn, name=celery_name, serializer="json")
    _state.connect_on_app_finalize(_register)
    for app in _state._get_active_apps():
        if app.finalized:
            with app._finalize_mutex:
                _register(app)
```

The `make_run_fn()` creates a wrapper that:
- Fires `task_started` signal
- Passes `TaskContext` if `takes_context=True`
- Handles sync and async task functions
- Fires `task_finished` signal on success or failure
- Records `TaskError` on exceptions

### Enqueue

```python
def enqueue(self, task, args, kwargs):
    self.validate_task(task)
    app = self._get_celery_app()
    options = self._build_send_options(task)
    celery_result = app.send_task(task.module_path, args=list(args), kwargs=dict(kwargs), **options)
    task_result = self._build_initial_result(task, celery_result.id, args, kwargs)
    task_enqueued.send(sender=type(self), task_result=task_result)
    return task_result
```

Uses `send_task()` (not `apply_async`) — more decoupled, doesn't require the task to be locally registered on the enqueue side.

### Result Retrieval

```python
def get_result(self, result_id):
    meta = self._get_celery_app().backend.get_task_meta(result_id)
    return meta_to_task_result(result_id, meta)
```

State mapping (Celery → Django):

| Celery State | Django TaskResultStatus |
|---|---|
| PENDING | READY |
| RECEIVED | READY |
| STARTED | RUNNING |
| SUCCESS | SUCCESSFUL |
| FAILURE | FAILED |
| REVOKED | FAILED |
| REJECTED | FAILED |
| RETRY | READY |
| IGNORED | FAILED |

### Priority Mapping

Django priority range: -100 to 100
Celery/AMQP priority range: 0 to 255

```python
def map_priority(django_priority: int | None) -> int:
    if django_priority is None:
        return 127  # middle
    return max(0, min(255, round((django_priority + 100) * 255 / 200)))
```

### Celery App Resolution

Configurable via `OPTIONS.celery_app` (import path), falls back to `get_current_app()`:

```python
TASKS = {
    "default": {
        "BACKEND": "django_tasks_celery.CeleryBackend",
        "QUEUES": ["default", "high", "low"],
        "OPTIONS": {
            "celery_app": "myproject.celery.app",  # optional, auto-detected if omitted
        },
    },
}
```

### System Checks

Following django-tasks-rq's pattern:
- Check that `celery` is importable
- Check that Celery app can be resolved
- Warn if result backend is disabled and `get_result` would fail

### Compat Layer

Support both Django 6.0 built-in `django.tasks` and the standalone `django-tasks` backport package (for Django 5.2 users):

```python
# compat.py
try:
    from django.tasks.backends.base import BaseTaskBackend
    from django.tasks.base import Task, TaskContext, TaskError, TaskResult, TaskResultStatus
    from django.tasks.signals import task_enqueued, task_started, task_finished
    from django.tasks.exceptions import TaskResultDoesNotExist
except ImportError:
    from django_tasks.backends.base import BaseTaskBackend
    from django_tasks.task import Task, TaskContext, TaskError, TaskResult, ResultStatus as TaskResultStatus
    from django_tasks.signals import task_enqueued, task_started, task_finished
    from django_tasks.exceptions import TaskResultDoesNotExist
```

---

## Feature Flags

| Flag | Value | Notes |
|---|---|---|
| `supports_defer` | `True` | Celery supports `eta` and `countdown` |
| `supports_async_task` | `True` | Wrapper handles both sync and async task functions |
| `supports_priority` | `True` | Mapped to Celery/AMQP priority (0-255) |
| `supports_get_result` | Dynamic property | `True` if Celery result backend is not `DisabledBackend` |

---

## Build & Tooling (matching django-cachex)

| Tool | Purpose |
|---|---|
| hatchling | Build backend |
| uv | Package manager, lockfile |
| ruff | Linter + formatter (line length 120, strict mode) |
| mypy + ty | Type checking (django-stubs) |
| pytest | Testing (pytest-django, pytest-cov) |
| testcontainers | Docker Redis for integration tests |
| pre-commit | Hooks (ruff, mypy, taplo, trailing comma) |
| mkdocs-material | Documentation |
| GitHub Actions | CI matrix, publish, docs |

### Python / Django / Celery Support

- Python: 3.12+
- Django: 5.2+ (via compat layer for django-tasks backport), 6.0+ native
- Celery: 5.4+

### Dependencies

- **Required**: Django >=5.2, celery >=5.4
- **Optional**: django-tasks (backport, for Django <6.0)

---

## Implementation Phases

### Phase 1: Core Backend

1. Project skeleton (pyproject.toml, pre-commit, CI, .gitignore, LICENSE, README)
2. `backend.py` — `CeleryBackend` with `enqueue()`, `validate_task()`, feature flags
3. `register.py` — task registration via `connect_on_app_finalize` + `_task_from_fun`
4. `make_run_fn()` — wrapper with signal handling, `takes_context`, sync/async support
5. Priority mapping
6. Celery app resolution (configurable + auto-detect)
7. Unit tests with `task_always_eager=True`

### Phase 2: Result Retrieval

1. `results.py` — Celery meta → Django `TaskResult` conversion
2. `get_result()` / `aget_result()` implementation
3. Dynamic `supports_get_result` property
4. State mapping tests
5. Integration tests with Redis result backend (testcontainers)

### Phase 3: System Checks & Compat

1. `check()` — system checks for Celery availability and configuration
2. `compat.py` — support django-tasks backport for Django 5.2
3. `aenqueue()` — native async (if Celery app supports `asend_task`, otherwise fallback to `sync_to_async`)

### Phase 4: Polish

1. Documentation (mkdocs-material)
2. Example configuration in README
3. PyPI publishing workflow
4. CI matrix (Python 3.12/3.13/3.14 × Django 5.2/6.0 × Celery 5.4/5.5)

---

## Configuration Example

```python
# settings.py

INSTALLED_APPS = [
    ...,
]

# Celery config
CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_RESULT_BACKEND = "redis://localhost:6379/1"
CELERY_RESULT_EXTENDED = True  # recommended for task name resolution in get_result

# Django Tasks config
TASKS = {
    "default": {
        "BACKEND": "django_tasks_celery.CeleryBackend",
        "QUEUES": ["default"],
        "OPTIONS": {
            # "celery_app": "myproject.celery.app",  # optional
        },
    },
}
```

```python
# myapp/tasks.py
from django.tasks import task

@task
def send_email(to, subject, body):
    # ...
    return {"sent": True}

@task(priority=5, queue_name="high")
def process_payment(order_id):
    # ...

@task(takes_context=True)
def retryable_task(context, item_id):
    print(f"Attempt {context.attempt}")
    # ...
```

```python
# myapp/views.py
from myapp.tasks import send_email

def contact_view(request):
    result = send_email.enqueue(to="user@example.com", subject="Hello", body="World")
    # result.id, result.status == TaskResultStatus.READY
```
