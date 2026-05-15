"""
Run the daily sales batch from the command line.

Usage:
    python manage.py run_daily_batch                    # yesterday, parallel
    python manage.py run_daily_batch --date 2026-05-14  # specific day
    python manage.py run_daily_batch --mode sequential  # baseline for speed-up
    python manage.py run_daily_batch --chunk-size 50    # tune throughput
    python manage.py run_daily_batch --sync             # block until done

`--sync` is the most useful flag for class demos: instead of returning an
AsyncResult ID, it WAITS for the chord to finish so the user sees the final
numbers on stdout in one go.
"""
import time
from django.core.management.base import BaseCommand
from products.tasks import run_daily_sales_batch
from products.models import BatchJobLog


class Command(BaseCommand):
    help = "Run the daily sales batch (Requirement 4)."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, default=None,
                            help="ISO date YYYY-MM-DD (default: yesterday)")
        parser.add_argument("--chunk-size", type=int, default=200)
        parser.add_argument("--mode", choices=["chunked", "sequential"], default="chunked")
        parser.add_argument("--sync", action="store_true",
                            help="Wait for the chord to finish before returning")
        parser.add_argument("--local", action="store_true",
                            help="Run the task in-process (no Celery worker needed)")

    def handle(self, *args, **opts):
        kwargs = {
            "report_date_str": opts["date"],
            "chunk_size": opts["chunk_size"],
            "mode": opts["mode"],
        }

        if opts["local"]:
            # `.apply()` runs the task synchronously IN THIS PROCESS — handy
            # when Redis isn't running and you just want to test the logic.
            self.stdout.write(self.style.NOTICE("Running locally (no Celery worker)..."))
            res = run_daily_sales_batch.apply(kwargs=kwargs).get()
            self.stdout.write(self.style.SUCCESS(f"Done: {res}"))
            return

        async_res = run_daily_sales_batch.delay(**kwargs)
        self.stdout.write(self.style.NOTICE(
            f"Dispatched to Celery. task_id={async_res.id}"
        ))

        if not opts["sync"]:
            return

        # Poll the BatchJobLog row that was just created by the dispatcher.
        # We don't `async_res.get()` because the chord callback is what
        # actually finishes the work, not the dispatcher task itself.
        time.sleep(0.5)
        log_id = None
        for _ in range(40):
            log = (BatchJobLog.objects
                   .filter(job_name="daily_sales_batch")
                   .order_by("-started_at").first())
            if log:
                log_id = log.id
                break
            time.sleep(0.25)

        if not log_id:
            self.stderr.write("Could not find BatchJobLog row — is the worker running?")
            return

        self.stdout.write(f"Watching BatchJobLog id={log_id} ...")
        while True:
            log.refresh_from_db()
            self.stdout.write(f"  status={log.status}  elapsed={log.duration_seconds}s")
            if log.status in ("SUCCESS", "FAILED"):
                break
            time.sleep(1)

        self.stdout.write(self.style.SUCCESS(
            f"Final: status={log.status}, duration={log.duration_seconds}s, "
            f"records={log.total_records}, metadata={log.metadata}"
        ))
