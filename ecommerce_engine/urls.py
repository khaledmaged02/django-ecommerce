from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse

def home(request):
    return HttpResponse("Server is working")

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home),
    # path('stores/', include('stores.urls')),
    path('orders/', include('orders.urls')),
]