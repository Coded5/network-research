"""Grid evaluation and isolated execution. No packet events are scheduled."""

import math
import pickle
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from propagation_lab.ns3_adapter import Ns3Adapter
from propagation_lab.scenario import Friis, LogDistance, Scenario

COVERAGE_COLUMNS = [
    "model", "tx_id", "x_m", "y_m", "z_m", "distance_m", "rx_power_dbm", "path_loss_db"
]
LINK_COLUMNS = [
    "model", "tx_id", "rx_id", "distance_m", "rx_power_dbm", "path_loss_db", "link_margin_db"
]
CURVE_COLUMNS = ["model", "tx_id", "distance_m", "rx_power_dbm", "path_loss_db"]


@dataclass
class SimulationResult:
    scenario: Scenario
    metadata: dict
    coverage: pd.DataFrame
    links: pd.DataFrame
    curves: pd.DataFrame


def sample_axis(length: float, resolution: float) -> np.ndarray:
    """Include both boundaries, with a shorter last interval when necessary."""
    return np.append(np.arange(math.ceil(length / resolution)) * resolution, length)


def run(scenario: Scenario, compare: bool = False) -> SimulationResult:
    scenario = Scenario.model_validate(scenario.model_dump())
    scenario.require_runnable()
    started = datetime.now(timezone.utc).isoformat()
    xs = sample_axis(scenario.environment.width_m, scenario.sampling.resolution_m)
    ys = sample_axis(scenario.environment.height_m, scenario.sampling.resolution_m)
    models = [scenario.propagation]
    if compare:
        models.append(LogDistance() if isinstance(scenario.propagation, Friis) else Friis())
    coverage, links, curves, model_metadata = [], [], [], {}
    adapter = Ns3Adapter(scenario.simulation.seed)
    try:
        for propagation in models:
            model_name = propagation.model
            tx_attributes = {}
            for tx in scenario.transmitters:
                power_at, attributes = adapter.channel(tx, propagation)
                tx_attributes[tx.id] = attributes
                effective_power = tx.power_dbm + tx.antenna_gain_dbi
                for y in ys:
                    for x in xs:
                        position = (float(x), float(y), scenario.sampling.receiver_height_m)
                        power = power_at(position)
                        coverage.append((
                            model_name, tx.id, *position, math.dist(tx.position, position),
                            power, effective_power - power,
                        ))
                for rx in scenario.receivers:
                    power = power_at(rx.position)
                    links.append((
                        model_name, tx.id, rx.id, math.dist(tx.position, rx.position),
                        power, effective_power - power, power - rx.sensitivity_dbm,
                    ))
                max_distance = max(1, math.hypot(
                    scenario.environment.width_m, scenario.environment.height_m
                ))
                for distance in np.geomspace(1, max_distance, 120):
                    # Equal antenna heights make the curve's horizontal offset a true 3D distance.
                    position = (tx.position[0] + float(distance), tx.position[1], tx.position[2])
                    power = power_at(position)
                    curves.append((
                        model_name, tx.id, float(distance), power, effective_power - power,
                    ))
            model_metadata[model_name] = {
                "parameters": propagation.parameters.model_dump(),
                "attributes_by_tx": tx_attributes,
            }
        metadata = {
            "application_version": "0.1.0",
            "ns3_version": adapter.version,
            "cppyy_version": adapter.cppyy_version,
            "selected_model": scenario.propagation.model,
            "models": model_metadata,
            "seed": scenario.simulation.seed,
            "duration_s": scenario.simulation.duration_s,
            "simulation_mode": "static_propagation_model_evaluation",
            "started_at": started,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "grid_shape": [len(ys), len(xs)],
            "receiver_gain_dbi": 0,
            "notes": [
                "No packet simulation, interference, or waveforms.",
                "Duration and seed do not affect these stationary deterministic models.",
                "Maximum RSS is not combined RF power.",
                "Log-distance reference loss is explicit, not inferred from frequency.",
                "Friis MinLoss is 0 dB; near-field values are not physically reliable.",
                "ns-3 3.44 log-distance applies reference loss at/below reference distance.",
            ],
        }
        return SimulationResult(
            scenario, metadata,
            pd.DataFrame(coverage, columns=COVERAGE_COLUMNS),
            pd.DataFrame(links, columns=LINK_COLUMNS),
            pd.DataFrame(curves, columns=CURVE_COLUMNS),
        )
    finally:
        adapter.close()


def run_isolated(scenario: Scenario, compare: bool = False) -> SimulationResult:
    """Discard all C++ state after each run; a binding crash cannot kill the UI."""
    scenario = Scenario.model_validate(scenario.model_dump())
    scenario.require_runnable()
    with tempfile.TemporaryDirectory(prefix="propagation-lab-") as directory:
        source, target = Path(directory) / "scenario.json", Path(directory) / "result.pickle"
        source.write_text(scenario.model_dump_json(), encoding="utf-8")
        command = [sys.executable, "-m", "propagation_lab.worker", str(source), str(target)]
        if compare:
            command.append("--compare")
        try:
            process = subprocess.run(command, capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Simulation exceeded 180 seconds; increase grid spacing") from exc
        if process.returncode != 0:
            raise RuntimeError(
                f"ns-3 worker failed (exit {process.returncode}). Check the pinned environment "
                f"and compiler headers described in README.md.\n{process.stderr[-4000:]}"
            )
        # Only deserialize our own worker's output in this private temporary directory.
        return pickle.loads(target.read_bytes())
