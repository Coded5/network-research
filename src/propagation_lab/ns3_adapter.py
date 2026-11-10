"""The sole boundary between Python data and ns-3 C++ objects."""

import hashlib
import math
import os
import sys
from importlib.metadata import version
from pathlib import Path

from propagation_lab.scenario import Friis, Obstacle, Propagation, Transmitter

NS3_VERSION = "3.44"
NS3_COMMIT = "43dce6710b8df69685e3479c1d33a571dda714ea"
ROOT = Path(__file__).resolve().parents[2]


def native_source_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(directory)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


class Ns3Adapter:
    def __init__(self, seed: int):
        import json

        source = ROOT / "vendor" / "ns-3"
        manifest = source / "build" / "propagation-lab-build.json"
        if not manifest.is_file():
            raise RuntimeError("Custom ns-3 build is missing. Run make ns3 first.")
        try:
            self.build_info = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError("Cannot read custom ns-3 build manifest. Run make ns3.") from exc
        if (
            self.build_info.get("ns3_commit") != NS3_COMMIT
            or self.build_info.get("native_sha256") != native_source_digest(ROOT / "native")
            or self.build_info.get("python_version")
            != f"{sys.version_info.major}.{sys.version_info.minor}"
        ):
            raise RuntimeError(
                "Custom ns-3 build is stale or uses another Python ABI. Run make ns3."
            )
        bindings = source / "build" / "bindings" / "python"
        existing = sys.modules.get("ns")
        if existing and Path(existing.__file__).resolve() != bindings / "ns" / "__init__.py":
            raise RuntimeError("Another ns-3 installation is loaded. Start a fresh process.")
        os.environ.setdefault("EXTRA_CLING_ARGS", self.build_info["cling_args"])
        if str(bindings) not in sys.path:
            sys.path.insert(0, str(bindings))
        try:
            import cppyy  # noqa: F401
            from ns import ns
            ns.ObstaclePropagationLossModel.GetTypeId()
        except (ImportError, RuntimeError, AttributeError) as exc:
            raise RuntimeError(
                "Cannot load custom ns-3. Run make ns3 using Python 3.12 and compatible "
                "compiler headers; see README.md."
            ) from exc
        self.ns = ns
        ns.RngSeedManager.SetSeed(seed)
        self.version = self.build_info["ns3_version"]
        self.cppyy_version = version("cppyy")

    def channel(self, tx: Transmitter, propagation: Propagation,
                obstacles: list[Obstacle] | None = None):
        ns = self.ns
        if isinstance(propagation, Friis):
            model = ns.CreateObject[ns.FriisPropagationLossModel]()
            attributes = {
                "Frequency": tx.frequency_hz,
                "SystemLoss": propagation.parameters.system_loss,
                "MinLoss": 0.0,
            }
        else:
            model = ns.CreateObject[ns.LogDistancePropagationLossModel]()
            attributes = {
                "Exponent": propagation.parameters.exponent,
                "ReferenceDistance": propagation.parameters.reference_distance_m,
                "ReferenceLoss": propagation.parameters.reference_loss_db,
            }
        for key, value in attributes.items():
            model.SetAttribute(key, ns.DoubleValue(value))
        if obstacles:
            base = model
            model = ns.CreateObject[ns.ObstaclePropagationLossModel]()
            model.SetBaseModel(base)
            for obstacle in obstacles:
                model.AddObstacle(
                    obstacle.kind == "rectangle", ns.Vector(*obstacle.start, 0),
                    ns.Vector(*obstacle.end, 0), obstacle.height_m, obstacle.blocks,
                    obstacle.attenuation_db,
                    -1 if obstacle.reflection_loss_db is None else obstacle.reflection_loss_db,
                )
            attributes = {**attributes, "Wrapper": "ns3::ObstaclePropagationLossModel"}
        source = ns.CreateObject[ns.ConstantPositionMobilityModel]()
        target = ns.CreateObject[ns.ConstantPositionMobilityModel]()
        source.SetPosition(ns.Vector(*tx.position))

        def rx_power(position, include_paths=False):
            target.SetPosition(ns.Vector(*position))
            power = float(model.CalcRxPower(tx.power_dbm + tx.antenna_gain_dbi, source, target))
            if not math.isfinite(power) and not (obstacles and power == -math.inf):
                raise ValueError(
                    "ns-3 returned nonfinite power; check model parameters and frequency"
                )
            if not include_paths:
                return power
            paths = []
            if obstacles:
                for path in model.GetPaths(tx.power_dbm + tx.antenna_gain_dbi, source, target):
                    reflected = path.kind == "reflected"
                    paths.append({
                        "kind": str(path.kind),
                        "obstacle_id": obstacles[path.obstacleIndex].id if reflected else "",
                        "distance_m": float(path.distanceM),
                        "rx_power_dbm": float(path.rxPowerDbm),
                        "reflection_loss_db": float(path.reflectionLossDb),
                        "transmission_loss_db": float(path.transmissionLossDb),
                        "bounce_x_m": float(path.bounce.x) if reflected else None,
                        "bounce_y_m": float(path.bounce.y) if reflected else None,
                        "bounce_z_m": float(path.bounce.z) if reflected else None,
                    })
            else:
                paths.append({
                    "kind": "direct", "obstacle_id": "",
                    "distance_m": math.dist(tx.position, position), "rx_power_dbm": power,
                    "reflection_loss_db": 0.0, "transmission_loss_db": 0.0,
                    "bounce_x_m": None, "bounce_y_m": None, "bounce_z_m": None,
                })
            return power, paths

        return rx_power, attributes

    def close(self):
        self.ns.Simulator.Destroy()
