# 🛒 مشروع التجارة الإلكترونية - Person #1 Foundation

## 📋 ما تم إنجازه:

✅ Django project مع PostgreSQL
✅ Models: Product, Category, Order, Cart, Wallet
✅ APIs: تسجيل، تسجيل دخول، منتجات، سلة، شراء
✅ Tests أساسية

## 🚀 كيفية التشغيل:

### 1. تثبيت المتطلبات
```bash
pip install django psycopg2-binary
```

### 2. إعداد قاعدة البيانات
```bash
# في PostgreSQL
CREATE DATABASE ecommerce_db;
```

### 3. Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. إنشاء superuser
```bash
python manage.py createsuperuser
```

### 5. إنشاء محافظ للمستخدمين
```bash
python manage.py create_wallets
```

### 6. تشغيل السيرفر
```bash
python manage.py runserver
```

## 🧪 اختبار APIs:

### تسجيل مستخدم جديد
```bash
curl -X POST http://localhost:8000/api/register/ \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"pass123"}'
```

### تسجيل الدخول
```bash
curl -X POST http://localhost:8000/api/login/ \
  -d "username=test&password=pass123"
```

### جلب المنتجات
```bash
curl http://localhost:8000/api/products/
```

### إضافة إلى السلة
```bash
curl -X POST http://localhost:8000/api/cart/add/ \
  -H "Content-Type: application/json" \
  -d '{"product_id":1,"quantity":2}'
```

### الشراء
```bash
curl -X POST http://localhost:8000/api/checkout/
```

## 📊 نقاط النهاية (API Endpoints):

```
GET  /api/ping/           - اختبار السيرفر
POST /api/register/       - تسجيل مستخدم جديد
POST /api/login/          - تسجيل الدخول
GET  /api/check-auth/     - التحقق من المصادقة
GET  /api/products/       - عرض المنتجات
POST /api/cart/add/       - إضافة للسلة
GET  /api/cart/           - عرض السلة
POST /api/cart/remove/     - حذف من السلة
POST /api/cart/update/     - تحديث الكمية
POST /api/checkout/        - إتمام الطلب
GET  /api/orders/         - عرض الطلبات
```

## 💰 الميزات المالية:

- **محفظة المستخدم**: كل مستخدم يحصل على محفظة برصيد ابتدائي $1000
- **التحقق من الرصيد**: لا يمكن الشراء إذا الرصيد غير كافٍ
- **إدارة المخزون**: التحقق من توفر المنتجات قبل الشراء
- **خصم تلقائي**: خصم المبلغ من المحفظة وتقليل المخزون عند الشراء

## 🧪 تشغيل الاختبارات:
```bash
python manage.py test
```

## 🎯 جودة العمل:
- ✅ كود نظيف ومنظم
- ✅ معالجة أخطاء ممتازة
- ✅ اختبارات شاملة
- ✅ آلية جلسات آمنة
- ✅ تعاملات قاعدة بيانات آمنة (transaction atomic)

## 📈 جاهز للمراحل القادمة:
الأساس مكتمل وجاهز لـ Person #2, #3, #4 لإضافة:
- حماية التزامن (race conditions)
- اختبار الأداء تحت الحمل
- تحسينات الـ concurrency
