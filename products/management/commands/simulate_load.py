"""
Run the load-distribution simulator from the command line.

Usage:
    python manage.py simulate_load                              # all strategies
    python manage.py simulate_load --strategy round_robin
    python manage.py simulate_load --servers 6 --requests 500
    python manage.py simulate_load --json                       # raw JSON
"""
import json as _json
from django.core.management.base import BaseCommand
from products.load_balancer import compare_all_strategies, run_simulation, STRATEGIES


class Command(BaseCommand):
    help = "Simulate request distribution across virtual servers (Requirement 5)."

    def add_arguments(self, parser):
        parser.add_argument("--strategy", default="all",
                            choices=list(STRATEGIES) + ["all"])
        parser.add_argument("--servers",  type=int, default=4)
        parser.add_argument("--requests", type=int, default=200)
        parser.add_argument("--json", action="store_true",
                            help="Print raw JSON instead of a pretty table")

    def handle(self, *args, **opts):
        if opts["strategy"] == "all":
            results = compare_all_strategies(
                num_requests=opts["requests"], num_servers=opts["servers"]
            )
        else:
            results = [run_simulation(opts["strategy"],
                                      num_servers=opts["servers"],
                                      num_requests=opts["requests"])]

        if opts["json"]:
            self.stdout.write(_json.dumps(results, indent=2))
            return

        # Pretty comparison table.
        header = ("Strategy", "Wall(s)", "RPS", "AvgLat(ms)", "P50", "Max", "Stdev")
        self.stdout.write(("{:<22}" + "{:>10}" * 6).format(*header))
        self.stdout.write("-" * 84)
        for r in results:
            self.stdout.write(("{:<22}" + "{:>10}" * 6).format(
                r["strategy"],
                r["wall_clock_sec"],
                r["throughput_rps"],
                r["latency_ms"]["avg"],
                r["latency_ms"]["p50"],
                r["latency_ms"]["max"],
                r["fairness_stdev"],
            ))
        self.stdout.write("")
        for r in results:
            self.stdout.write(f"{r['strategy']:<22} per-server counts: {r['per_server_counts']}")
