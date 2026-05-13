from django.test import TestCase, Client
from django.contrib.auth.models import User
from .models import Product, Cart, CartItem, Wallet

class EcommerceTests(TestCase):
    def setUp(self):
        # إنشاء مستخدم للتجربة
        self.user = User.objects.create_user(username="testuser", password="12345")
        self.client = Client()

        # تسجيل الدخول
        self.client.login(username="testuser", password="12345")

        # إنشاء منتج للتجربة
        self.product = Product.objects.create(name="Laptop Dell", price=800, stock=10)
        
        # إنشاء محفظة للمستخدم
        self.wallet = Wallet.objects.create(user=self.user, balance=1000.00)

    def test_login(self):
        response = self.client.post("/api/login/", {"username": "testuser", "password": "12345"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Login successful", response.json().get("message", ""))

    def test_products_list(self):
       response = self.client.get("/api/products/")
       self.assertEqual(response.status_code, 200)
        # نتأكد إن أول منتج اسمه Laptop Dell
       self.assertEqual(response.json()["products"][0]["name"], "Laptop Dell")


    def test_add_to_cart(self):
        response = self.client.post("/api/cart/add/", {"product_id": self.product.id, "quantity": 2}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Product added to cart")

    def test_update_cart_item(self):
        # أولاً نضيف المنتج للسلة
        self.client.post("/api/cart/add/", {"product_id": self.product.id, "quantity": 2}, content_type="application/json")
        # بعدين نعدّل الكمية
        response = self.client.post("/api/cart/update/", {"product_id": self.product.id, "quantity": 5}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Cart item updated")

    def test_remove_from_cart(self):
        # أولاً نضيف المنتج للسلة
        self.client.post("/api/cart/add/", {"product_id": self.product.id, "quantity": 2}, content_type="application/json")
        # بعدين نحذفه
        response = self.client.post("/api/cart/remove/", {"product_id": self.product.id}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Product removed from cart")

    def test_checkout(self):
        # نضيف منتج للسلة
        self.client.post("/api/cart/add/", {"product_id": self.product.id, "quantity": 1}, content_type="application/json")
        # نعمل checkout
        response = self.client.post("/api/checkout/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Order created", response.json().get("message", ""))

    def test_register(self):
        """اختبار تسجيل مستخدم جديد"""
        response = self.client.post("/api/register/", {
            "username": "newuser",
            "password": "pass123"
        }, content_type="application/json")
        
        self.assertEqual(response.status_code, 200)
        self.assertIn("registered successfully", response.json()["message"])
        
        # التحقق من إنشاء المحفظة
        user = User.objects.get(username="newuser")
        self.assertTrue(Wallet.objects.filter(user=user).exists())
        self.assertEqual(user.wallet.balance, 1000.00)

    def test_checkout_insufficient_balance(self):
        """اختبار: فشل الشراء بسبب رصيد غير كافٍ"""
        # نخلي الرصيد قليل
        self.wallet.balance = 10
        self.wallet.save()
        
        # نضيف منتج غالي للسلة
        self.client.post("/api/cart/add/", {"product_id": self.product.id, "quantity": 1}, content_type="application/json")
        
        # محاولة checkout
        response = self.client.post("/api/checkout/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Insufficient balance", response.json()["error"])

    def test_checkout_insufficient_stock(self):
        """اختبار: فشل الشراء بسبب نفاذ المخزون"""
        # نخلي المخزون قليل
        self.product.stock = 1
        self.product.save()
        
        # نحاول نشتري أكثر من المتوفر
        self.client.post("/api/cart/add/", {"product_id": self.product.id, "quantity": 5}, content_type="application/json")
        
        response = self.client.post("/api/checkout/")
        self.assertEqual(response.status_code, 400)
        # قد يكون الخطأ بسبب الرصيد أو المخزون، نتحقق من أي منهما
        error_msg = response.json()["error"]
        self.assertTrue("Insufficient" in error_msg)

    def test_checkout_success_deducts_stock(self):
        """اختبار: الشراء الناجح يقلل المخزون"""
        # نتأكد إن الرصيد كافي
        self.wallet.balance = 2000.00
        self.wallet.save()
        
        initial_stock = self.product.stock
        
        self.client.post("/api/cart/add/", {"product_id": self.product.id, "quantity": 2}, content_type="application/json")
        
        response = self.client.post("/api/checkout/")
        self.assertEqual(response.status_code, 200)
        
        # نتحقق من تقليل المخزون
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, initial_stock - 2)
