from django.urls import path
from .views import (
    add_to_cart, api_login, cart_detail, checkout, check_auth, orders_list,
    products_list, register, remove_from_cart, update_cart_item,
    # Requirement 4 — Batch Processing
    trigger_daily_sales_batch, batch_job_status, daily_sales_report,
    # Requirement 5 — Load Distribution
    simulate_load,
)
from django.http import JsonResponse

def ping(request):
    return JsonResponse({"ping": "ok"})

urlpatterns = [
    path('ping/', ping, name='api_ping'),
    path('checkout/', checkout, name='checkout'),
    path('login/', api_login, name='api_login'),
    path('register/', register, name='register'),
    path('check-auth/', check_auth, name='check_auth'),
    path('orders/', orders_list, name='orders_list'),
    path('products/', products_list, name='products_list'),
    # cart
    path('cart/', cart_detail, name='cart_detail'),
    path('cart/add/', add_to_cart, name='add_to_cart'),
    path('cart/remove/', remove_from_cart, name='remove_from_cart'),
    path('cart/update/', update_cart_item, name='update_cart_item'),

    # Requirement 4 — Batch processing
    path('batch/run/',                trigger_daily_sales_batch, name='batch_run'),
    path('batch/status/<int:job_log_id>/', batch_job_status,     name='batch_status'),
    path('batch/report/',             daily_sales_report,        name='batch_report'),

    # Requirement 5 — Load distribution simulator
    path('load/simulate/',            simulate_load,             name='load_simulate'),
]
