from concurrent.futures import ThreadPoolExecutor

from django.test import TransactionTestCase
from django.contrib.auth.models import User

from store.models import Product, Order
from store.services.order_service import create_order_safely


class ConcurrencyTest(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user1 = User.objects.create_user(
            username="user1",
            password="123"
        )

        self.user2 = User.objects.create_user(
            username="user2",
            password="123"
        )

        self.product = Product.objects.create(
            name="Laptop",
            price=1200,
            stock_quantity=1
        )

    def try_create_order(self, user):
        try:
            return create_order_safely(
                user=user,
                items=[
                    {
                        "product_id": self.product.id,
                        "quantity": 1
                    }
                ]
            )
        except Exception:
            return None

    def test_two_users_cannot_buy_same_last_item(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(
                self.try_create_order,
                [self.user1, self.user2]
            ))

        successful_orders = [
            result for result in results
            if result is not None
        ]

        self.product.refresh_from_db()

        self.assertEqual(len(successful_orders), 1)
        self.assertEqual(self.product.stock_quantity, 0)
        self.assertEqual(Order.objects.count(), 1)