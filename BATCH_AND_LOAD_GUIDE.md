# Batch Processing & Load Distribution — Run & Test Guide
**Role:** Batch, Load Balancing & Testing Engineer
**Covers:** Requirement 4 (Batch Processing) + Requirement 5 (Load Distribution)

---

## 0. What this delivers

| Requirement | File | What it does |
|---|---|---|
| 4 — Batch Processing | `products/tasks.py` | Celery `chord` that splits daily orders into chunks, processes them in parallel workers, then aggregates into `DailySalesReport`. |
| 4 — Job tracking | `products/models.py` (`BatchJobLog`, `DailySalesReport`) | Persists every run + final report, so the grader can verify results in Django Admin. |
| 4 — Trigger CLI | `products/management/commands/run_daily_batch.py` | `python manage.py run_daily_batch …` |
| 4 — Trigger API | `POST /api/batch/run/` | Kick off the batch from any HTTP client. |
| 5 — Load simulator | `products/load_balancer.py` | Threaded virtual servers + 4 dispatch strategies + metrics. |
| 5 — Simulator CLI | `products/management/commands/simulate_load.py` | `python manage.py simulate_load …` |
| 5 — Simulator API | `GET /api/load/simulate/` | Run the comparison from HTTP. |
| Glue | `ecommerce_project/celery.py`, `settings.py` (CELERY_*) | Celery + Redis wiring. |
| Seed data | `products/management/commands/seed_orders.py` | Creates fake orders for the demo. |

---

## 1. One-time setup

### 1.1 Install Python packages
```bash
pip install -r requirements-batch.txt
# (celery, redis, django-celery-beat, django-celery-results)
```

### 1.2 Install & start Redis
- **Windows:** install Memurai or use WSL → `sudo apt install redis-server && redis-server`.
- **Mac:** `brew install redis && brew services start redis`.
- **Linux:** `sudo apt install redis-server && sudo systemctl start redis`.

Verify: `redis-cli ping` should print `PONG`.

### 1.3 Migrate the new tables
```bash
python manage.py migrate
```
This creates `products_dailysalesreport`, `products_batchjoblog`, plus the
`django_celery_beat_*` tables.

### 1.4 Seed some orders so there's something to batch
```bash
python manage.py seed_orders --count 2000 --date 2026-05-14
```

---

## 2. Running Requirement 4 (Batch Processing)

You need TWO terminals — one for the Django dev server, one for the Celery worker.

### Terminal A — Django
```bash
python manage.py runserver
```

### Terminal B — Celery worker (the parallel workhorse)
```bash
celery -A ecommerce_project worker --loglevel=info --concurrency=4
```
`--concurrency=4` = 4 worker processes. This is the "parallelism" knob;
change it to 1 for a baseline run, then to 4/8 to show speed-up.

### 2.1 Trigger from CLI (easiest for a demo)
```bash
# Parallel run (chunks, default)
python manage.py run_daily_batch --date 2026-05-14 --chunk-size 200 --sync

# Sequential baseline — for the speed-up number
python manage.py run_daily_batch --date 2026-05-14 --mode sequential --sync
```
`--sync` polls `BatchJobLog` and prints the final duration. Compare both
durations to compute speed-up = `sequential_duration / chunked_duration`.

### 2.2 Trigger from API
```bash
curl -X POST http://127.0.0.1:8000/api/batch/run/ \
     -H 'Content-Type: application/json' \
     -d '{"date":"2026-05-14","chunk_size":200,"mode":"chunked"}'
```
Response:
```json
{ "message": "Batch job dispatched",
  "celery_task_id": "5b…", "params": {…} }
```

### 2.3 Inspect what happened
```bash
# The final report (one row per day)
curl 'http://127.0.0.1:8000/api/batch/report/?date=2026-05-14'

# The run log (includes per-chunk timings — great for the report)
curl 'http://127.0.0.1:8000/api/batch/status/1/'
```
Or open Django Admin at `http://127.0.0.1:8000/admin/` → *Daily Sales
Reports* / *Batch Job Logs*.

### 2.4 What to look at in `BatchJobLog.metadata` (the talking points)
- `num_chunks` — how the data was split.
- `chunk_timings_sec` — per-chunk wall time. **The maximum tells you the
  parallel wall time;** the **sum** tells you the would-be sequential time.
- The ratio `sum_chunk_time / max_chunk_time` ≈ ideal speed-up, bounded
  above by `--concurrency`.

---

## 3. Running Requirement 5 (Load Distribution)

No external services needed — pure Python.

### 3.1 Quick comparison of all 4 strategies
```bash
python manage.py simulate_load --servers 4 --requests 300
```
Sample output:
```
Strategy                Wall(s)       RPS  AvgLat(ms)   P50   Max   Stdev
------------------------------------------------------------------------------------
round_robin              3.78    79.40       49.95   49.98 75.12   0.00
random                   3.81    78.74       49.91   49.99 76.02   8.66
least_connections        3.62    82.87       49.55   49.84 73.91   1.41
weighted_round_robin     3.65    82.20       49.62   49.91 74.30  15.62
```

### 3.2 Single-strategy mode
```bash
python manage.py simulate_load --strategy least_connections --requests 500
```

### 3.3 From the API
```bash
curl 'http://127.0.0.1:8000/api/load/simulate/?strategy=all&servers=4&requests=300'
```

### 3.4 How to read the metrics (for your defense)

- **Wall(s)** — total time to drain the request queue. Lower = better
  parallel utilization of the fleet.
- **AvgLat / P50 / Max** — per-request response time. `Max` exposes
  outliers from unlucky scheduling.
