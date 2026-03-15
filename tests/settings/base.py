"""Base Django settings for tests."""

SECRET_KEY = "test-secret-key-not-for-production"
DEBUG = True
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}
USE_TZ = True
ROOT_URLCONF = "tests.settings.urls"

# Celery config (eager mode for unit tests)
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_RESULT_EXTENDED = True

# Django Tasks config
TASKS = {
    "default": {
        "BACKEND": "django_tasks_celery.CeleryBackend",
        "QUEUES": ["default", "high", "low"],
    },
}
