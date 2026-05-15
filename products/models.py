
from django.db import models
from django.contrib.auth.models import User

class Product(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    
class Category(models.Model):
   
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Order(models.Model):
   
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=50, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order #{self.id} - {self.user.username}"
    
class OrderItem(models.Model):

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"
    
class Cart(models.Model):
   
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cart for {self.user.username}"


class CartItem(models.Model):
   
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

class Wallet(models.Model):

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}'s Wallet - ${self.balance}"


# =============================================================================
#  BATCH PROCESSING MODELS (Requirement 4)
# =============================================================================
# We persist two things:
#   1. DailySalesReport: the *output* of a successful batch run for one day.
#      One row per (date) — UNIQUE constraint enforces idempotency, i.e. if
#      you re-run the batch for the same day it OVERWRITES, never duplicates.
#   2. BatchJobLog: the *metadata* of every batch run (succeeded or failed).
#      This is what we'll inspect during the demo to prove the job ran in
#      parallel and to measure speed-up.
# -----------------------------------------------------------------------------
class DailySalesReport(models.Model):
    """Aggregated sales for a single day, produced by the chunked batch job."""

    report_date = models.DateField(unique=True, db_index=True)
    total_orders = models.IntegerField(default=0)
    total_items_sold = models.IntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # Per-product breakdown stored as JSON so we don't need a second table.
    # Shape: {"<product_id>": {"name": "...", "qty": N, "revenue": "..."}}
    product_breakdown = models.JSONField(default=dict, blank=True)
    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-report_date']

    def __str__(self):
        return f"SalesReport[{self.report_date}] orders={self.total_orders} revenue=${self.total_revenue}"


class BatchJobLog(models.Model):
    """One row per batch execution. Used to compute speed-up & detect failures."""

    STATUS_CHOICES = [
        ('RUNNING', 'Running'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
    ]

    job_name = models.CharField(max_length=100, db_index=True)
    # We support running the batch in two modes (sequential vs. chunked)
    # so we can show the speed-up in the report.
    mode = models.CharField(max_length=20, default='chunked')  # 'sequential' | 'chunked'
    chunk_size = models.IntegerField(null=True, blank=True)
    total_records = models.IntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='RUNNING')
    error_message = models.TextField(blank=True, default='')
    # Free-form JSON for anything else worth recording (number of chunks,
    # number of workers, per-chunk timings, etc.)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.job_name}[{self.mode}] {self.status} ({self.duration_seconds}s)"


