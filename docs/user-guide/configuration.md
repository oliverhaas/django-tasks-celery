# Configuration

## Django settings

### `TASKS`

Configure one or more task backends:

```python
TASKS = {
    "default": {
        "BACKEND": "django_tasks_celery.CeleryBackend",
        "QUEUES": ["default", "high", "low"],
        "OPTIONS": {
            "celery_app": "myproject.celery.app",  # Optional: explicit Celery app path
        },
    },
}
```

| Key | Description |
|-----|-------------|
| `BACKEND` | Import path to the backend class. Use `"django_tasks_celery.CeleryBackend"`. |
| `QUEUES` | List of allowed queue names. Tasks using unlisted queues are rejected. |
| `OPTIONS` | Backend-specific options (see below). |

### Backend OPTIONS

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `celery_app` | `str` | Auto-detect | Import path to the Celery app instance (e.g. `"myproject.celery.app"`). If omitted, uses `celery.current_app`. |

### Celery settings

These standard Celery settings are read from your Django settings (with the `CELERY_` prefix):

| Setting | Required | Description |
|---------|----------|-------------|
| `CELERY_BROKER_URL` | Yes | Broker connection URL (e.g. `redis://localhost:6379/0`). |
| `CELERY_RESULT_BACKEND` | Recommended | Result backend URL. Required for `get_result()`. |
| `CELERY_RESULT_EXTENDED` | Recommended | Set to `True` for `get_result()` to resolve task references, args, kwargs, and worker IDs. |

## System checks

The backend runs Django system checks at startup:

| ID | Level | Description |
|----|-------|-------------|
| `django_tasks_celery.E002` | Error | Could not resolve the Celery app. |
| `django_tasks_celery.W001` | Warning | Result backend is disabled — `get_result()` will not work. |
| `django_tasks_celery.W002` | Warning | `CELERY_RESULT_EXTENDED` is not enabled — `get_result()` will not resolve task references. |

## Feature support

| Feature | Supported |
|---------|-----------|
| `supports_defer` | Yes (via Celery `eta`) |
| `supports_async_task` | Yes |
| `supports_priority` | Yes (mapped to 0–255 AMQP range) |
| `supports_get_result` | Dynamic — `True` when a result backend is configured |
