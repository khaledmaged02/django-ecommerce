from decimal import Decimal
from django.db import transaction
from store.models import Product, Order, OrderItem


def create_order_safely(user, items):
    with transaction.atomic():
        order = Order.objects.create(
            user=user,
            status="pending",
            total_price=Decimal("0.00")
        )

        total_price = Decimal("0.00")

        for item in items:
            product_id = item["product_id"]
            quantity = item["quantity"]

            product = Product.objects.select_for_update().get(id=product_id)

            if product.stock_quantity < quantity:
                raise Exception(f"Not enough stock for product: {product.name}")

            product.stock_quantity -= quantity
            product.save()

            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=quantity,
                price_at_purchase=product.price
            )

            total_price += product.price * quantity

        order.total_price = total_price
        order.status = "completed"
        order.save()

        return order