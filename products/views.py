import json
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import Cart, CartItem, Order, OrderItem, Product, Wallet, DailySalesReport, BatchJobLog
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User

# Imports for Requirements 4 & 5 — kept local where possible to avoid
# circular imports at startup if Celery isn't installed yet in dev envs.
from .tasks import run_daily_sales_batch
from .load_balancer import compare_all_strategies, run_simulation, STRATEGIES


#  CHECKOUT: إتمام عملية الشراء والدفع
@csrf_exempt
@transaction.atomic
def checkout(request):

    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    user = request.user
    
    try:
        cart = Cart.objects.get(user=user)
    except Cart.DoesNotExist:
        return JsonResponse({"error": "Cart is empty"}, status=400)
    
    # التحقق: هل السلة فارغة؟
    cart_items = cart.items.all()
    if not cart_items:
        return JsonResponse({"error": "Cart is empty"}, status=400)

    #  حساب المجموع الكلي للسلة
    total_price = 0
    for item in cart_items:
        total_price += item.price * item.quantity  

    #  التحقق من رصيد محفظة المستخدم
    wallet = user.wallet
    if wallet.balance < total_price:
        return JsonResponse({
            "error": f"Insufficient balance. Required: ${total_price}, Available: ${wallet.balance}"
        }, status=400)

    #  التحقق من توفر المخزون لكل منتج
    for item in cart_items:
        product = item.product
        if product.stock < item.quantity:
            return JsonResponse({
                "error": f"Insufficient stock for {product.name}. Available: {product.stock}, Requested: {item.quantity}"
            }, status=400)

    #  خصم المبلغ من محفظة المستخدم
    wallet.balance -= total_price
    wallet.save()

    #  تقليل المخزون لكل منتج
    for item in cart_items:
        product = item.product
        product.stock -= item.quantity 
        product.save()

    #  إنشاء طلب جديد في النظام
    order = Order.objects.create(
        user=user,
        total_price=total_price,
        status="completed" 
    )

    #  نسخ عناصر السلة للطلب
    for item in cart_items:
        OrderItem.objects.create(
            order=order,
            product=item.product,
            quantity=item.quantity,
            price=item.price
        )

    #  تفريغ السلة بعد الشراء
    cart.items.all().delete()

    return JsonResponse({
        "message": "Order created successfully",
        "order_id": order.id,
        "total_paid": str(total_price),
        "remaining_balance": str(wallet.balance)
    })



#  LOGIN: تسجيل دخول المستخدم

@csrf_exempt
def api_login(request):
   
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        
        user = authenticate(username=username, password=password)
        if user is not None:

            login(request, user)

            # إنشاء سلة للمستخدم إذا لم تكن موجودة
            cart, created = Cart.objects.get_or_create(user=user)
            return JsonResponse({"message": "Login successful", "cart_created": created})
        else:
            return JsonResponse({"error": "Invalid credentials"}, status=401)
    return JsonResponse({"error": "POST required"}, status=400)


#  CHECK_AUTH: التحقق من حالة الجلسة

def check_auth(request):
    """دالة اختبار للتحقق من حالة المصادقة والجلسة"""
    return JsonResponse({
        "is_authenticated": request.user.is_authenticated,  # هل المستخدم مسجل؟
        "username": request.user.username if request.user.is_authenticated else None,  # اسم المستخدم
        "session_key": request.session.session_key,  # مفتاح الجلسة
        "has_cart": Cart.objects.filter(user=request.user).exists() if request.user.is_authenticated else False  # هل عنده سلة؟
    })
 

#  ORDERS_LIST: عرض طلبات المستخدم

def orders_list(request):
    
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    orders = Order.objects.filter(user=request.user)
    data = []

    for order in orders:
        data.append({
            "id": order.id,  
            "created_at": order.created_at, 
            "total": order.total_price,  
        })
    return JsonResponse({"orders": data})


#  PRODUCTS_LIST: عرض كل المنتجات المتوفرة
def products_list(request):
   
    products = Product.objects.all()

    data = []
    for product in products:
        data.append({
            "id": product.id,  
            "name": product.name,  
            "price": product.price,  
            "stock": product.stock,  
        })

    return JsonResponse({"products": data})


#  CART_DETAIL: عرض محتويات سلة المستخدم

def cart_detail(request):

    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    cart, created = Cart.objects.get_or_create(user=request.user)

    items = []
    for item in cart.items.all():
        items.append({
            "product": item.product.name,  # اسم المنتج
            "quantity": item.quantity,  # الكمية
            "price": item.product.price,  # سعر الوحدة
        })

    return JsonResponse({"cart": items})


#  ADD_TO_CART: إضافة منتج للسلة=
@csrf_exempt
def add_to_cart(request):

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=400)

    try:
        data = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    product_id = data.get("product_id")
    quantity = data.get("quantity", 1)  

    
    if not product_id:
        return JsonResponse({"error": "Product ID required"}, status=400)

    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return JsonResponse({"error": "Product not found"}, status=404)

   
    cart, _ = Cart.objects.get_or_create(user=request.user)

    # إضافة المنتج للسلة أو تحديث الكمية
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart, 
        product=product,
        defaults={'price': product.price, 'quantity': quantity}
    )
    if not created:  
        cart_item.quantity += quantity  
        cart_item.save()

    return JsonResponse({"message": "Product added to cart"})


#  REMOVE_FROM_CART: حذف منتج من السلة

