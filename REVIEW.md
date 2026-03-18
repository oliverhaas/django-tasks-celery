# django-tasks-celery — Thorough Review

## Critical Bugs

### 1. Worker-side task discovery is completely broken

**Severity: CRITICAL — package does not work in production**

`ensure_celery_task()` is only called during `enqueue()` in the Django web process.
The Celery worker is a *separate process* — it never calls `ensure_celery_task()`.
When the worker receives a task message (e.g. `tests.tasks.simple_task`), it raises
`celery.exceptions.NotRegistered` because no Celery task with that name exists.

The integration tests mask this because `celery_worker` starts in the same process,
and `_patch_app_and_clear_registry` explicitly calls `ensure_celery_task()` before the
worker thread starts.

**Fix:** Add a Django `AppConfig` with a `ready()` method that discovers all `@task`
functions across `INSTALLED_APPS` and registers them with Celery. This runs in both
the web process and the worker process (since workers run `django.setup()`).

### 2. `get_result()` returns `task=None` when `CELERY_RESULT_EXTENDED=False`

Without extended results, the Celery metadata has no `name` field.
`get_result()` returns a `TaskResult` with `task=None`, which causes:
- `TaskResult.refresh()` → `AttributeError: 'NoneType' object has no attribute 'get_backend'`
- `Task.get_result()` → `AttributeError` on `result.task.func`

**Fix:** Add a system check warning for `CELERY_RESULT_EXTENDED` not being `True`.
Consider raising `TaskResultDoesNotExist` when the task cannot be resolved.

### 3. `get_result()` ignores `args`, `kwargs`, and `worker` from Celery metadata

Extended Celery metadata includes `args`, `kwargs`, and `worker` fields, but
`meta_to_task_result()` hardcodes `args=[]`, `kwargs={}`, `worker_ids=[]`.

**Fix:** Populate these from the metadata when available.

### 4. `task_finished` signal's `TaskResult` has no `_return_value`

In `_make_run_fn()`, the successful `task_result` sent via `task_finished` signal
never has `_return_value` set. Signal handlers that try to access
`task_result.return_value` will get `None` instead of the actual value.

**Fix:** Use `object.__setattr__` to set `_return_value` on the result before
sending the signal.

### 5. `context.attempt` always returns 0

`TaskContext.attempt` returns `len(task_result.worker_ids)`. Our `_make_run_fn()`
sets `worker_ids=[]` and never populates it. So `context.attempt` is always `0`.

**Fix:** Populate `worker_ids` with the current worker's hostname from
`current_task.request.hostname`.


## Bugs / Correctness Issues

### 6. Priority mapping is broker-dependent (inverted on Redis)

Our mapping: Django `100` (highest) → Celery `255`.
- **RabbitMQ**: higher number = higher priority ✓
- **Redis**: lower number = higher priority ✗ (our mapping is inverted!)

Celery does not normalize priority semantics across brokers.

**Fix:** Either detect the broker and invert, or document the limitation clearly.
At minimum, add a system check warning for Redis brokers.

### 7. `get_result()` cannot raise `TaskResultDoesNotExist`

Django's `BaseTaskBackend.get_result()` contract says:
> Raise `TaskResultDoesNotExist` if such result does not exist.

But Celery returns `PENDING` for unknown task IDs — there's no way to distinguish
"task not yet started" from "task never existed". Our test explicitly validates this
wrong behavior (`test_pending_result` asserts `READY` for `'nonexistent-task-id'`).

**Fix:** Document this as a known limitation. Celery fundamentally cannot distinguish
pending from nonexistent.

### 8. `check()` E001 is unreachable

`check()` tries to detect if celery is not installed:
```python
try:
    import celery
except ImportError:
    messages.append(checks.Error(..., id="django_tasks_celery.E001"))
```
But `backend.py` imports from `register.py` which imports `from celery import ...`
at module level. If celery is not installed, `CeleryBackend` cannot even be imported,
so `check()` is never called.

**Fix:** Move celery imports to be lazy/conditional, or remove this check.


## Design Issues

### 9. `aenqueue()` and `aget_result()` are redundant

`BaseTaskBackend` already provides identical implementations:
```python
async def aenqueue(self, task, args, kwargs):
    return await sync_to_async(self.enqueue, thread_sensitive=True)(
        task=task, args=args, kwargs=kwargs
    )
```
Our implementations are exact copies.

