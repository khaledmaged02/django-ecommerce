"""
Seed fake Orders + OrderItems so you have data to batch-process.

Usage:
    python manage.py seed_orders                       # 1000 orders, today
    python manage.py seed_orders --count 5000
    python manage.py seed_orders --date 2026-05-14
"""
import random
from datetime import datetime, time as dtime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone

from products.models import Product, Order, OrderItem


class Command(BaseCommand):
    help = "Create fake Orders/OrderItems for batch-processing demos."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=1000)
        parser.add_argument("--date", type=str, default=None,
                            help="ISO date YYYY-MM-DD (default: today)")
        parser.add_argument("--username", type=str, default="batchdemo",
                            help="Username to attach orders to (created if missing)")

    def handle(self, *args, **opts):
        target = (datetime.strptime(opts["date"], "%Y-%m-%d").date()
                  if opts["date"] else timezone.now().date())
        user, _ = User.objects.get_or_create(
            username=opts["username"], defaults={"email": "batch@example.com"}
        )

        # Make sure we have at least 5 products to attach order items to.
        products = list(Product.objects.all()[:50])
        if not products:
            for i in range(10):
                products.append(Product.objects.create(
                    name=f"Demo Product {i+1}",
                    price=Decimal(random.randint(10, 200)),
                    stock=1_000_000,
                ))

        created = 0
        for _ in range(opts["count"]):
            # Random time within the target day so they fall inside the batch window.
            t = dtime(random.randint(0, 23), random.randint(0, 59), random.randint(0, 59))
            ts = timezone.make_aware(datetime.combine(target, t))
            total = Decimal("0.00")
            order = Order.objects.create(user=user, total_price=0, status="completed")
            # Manually override created_at so batches by-date work.
            Order.objects.filter(id=order.id).update(created_at=ts)

            n_items = random.randint(1, 4)
            for _ in range(n_items):
                p = random.choice(products)
                qty = random.randint(1, 5)
                line = p.price * qty
                total += line
                OrderItem.objects.create(order=order, product=p, quantity=qty, price=p.price)
            Order.objects.filter(id=order.id).update(total_price=total)
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Created {created} orders for {target} (user={user.username})"
        ))
