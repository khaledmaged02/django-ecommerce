from django.urls import path
from .views import add_to_cart, api_login, cart_detail, checkout, check_auth, orders_list, products_list, register, remove_from_cart, update_cart_item
from django.http import JsonResponse

def ping(request):
    return JsonResponse({"ping":"ok"})

urlpatterns = [
    path('ping/', ping, name='api_ping'),
    path('checkout/', checkout, name='checkout'),
    path('login/', api_login, name='api_login'),
    path('register/', register, name='register'),
    path('check-auth/', check_auth, name='check_auth'),
    path('orders/', orders_list, name='orders_list'),
    path('products/', products_list, name='products_list'),
    #cart 
    path('cart/', cart_detail, name='cart_detail'),
    path('cart/add/', add_to_cart, name='add_to_cart'),
    path('cart/remove/', remove_from_cart, name='remove_from_cart'),
    path('cart/update/', update_cart_item, name='update_cart_item'),
    
]