- **Stdev (fairness_stdev)** — standard deviation of per-server request
  counts. `0` means perfectly even distribution (only Round Robin
  achieves this when total requests is divisible by N). High values
  with **Weighted RR are EXPECTED** because heavier servers should get
  more requests.
- **per_server_counts** — `{S1: 75, S2: 75, S3: 75, S4: 75}` proves
  the strategy actually does what we claim.

### 3.5 Why each strategy?

| Strategy | When to use | Trade-off |
|---|---|---|
| Round Robin | All servers equal, all requests equal | Blind to load → slow server becomes a bottleneck. |
| Random | Stateless, easy to scale, "good enough" for many small requests | High variance for small N. |
| Least Connections | Heterogeneous request cost — our checkout vs. listing | O(N) scan per dispatch; needs a shared counter. |
| Weighted RR | Mixed-power fleet (one big server, two small) | Doesn't adapt at runtime to actual load. |

The defense argument for our e-commerce system: **Least Connections**
is the right default because cart/checkout latency varies a lot, and we
can't pretend all requests cost the same.

---

## 4. How to TEST your part end-to-end

### 4.1 Smoke test (60 seconds)
1. `redis-cli ping` → `PONG`
2. `python manage.py migrate` → no errors
3. `python manage.py seed_orders --count 100` → "Created 100 orders…"
4. In Terminal B: `celery -A ecommerce_project worker -l info` → starts
5. In Terminal A: `python manage.py run_daily_batch --sync`
   → ends with `Final: status=SUCCESS, duration=…s, …`
6. `python manage.py simulate_load` → prints comparison table

If all six pass, your code works.

### 4.2 Manual correctness check
```bash
# Pre-batch: total revenue from raw orders
python manage.py shell -c "
from products.models import Order;
from datetime import date;
qs = Order.objects.filter(created_at__date=date(2026,5,14));
print('orders:', qs.count(),
      'revenue:', sum(o.total_price for o in qs))"

# Post-batch: what the report says
curl 'http://127.0.0.1:8000/api/batch/report/?date=2026-05-14'
```
The numbers must match. They will, because each chunk operates on a
disjoint slice of order IDs and the reduce step is wrapped in
`transaction.atomic`.

### 4.3 Speed-up measurement (for Requirement 10 — Benchmarking)
```bash
# Baseline
python manage.py run_daily_batch --date 2026-05-14 --mode sequential --sync

# Parallel with different chunk sizes / concurrencies
python manage.py run_daily_batch --date 2026-05-14 --chunk-size 100  --sync
python manage.py run_daily_batch --date 2026-05-14 --chunk-size 500  --sync
```
Then `SELECT mode, chunk_size, duration_seconds FROM products_batchjoblog
ORDER BY started_at DESC;` and plot duration vs. concurrency.

### 4.4 Race-condition check (Requirement 1 cross-cutting)
Fire the same batch twice in parallel:
```bash
python manage.py run_daily_batch --date 2026-05-14 &
python manage.py run_daily_batch --date 2026-05-14 &
wait
```
Both should succeed; the final `DailySalesReport` for that date should
still hold the correct totals (no duplicate rows — guaranteed by the
`unique=True` constraint on `report_date` + `update_or_create`).

### 4.5 Load balancer assertions (programmatic)
You can write a tiny shell test:
```bash
python manage.py simulate_load --strategy round_robin --requests 200 --json \
  | python -c "
import json, sys
d = json.load(sys.stdin)[0]
counts = list(d['per_server_counts'].values())
assert max(counts) - min(counts) <= 1, 'RR should be fair!'
print('OK, RR fairness:', counts)
"
```

### 4.6 What to demo to your group / instructor (3-minute script)
1. **Show the architecture diagram** (talk about `chord` map-reduce).
2. Start Redis + Celery worker with `--concurrency=4`.
3. Run `seed_orders --count 5000`.
4. Run `run_daily_batch --mode sequential --sync` → note duration (say 12s).
5. Run `run_daily_batch --chunk-size 200 --sync` → note duration (say 4s).
6. Open Django Admin → BatchJobLog → show the two rows, point to
   `metadata.chunk_timings_sec` and the `max` vs `sum` ratio.
7. Run `simulate_load` → walk through the comparison table.

---

## 5. Files you should mention in the design document (AOP/Architecture)

- `ecommerce_project/celery.py` — Celery app + broker choice.
- `products/tasks.py` — the map-reduce pattern via `chord`.
- `products/models.py` — `DailySalesReport`, `BatchJobLog`.
- `products/load_balancer.py` — Strategy pattern (each strategy is its
  own class) and ThreadPool-style server simulation.

For the AOP/performance-monitoring requirement, the comments in
`process_chunk` and `aggregate_chunks` mark the *join points* where you
could later wrap a Python decorator (e.g. `@measure_latency`) without
touching the business logic. That's the AOP story.

---

## 6. Common troubleshooting

| Symptom | Fix |
|---|---|
| `Connection refused` on port 6379 | Redis not running. `redis-server` or start the service. |
| `KeyError: 'CELERY_BROKER_URL'` | Make sure `from .celery import app as celery_app` is in `ecommerce_project/__init__.py`. |
| Tasks are dispatched but nothing runs | The Celery worker isn't started, or you started it pointing at the wrong app name. Must be `celery -A ecommerce_project worker`. |
| Migrations conflict | Delete `__pycache__` and rerun `python manage.py migrate products`. |
| `django_celery_beat` not found | `pip install django-celery-beat` and re-run migrate. |
| Numbers don't match between manual count and batch | Check the time zone. The batch slices by `created_at` in **server local time**; if your test creates orders at midnight there can be off-by-one days. |
