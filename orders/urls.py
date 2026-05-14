from django.urls import path
from .views import create_order, get_product_details

urlpatterns = [
    path('create/', create_order),
    path('product/<int:product_id>/', get_product_details),
]