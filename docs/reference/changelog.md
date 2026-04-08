# Changelog

## 0.1.0 (2026-04-08)

First stable release.

- No API changes from 0.1.0a2

## 0.1.0a2 (2026-03-15)

Initial alpha release.

- `CeleryBackend` implementing Django 6.0's `BaseTaskBackend`
- `enqueue()` / `get_result()` with full Celery integration
- Priority mapping (Django -100..100 to Celery/AMQP 0..255)
- Deferred execution via Celery `eta`
- Sync and async task function support
- Django signals: `task_enqueued`, `task_started`, `task_finished`
- System checks for Celery app, result backend, and `CELERY_RESULT_EXTENDED`
- Worker-side task auto-discovery via `validate_task()`
- Support for both `celery` and `celery-asyncio` as optional dependencies
