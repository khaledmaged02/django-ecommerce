#from .tasks import process_order_invoice

# from django.http import JsonResponse
# from .tasks import test_task

# def create_order(request):
#     test_task.delay(101)

#     return JsonResponse({
#         "message": "Order sent to background"
#     })
import random
from django.http import JsonResponse
from django.core.cache import cache
from django.shortcuts import get_object_or_404

from store.models import Product
from .tasks import process_order_invoice


def create_order(request):
    order_id = random.randint(10000, 99999)
    user_email = "student@university.edu"

    try:
        process_order_invoice.delay(order_id, user_email)
        return JsonResponse({
            "status": "success",
            "message": "Order processing started in background",
            "order_id": order_id
        })
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": "Failed to enqueue task",
            "details": str(e)
        }, status=500)


def get_product_details(request, product_id):
    cache_key = f"product_{product_id}"
    product_data = cache.get(cache_key)

    if product_data:
        return JsonResponse({
            "source": "Redis Cache",
            "data": product_data
        })

    product = get_object_or_404(Product, id=product_id)

    product_data = {
        "id": product.id,
        "name": product.name,
        "price": float(product.price),
    }

    cache.set(cache_key, product_data, timeout=600)

    return JsonResponse({
        "source": "Database",
        "data": product_data
    })