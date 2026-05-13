from celery import shared_task
import time


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def process_order_invoice(self, order_id, user_email):

    print(f"Starting invoice processing for Order {order_id}")

    
    time.sleep(5)

    print(f"Invoice generated for {user_email}")

    return {
        "status": "success",
        "order_id": order_id,
        "email": user_email
    }