**Fix:** Remove them — inherit from the base class.

### 10. Multi-backend configuration is broken

`_django_task_registry` is keyed by `module_path`. The first `enqueue()` call
registers the task with that backend's `run_fn`. Subsequent backends reuse the
first backend's `run_fn` because `ensure_celery_task` short-circuits.

If a user has `TASKS = {"default": CeleryBackend(...), "priority": CeleryBackend(...)}`,
the signals in `run_fn` will always reference the first backend.

**Fix:** Key the registry by `(module_path, backend_alias)` or store the backend
reference differently.

### 11. Thread safety of `_django_task_registry`

`_django_task_registry` is a plain `dict` with TOCTOU race on the
`if celery_name in _django_task_registry: return` check. Not a correctness issue
(all operations are idempotent) but `_register_on_future_apps` would be called
multiple times per task in a race.

**Fix:** Use a `threading.Lock` or accept the minor duplication.


## Missing Tests

### 12. No tests for `aenqueue()` or `aget_result()`

The async API is completely untested.

### 13. No integration test for the real worker discovery flow

All integration tests pre-register tasks. None test the actual production flow
where a worker must discover tasks independently.

### 14. No test for `TaskResult.refresh()`

`refresh()` calls `self.task.get_backend().get_result(self.id)` and updates
attributes. We never test this.

### 15. No test for `return_value` on successful `TaskResult`

The `meta_to_task_result` test for `test_success_meta` doesn't check
`result.return_value` — it only checks `result.status` and `result.finished_at`.

**Note:** `test_result_has_return_value` in integration tests does cover this,
but the unit test doesn't.


## Configuration / Packaging

### 16. Docs pages referenced in `mkdocs.yml` don't exist

`mkdocs.yml` nav references 5 pages that don't exist:
- `getting-started/installation.md`
- `getting-started/quickstart.md`
- `user-guide/configuration.md`
- `reference/api.md`
- `reference/changelog.md`

### 17. `testcontainers[redis]` in dev deps but never used

`pyproject.toml` includes `testcontainers[redis]==4.14.1` in the dev dependency
group, but no test uses testcontainers.

### 18. `ruff target-version = "py313"` vs `requires-python = ">=3.12"`

Minor inconsistency — ruff targets 3.13 but the package supports 3.12.

### 19. No `dependabot.yml` config

`dependabot-automerge.yml` workflow exists but there's no `dependabot.yml`
configuration file to actually enable Dependabot.

### 20. `OPTIONS` key uses lowercase (`celery_app`)

Django convention for backend `OPTIONS` is `UPPERCASE` keys (see cache, database
backends). Our `celery_app` option is lowercase.


## Documentation

### 21. README says "not yet production-ready" but we want production-ready

The README and docs both have alpha warnings. These should be updated as the
package matures.

### 22. No documentation of known limitations

Missing documentation for:
- Priority mapping is broker-dependent (Redis vs RabbitMQ)
- `get_result()` cannot distinguish pending from nonexistent tasks
- `CELERY_RESULT_EXTENDED = True` is required for `get_result()` to return task references
- Worker needs Django setup and task module imports

### 23. Example project `run.py` uses `time.sleep(2)` for polling

Fragile approach — should use `celery_result.get(timeout=...)` or polling loop.

### 24. Example project is broken for real worker deployment

`celery_app.py` doesn't call `autodiscover_tasks()`, and there's no mechanism
for the worker to discover `@task` functions. Only `run_in_process.py` works.

### 25. `docs/index.md` Quick Start doesn't mention `CELERY_RESULT_EXTENDED`

The quick start config omits `CELERY_RESULT_EXTENDED = True`, which is needed
for `get_result()` to work properly.


## Minor / Nice-to-Have

### 26. `compat.py` is no longer needed for backport support

Originally created to support both Django 6.0 and `django-tasks` backport.
Now only Django 6.0 is supported. The module still provides a clean single import
point but could be eliminated.

### 27. Serializer hardcoded to `json`

`_register_on_app` hardcodes `serializer="json"`. Could be configurable via
`OPTIONS` for users who want pickle or msgpack.

### 28. No `CHANGELOG.md` or release notes

The `reference/changelog.md` doc page doesn't exist. No changelog anywhere.
