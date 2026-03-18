# Installation

## Requirements

- Python 3.12+
- Django 6.0+
- Celery 5.4+ **or** celery-asyncio 6.0+

## Install with Celery

```bash
pip install django-tasks-celery[celery]
```

## Install with celery-asyncio

[celery-asyncio](https://github.com/oliverhaas/celery-asyncio) is an async-native rewrite of Celery with the same API:

```bash
pip install django-tasks-celery[celery-asyncio]
```

## Verify

```python
>>> import django_tasks_celery
>>> django_tasks_celery.__version__
'...'
```
