"""
Celery configuration for the ecommerce_project.

This module bootstraps the Celery app used by Requirement 4 (Batch Processing).
The chosen broker/result-backend is Redis because:
    * It is in-memory => very low task dispatch latency, matching the
      "High-Performance" goal of the project.
    * Redis can also be used as a distributed cache (Requirement 6), so reusing
      it as the broker avoids running a second service.
    * It supports atomic primitives (INCR, LPUSH/BRPOP) used by Celery to
      guarantee that a task is delivered to exactly one worker process,
      which is the foundation of the Producer/Consumer pattern we rely on
      for parallel batch processing.

The worker uses the default 'prefork' pool. With concurrency=N, Celery forks
N OS processes. Each process pulls one chunk from the Redis queue, processes
it in parallel with the others, and writes its partial result back. This is
exactly the "Chunks" model described in Requirement 4.
"""
import os
from celery import Celery

# Tell Celery where Django settings live BEFORE importing anything else.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce_project.settings')

# The string here is the name of the current module's Celery app. It is also
# used as the default queue name if no other queue is declared.
app = Celery('ecommerce_project')

# Pull every config key that starts with 'CELERY_' from Django settings.py.
# The namespace argument means we write CELERY_BROKER_URL in settings, and
# Celery reads it as broker_url internally.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks.py inside every INSTALLED_APP. This is what lets us
# write @shared_task in products/tasks.py and have Celery find it.
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    """A trivial task you can call from a Django shell to verify
    that the worker is alive: `debug_task.delay()`."""
    print(f'Request: {self.request!r}')
