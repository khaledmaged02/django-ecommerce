"""
products/tasks.py
==================
Celery tasks that implement Requirement 4 (Batch Processing) of the
High-Performance E-Commerce Backend Engine project.

WHAT THIS FILE DOES
-------------------
We expose a *background job* — `run_daily_sales_batch` — that:

    1. Looks at every Order created within a given calendar day.
    2. Splits those orders into fixed-size "chunks" (default = 200 orders).
    3. Hands each chunk to its own Celery worker process via a `chord`.
       Workers run in parallel on the SAME or DIFFERENT machines.
    4. Each worker returns a partial aggregate (orders, items, revenue,
       per-product breakdown) for the chunk it received.
    5. The chord's *callback* — `aggregate_chunks` — merges the partials
       and writes a single DailySalesReport row.

This is the textbook MAP-REDUCE pattern adapted to Celery:

    map step  =>  process_chunk()        (runs N times in parallel)
    reduce    =>  aggregate_chunks()     (runs once at the end)

WHY CHUNKING?
-------------
* RAM: loading 1,000,000 orders at once is a memory bomb. 200 at a time
  fits in cache.
* PARALLELISM: a single thread aggregating 1M rows = sequential. With
  chunks we get true CPU parallelism limited only by `--concurrency N`
  on the worker.
* RESILIENCE: if a chunk fails we can retry just that chunk, not the
  whole job (Celery does this for us via `acks_late=True`).

CRITICAL-SECTION / RACE-CONDITION NOTES
---------------------------------------
* Each chunk operates on a DISJOINT set of order IDs (we slice by primary
  key). There is no shared mutable state between chunk tasks, so we do
  not need a lock during the map phase. This is "embarrassingly parallel"
  by construction.
* The reduce phase happens in a single worker process (the callback) and
  performs ONE `update_or_create` inside `transaction.atomic` — this is
  the only synchronization point and it is protected by Postgres's row
  lock on the unique `report_date` column. No race possible.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable, List, Dict, Any

from celery import shared_task, chord
from django.db import transaction
from django.utils import timezone

from .models import Order, OrderItem, DailySalesReport, BatchJobLog

logger = logging.getLogger(__name__)

# Default chunk size. 200 is a sweet spot for Postgres + Python:
#   * Small enough to fit comfortably in memory.
#   * Large enough that per-task overhead (~1-3 ms) is amortized.
# Tune this from the API/CLI when demonstrating throughput trade-offs.
DEFAULT_CHUNK_SIZE = 200


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _resolve_target_date(report_date_str: str | None) -> date:
    """Accept ISO 'YYYY-MM-DD' or default to *yesterday* (typical daily-job convention)."""
    if report_date_str:
        return datetime.strptime(report_date_str, "%Y-%m-%d").date()
    return (timezone.now() - timedelta(days=1)).date()


def _chunked(iterable: List[int], size: int) -> Iterable[List[int]]:
    """Yield successive `size`-sized slices from a list of IDs."""
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


# -----------------------------------------------------------------------------
# THE MAP STEP — runs in parallel, once per chunk
# -----------------------------------------------------------------------------
@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,          # exponential back-off: 1s, 2s, 4s, ...
    retry_kwargs={"max_retries": 3},
    acks_late=True,              # see acks_late note in settings.py
)
def process_chunk(self, order_ids: List[int]) -> Dict[str, Any]:
    """
    Process ONE chunk of order IDs and return a partial aggregate.

    This task is intentionally SIDE-EFFECT FREE — it only READs from the DB
    and RETURNS a plain dict. All writes happen in the reduce step. That
    keeps it idempotent and safe to retry.
    """
    chunk_started = time.perf_counter()

    # Pull all items for this chunk in ONE query (select_related to avoid
    # the N+1 problem on Product.name). This is the I/O bottleneck we are
    # parallelizing.
    items = (
        OrderItem.objects
        .filter(order_id__in=order_ids)
        .select_related("product", "order")
    )

    total_orders = len(set(order_ids))
    total_items = 0
    total_revenue = Decimal("0.00")
    product_breakdown: Dict[str, Dict[str, Any]] = {}

    for item in items:
        line_revenue = item.price * item.quantity
        total_items += item.quantity
        total_revenue += line_revenue

        pid = str(item.product_id)
        entry = product_breakdown.setdefault(
            pid, {"name": item.product.name, "qty": 0, "revenue": "0.00"}
        )
        entry["qty"] += item.quantity
        entry["revenue"] = str(Decimal(entry["revenue"]) + line_revenue)

    chunk_elapsed = time.perf_counter() - chunk_started
    logger.info(
        "process_chunk: %d orders, %d items, $%s, took %.3fs",
        total_orders, total_items, total_revenue, chunk_elapsed,
    )

    # Return type MUST be JSON-serializable (we set JSON serializer in settings).
    return {
        "orders": total_orders,
        "items": total_items,
        "revenue": str(total_revenue),
        "products": product_breakdown,
        "elapsed": chunk_elapsed,
        "chunk_size": len(order_ids),
    }


# -----------------------------------------------------------------------------
# THE REDUCE STEP — runs ONCE after every chunk finishes
# -----------------------------------------------------------------------------
@shared_task(bind=True, acks_late=True)
def aggregate_chunks(
    self,
    chunk_results: List[Dict[str, Any]],
    report_date_str: str,
    job_log_id: int,
) -> Dict[str, Any]:
    """Merge partial aggregates into a single DailySalesReport row."""
    target_date = datetime.strptime(report_date_str, "%Y-%m-%d").date()

    total_orders = 0
    total_items = 0
    total_revenue = Decimal("0.00")
    merged_products: Dict[str, Dict[str, Any]] = {}
    chunk_timings: List[float] = []

    for r in chunk_results:
        total_orders += r["orders"]
        total_items += r["items"]
        total_revenue += Decimal(r["revenue"])
        chunk_timings.append(r["elapsed"])
        # Merge per-product dictionaries.
        for pid, info in r["products"].items():
            if pid in merged_products:
                merged_products[pid]["qty"] += info["qty"]
                merged_products[pid]["revenue"] = str(
                    Decimal(merged_products[pid]["revenue"]) + Decimal(info["revenue"])
                )
            else:
                merged_products[pid] = {
                    "name": info["name"],
                    "qty": info["qty"],
                    "revenue": info["revenue"],
                }

    # The ONLY critical section in the whole pipeline. Postgres serializes
    # writes to a single row via its standard row-locking; the atomic block
    # makes the read-modify-write of BatchJobLog visible together.
    with transaction.atomic():
        DailySalesReport.objects.update_or_create(
            report_date=target_date,
            defaults={
                "total_orders": total_orders,
                "total_items_sold": total_items,
                "total_revenue": total_revenue,
                "product_breakdown": merged_products,
            },
        )

        log = BatchJobLog.objects.get(id=job_log_id)
        log.status = "SUCCESS"
        log.finished_at = timezone.now()
        log.duration_seconds = (log.finished_at - log.started_at).total_seconds()
        # Helpful diagnostics for the demo / report:
        log.metadata = {
            **log.metadata,
            "num_chunks": len(chunk_results),
            "chunk_timings_sec": chunk_timings,
            "max_chunk_time": max(chunk_timings) if chunk_timings else 0,
            "min_chunk_time": min(chunk_timings) if chunk_timings else 0,
            "sum_chunk_time": sum(chunk_timings),  # would-be sequential time
        }
        log.save()

    return {
        "report_date": str(target_date),
        "total_orders": total_orders,
        "total_items_sold": total_items,
        "total_revenue": str(total_revenue),
        "num_chunks": len(chunk_results),
        "job_log_id": job_log_id,
    }


# -----------------------------------------------------------------------------
# THE ENTRY POINT — the "Background Job" Requirement 4 calls for
# -----------------------------------------------------------------------------
@shared_task(bind=True)
def run_daily_sales_batch(
    self,
    report_date_str: str | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    mode: str = "chunked",
) -> Dict[str, Any]:
    """
    Launch the daily sales batch.

    Args:
        report_date_str: ISO date 'YYYY-MM-DD'. Defaults to yesterday.
        chunk_size:      Orders per chunk-task. Tune to show throughput curves.
        mode:            'chunked'   -> map/reduce via chord (PARALLEL, default)
                         'sequential'-> single pass, no chunks (BASELINE for
                                         the speed-up report — requirement 10).

    Returns:
        dict describing what was dispatched. The actual aggregate is written
        asynchronously by `aggregate_chunks` and ends up in DailySalesReport.
    """
    target_date = _resolve_target_date(report_date_str)

    # Collect order IDs for the target day. We grab only IDs (not full rows)
    # so the dispatcher's memory footprint stays tiny even for millions of
    # orders. The workers will re-fetch their slice.
    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    order_ids = list(
        Order.objects
        .filter(created_at__gte=day_start, created_at__lt=day_end)
        .values_list("id", flat=True)
    )

    # Open a BatchJobLog up-front so the user can see "RUNNING" jobs
    # while they're in flight.
    log = BatchJobLog.objects.create(
        job_name="daily_sales_batch",
        mode=mode,
        chunk_size=chunk_size,
        total_records=len(order_ids),
        metadata={"target_date": str(target_date)},
    )

    if not order_ids:
        # Nothing to do — write an empty report and finish.
        with transaction.atomic():
            DailySalesReport.objects.update_or_create(
                report_date=target_date,
                defaults={"total_orders": 0, "total_items_sold": 0,
                          "total_revenue": 0, "product_breakdown": {}},
            )
            log.status = "SUCCESS"
            log.finished_at = timezone.now()
            log.duration_seconds = (log.finished_at - log.started_at).total_seconds()
            log.save()
        return {"report_date": str(target_date), "total_orders": 0, "dispatched_chunks": 0,
                "job_log_id": log.id}

    # --- Sequential baseline (for benchmarking ONLY) -------------------------
    if mode == "sequential":
        # Run the whole thing in a single task — no chunking, no parallelism.
        # This is what we compare against to compute speed-up.
        result = process_chunk.run(order_ids)
        aggregate_chunks.run([result], str(target_date), log.id)
        return {"report_date": str(target_date), "mode": "sequential",
                "dispatched_chunks": 1, "job_log_id": log.id}

    # --- Parallel path (the real Requirement 4 implementation) ---------------
    chunks = list(_chunked(order_ids, chunk_size))
    logger.info("Dispatching %d chunks of <=%d orders each", len(chunks), chunk_size)

    # A `chord` = group(map tasks) | callback(reduce task).
    # Celery routes the map tasks to whatever workers are available and only
    # invokes the callback after ALL of them have returned successfully.
    header = [process_chunk.s(c) for c in chunks]
    callback = aggregate_chunks.s(str(target_date), log.id)
    async_result = chord(header)(callback)

    return {
        "report_date": str(target_date),
        "mode": "chunked",
        "dispatched_chunks": len(chunks),
        "chunk_size": chunk_size,
        "job_log_id": log.id,
        "celery_task_id": async_result.id,
    }


# -----------------------------------------------------------------------------
# Bonus async task — useful for Requirement 3 (Asynchronous Queues) too
# -----------------------------------------------------------------------------
@shared_task
def send_order_notification(order_id: int) -> str:
    """Stub for emailing/notifying the customer outside the request cycle.
    Kept here so the team can plug in a real email/SMS gateway later."""
    logger.info("send_order_notification: order %s", order_id)
    return f"notified:{order_id}"
