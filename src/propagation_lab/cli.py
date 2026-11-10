"""Run a saved scenario or verify the pinned ns-3 binding from a terminal."""

import argparse
import math
from datetime import datetime, timezone
from pathlib import Path

from propagation_lab.engine import run_isolated
from propagation_lab.export import export_results
from propagation_lab.scenario import Environment, Receiver, Scenario, Transmitter, default_scenario


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scenario", nargs="?", type=Path, help="Scenario JSON (default: example layout)"
    )
    parser.add_argument(
        "--output", type=Path, help="New result directory; existing paths are not replaced"
    )
    parser.add_argument("--compare", action="store_true", help="Also evaluate the other loss model")
    parser.add_argument(
        "--smoke", action="store_true", help="Check real ns-3 Friis against a reference"
    )
    args = parser.parse_args()
    try:
        if args.smoke:
            scenario = Scenario(
                environment=Environment(width_m=100, height_m=1),
                transmitters=[Transmitter(id="tx_1", position=(0, 0, 0))],
                receivers=[Receiver(id="rx_1", position=(100, 0, 0))],
            )
        elif args.scenario:
            scenario = Scenario.model_validate_json(args.scenario.read_text(encoding="utf-8"))
        else:
            scenario = default_scenario()
        result = run_isolated(scenario, compare=args.compare)
        print(f"ns-3 {result.metadata['ns3_version']} · static propagation model evaluation")
        print(result.links.to_string(index=False))
        if args.smoke:
            reference = 20 - 20 * math.log10(4 * math.pi * 100 * 2.4e9 / 299792458)
            actual = result.links.iloc[0].rx_power_dbm
            if abs(actual - reference) > 1e-6:
                raise RuntimeError(f"Friis mismatch: ns-3 {actual}, reference {reference}")
            print(f"Friis reference passed (tolerance 1e-6 dB): {actual:.9f} dBm")
        else:
            output = args.output or Path("results") / datetime.now(timezone.utc).strftime(
                "scenario_%Y%m%dT%H%M%S_%fZ"
            )
            print(f"Results: {export_results(result, output)}")
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
