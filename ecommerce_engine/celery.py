import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce_engine.settings')

app = Celery('ecommerce_engine')


app.config_from_object('django.conf:settings', namespace='CELERY')


app.conf.broker_url = 'redis://localhost:6379/0'


app.conf.result_backend = 'redis://localhost:6379/0'

app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')