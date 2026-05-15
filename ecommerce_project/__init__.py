# This will make sure the Celery app is always imported when
# Django starts, so that @shared_task decorators in any installed
# app use this app (and thus the configured Redis broker).
from .celery import app as celery_app

__all__ = ('celery_app',)