@csrf_exempt
def remove_from_cart(request):

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    product_id = data.get("product_id")
    if not product_id:
        return JsonResponse({"error": "Product ID required"}, status=400)

    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return JsonResponse({"error": "Product not found"}, status=404)

    cart, _ = Cart.objects.get_or_create(user=request.user)

    # البحث عن المنتج في السلة وحذفه
    try:
        cart_item = CartItem.objects.get(cart=cart, product=product)
        cart_item.delete()  # حذف المنتج من السلة
        return JsonResponse({"message": "Product removed from cart"})
    except CartItem.DoesNotExist:
        return JsonResponse({"error": "Product not in cart"}, status=404)
    

#  UPDATE_CART_ITEM: تحديث كمية منتج في السلة

@csrf_exempt
def update_cart_item(request):
   
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

   
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    product_id = data.get("product_id")
    quantity = data.get("quantity")

    if not product_id or quantity is None:
        return JsonResponse({"error": "Product ID and quantity required"}, status=400)

    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return JsonResponse({"error": "Product not found"}, status=404)

    # جلب سلة المستخدم
    cart, _ = Cart.objects.get_or_create(user=request.user)

    # البحث عن المنتج في السلة وتحديث الكمية
    try:
        cart_item = CartItem.objects.get(cart=cart, product=product)
        cart_item.quantity = quantity  
        cart_item.save()
        return JsonResponse({"message": "Cart item updated"})
    except CartItem.DoesNotExist:
        return JsonResponse({"error": "Product not in cart"}, status=404)


#  REGISTER: تسجيل مستخدم جديد

@csrf_exempt
def register(request):
   
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    try:
        data = json.loads(request.body)
    except:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    username = data.get("username")
    password = data.get("password")
    email = data.get("email", "")

    if not username or not password:
        return JsonResponse({"error": "Username and password required"}, status=400)

    if User.objects.filter(username=username).exists():
        return JsonResponse({"error": "Username already exists"}, status=400)

    user = User.objects.create_user(username=username, password=password, email=email)
    
    # إنشاء محفظة برصيد ابتدائي 1000$
    Wallet.objects.create(user=user, balance=1000.00)
    
    login(request, user)

    return JsonResponse({
        "message": "User registered successfully",
        "username": user.username,
        "initial_balance": "1000.00"
    })


# =============================================================================
#  REQUIREMENT 4 — BATCH PROCESSING ENDPOINTS
# =============================================================================
# These endpoints let the team (and the grader) trigger and inspect the
# daily-sales batch job from the API. The actual work runs in Celery workers.

@csrf_exempt
def trigger_daily_sales_batch(request):
    """POST /api/batch/run/  body: {"date": "YYYY-MM-DD", "chunk_size": 200, "mode": "chunked"}
    Returns the BatchJobLog id immediately. The job runs in the background."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=400)

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        body = {}

    report_date = body.get("date")                  # None => yesterday
    chunk_size = int(body.get("chunk_size", 200))
    mode = body.get("mode", "chunked")              # "chunked" | "sequential"

    # .delay() = "send to Celery, don't wait". We get back an AsyncResult.
    async_res = run_daily_sales_batch.delay(
        report_date_str=report_date,
        chunk_size=chunk_size,
        mode=mode,
    )
    return JsonResponse({
        "message": "Batch job dispatched",
        "celery_task_id": async_res.id,
        "params": {"date": report_date, "chunk_size": chunk_size, "mode": mode},
    })


def batch_job_status(request, job_log_id: int):
    """GET /api/batch/status/<job_log_id>/ — inspect a BatchJobLog row."""
    try:
        log = BatchJobLog.objects.get(id=job_log_id)
    except BatchJobLog.DoesNotExist:
        return JsonResponse({"error": "BatchJobLog not found"}, status=404)
    return JsonResponse({
        "id": log.id,
        "job_name": log.job_name,
        "mode": log.mode,
        "chunk_size": log.chunk_size,
        "total_records": log.total_records,
        "status": log.status,
        "started_at": log.started_at.isoformat() if log.started_at else None,
        "finished_at": log.finished_at.isoformat() if log.finished_at else None,
        "duration_seconds": log.duration_seconds,
        "error_message": log.error_message,
        "metadata": log.metadata,
    })


def daily_sales_report(request):
    """GET /api/batch/report/?date=YYYY-MM-DD — read the produced report."""
    date_str = request.GET.get("date")
    qs = DailySalesReport.objects.all()
    if date_str:
        qs = qs.filter(report_date=date_str)
    data = [{
        "report_date": str(r.report_date),
        "total_orders": r.total_orders,
        "total_items_sold": r.total_items_sold,
        "total_revenue": str(r.total_revenue),
        "product_breakdown": r.product_breakdown,
        "generated_at": r.generated_at.isoformat(),
    } for r in qs[:30]]
    return JsonResponse({"reports": data})


# =============================================================================
#  REQUIREMENT 5 — LOAD DISTRIBUTION ENDPOINT
# =============================================================================
@csrf_exempt
def simulate_load(request):
    """GET/POST /api/load/simulate/
    Query params (or JSON body): strategy=all|round_robin|random|...,
                                 servers=4, requests=200
    Runs the in-process simulator and returns the JSON metrics."""
    if request.method == "POST":
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            body = {}
        strategy = body.get("strategy", "all")
        num_servers = int(body.get("servers", 4))
        num_requests = int(body.get("requests", 200))
    else:
        strategy = request.GET.get("strategy", "all")
        num_servers = int(request.GET.get("servers", 4))
        num_requests = int(request.GET.get("requests", 200))

    if strategy == "all":
        result = compare_all_strategies(num_requests=num_requests, num_servers=num_servers)
    elif strategy in STRATEGIES:
        result = [run_simulation(strategy, num_servers=num_servers, num_requests=num_requests)]
    else:
        return JsonResponse({"error": f"Unknown strategy: {strategy}",
                             "available": list(STRATEGIES) + ["all"]}, status=400)

    return JsonResponse({"results": result})
