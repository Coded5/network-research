"""The sole boundary between Python data and ns-3 C++ objects."""

import math
from importlib.metadata import version

from propagation_lab.scenario import Friis, Propagation, Transmitter


class Ns3Adapter:
    def __init__(self, seed: int):
        try:
            import cppyy  # noqa: F401
            from ns import ns
        except (ImportError, RuntimeError) as exc:
            raise RuntimeError(
                "Cannot load ns-3. Use the pinned Python 3.12 environment; "
                "see README.md for compiler/header compatibility."
            ) from exc
        self.ns = ns
        ns.RngSeedManager.SetSeed(seed)
        self.version = version("ns3")
        self.cppyy_version = version("cppyy")

    def channel(self, tx: Transmitter, propagation: Propagation):
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
        source = ns.CreateObject[ns.ConstantPositionMobilityModel]()
        target = ns.CreateObject[ns.ConstantPositionMobilityModel]()
        source.SetPosition(ns.Vector(*tx.position))

        def rx_power(position):
            target.SetPosition(ns.Vector(*position))
            power = float(model.CalcRxPower(tx.power_dbm + tx.antenna_gain_dbi, source, target))
            if not math.isfinite(power):
                raise ValueError(
                    "ns-3 returned nonfinite power; check model parameters and frequency"
                )
            return power

        return rx_power, attributes

    def close(self):
        self.ns.Simulator.Destroy()
