"""Illustrative capacity arithmetic; no network calls or performance claims."""

import argparse
import json
import math
from pathlib import Path


def calculate(config):
    positive = ("month_days", "outbound_kbit_per_active_player", "overhead_factor",
                "hypothetical_measured_node_ccu")
    for key in positive:
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{key} must be positive and finite")
    for key in ("average_to_peak_ratio", "admission_fraction"):
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 1:
            raise ValueError(f"{key} must be in (0, 1]")
    reserve = config["failure_reserve_nodes"]
    if type(reserve) is not int or reserve < 0:
        raise ValueError("failure_reserve_nodes must be a nonnegative integer")
    safe_cap = math.floor(config["hypothetical_measured_node_ccu"] * config["admission_fraction"])
    if safe_cap < 1:
        raise ValueError("safe node capacity must be at least one")
    prices = config["prices_thb"]
    for key, value in prices.items():
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
            raise ValueError(f"price {key} must be null or nonnegative and finite")
    required_prices = ("world_node_per_month", "fixed_services_per_month", "realtime_egress_per_gb")
    priced = all(prices.get(key) is not None for key in required_prices)
    included = prices.get("included_realtime_egress_gb", 0)
    if included is None:
        raise ValueError("included_realtime_egress_gb must be numeric")
    seconds = config["month_days"] * 86400
    rows = []
    for peak in config["scenarios_peak_ccu"]:
        if type(peak) is not int or peak <= 0:
            raise ValueError("peak CCU must be a positive integer")
        average = peak * config["average_to_peak_ratio"]
        wire_kbit = config["outbound_kbit_per_active_player"] * config["overhead_factor"]
        gb = average * wire_kbit * 1000 / 8 * seconds / 1e9
        nodes = math.ceil(peak / safe_cap) + reserve
        cost = None
        if priced:
            cost = (nodes * prices["world_node_per_month"] + prices["fixed_services_per_month"]
                    + max(0, gb - included) * prices["realtime_egress_per_gb"])
        rows.append({"peak_ccu": peak, "average_ccu": average,
                     "peak_outbound_mbps": round(peak * wire_kbit / 1000, 3),
                     "monthly_realtime_outbound_gb": round(gb, 3),
                     "safe_ccu_per_world_node": safe_cap,
                     "world_nodes_including_reserve": nodes,
                     "partial_monthly_cost_thb": None if cost is None else round(cost, 2)})
    return {"status": "estimate_not_benchmark", "prices_complete": priced, "scenarios": rows}


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=root / "planning/capacity-assumptions.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = calculate(json.loads(args.input.read_text(encoding="utf-8")))
    serialized = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
