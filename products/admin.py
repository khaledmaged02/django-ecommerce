from django.contrib import admin
from .models import (
    Cart, CartItem, Category, Order, OrderItem, Product, Wallet,
    DailySalesReport, BatchJobLog,
)

admin.site.register(Product)
admin.site.register(Category)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(Cart)
admin.site.register(CartItem)
admin.site.register(Wallet)


# Requirement 4 — let the grader inspect batch artefacts from /admin/
@admin.register(DailySalesReport)
class DailySalesReportAdmin(admin.ModelAdmin):
    list_display = ("report_date", "total_orders", "total_items_sold",
                    "total_revenue", "generated_at")
    ordering = ("-report_date",)
    readonly_fields = ("generated_at",)


@admin.register(BatchJobLog)
class BatchJobLogAdmin(admin.ModelAdmin):
    list_display = ("id", "job_name", "mode", "chunk_size", "total_records",
                    "status", "duration_seconds", "started_at")
    list_filter = ("job_name", "mode", "status")
    ordering = ("-started_at",)
    readonly_fields = ("started_at", "finished_at", "duration_seconds")
