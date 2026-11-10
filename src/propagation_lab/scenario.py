"""Validated, versioned scenario contract shared by the CLI and editor."""

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Positive = Annotated[float, Field(gt=0)]
Height = Annotated[float, Field(ge=0, le=10000)]
Position = tuple[float, float, Height]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_default=True)


class Environment(Model):
    width_m: Positive = 500
    height_m: Positive = 500


class Transmitter(Model):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str = Field(default="", max_length=120)
    position: Position
    frequency_hz: float = Field(default=2.4e9, gt=0, le=1e12)
    power_dbm: float = Field(default=20, ge=-100, le=100)
    antenna_gain_dbi: float = Field(default=0, ge=-100, le=100)


class Receiver(Model):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str = Field(default="", max_length=120)
    position: Position
    sensitivity_dbm: float = Field(default=-90, ge=-200, le=100)


class FriisParameters(Model):
    system_loss: float = Field(default=1, ge=1)


class LogDistanceParameters(Model):
    exponent: float = Field(default=3, gt=0, le=10)
    reference_distance_m: Positive = 1
    reference_loss_db: float = Field(default=46.6777, ge=0, le=300)


class Friis(Model):
    model: Literal["friis"] = "friis"
    parameters: FriisParameters = Field(default_factory=FriisParameters)


class LogDistance(Model):
    model: Literal["log_distance"] = "log_distance"
    parameters: LogDistanceParameters = Field(default_factory=LogDistanceParameters)


Propagation = Annotated[Friis | LogDistance, Field(discriminator="model")]


class Sampling(Model):
    resolution_m: Positive = 5
    receiver_height_m: Height = 1.5


class Simulation(Model):
    duration_s: Positive = 1
    seed: int = Field(default=42, ge=1, le=2**32 - 1)


class Scenario(Model):
    schema_version: Literal["1.0"] = "1.0"
    name: str = Field(default="Free Space Propagation", min_length=1, max_length=120)
    environment: Environment = Field(default_factory=Environment)
    transmitters: list[Transmitter] = Field(default_factory=list, max_length=32)
    receivers: list[Receiver] = Field(default_factory=list, max_length=500)
    propagation: Propagation = Field(default_factory=Friis)
    sampling: Sampling = Field(default_factory=Sampling)
    simulation: Simulation = Field(default_factory=Simulation)

    @model_validator(mode="after")
    def validate_layout(self):
        nodes = [*self.transmitters, *self.receivers]
        if len({node.id for node in nodes}) != len(nodes):
            raise ValueError("Node IDs must be unique across transmitters and receivers")
        for node in nodes:
            x, y, _ = node.position
            if not (0 <= x <= self.environment.width_m and 0 <= y <= self.environment.height_m):
                raise ValueError(f"Node {node.id} lies outside the map")
        ratios = [
            self.environment.width_m / self.sampling.resolution_m,
            self.environment.height_m / self.sampling.resolution_m,
        ]
        if any(not math.isfinite(ratio) or ratio > 499_999 for ratio in ratios):
            raise ValueError("Grid exceeds 500,000 TX-cell evaluations; increase grid spacing")
        nx, ny = (math.ceil(ratio) + 1 for ratio in ratios)
        if nx * ny * max(1, len(self.transmitters)) > 500_000:
            raise ValueError("Grid exceeds 500,000 TX-cell evaluations; increase grid spacing")
        return self

    def require_runnable(self):
        if not self.transmitters:
            raise ValueError("Add at least one transmitter before running")


def default_scenario() -> Scenario:
    return Scenario(
        transmitters=[Transmitter(id="tx_1", position=(100, 250, 10))],
        receivers=[
            Receiver(id="rx_1", position=(200, 250, 1.5)),
            Receiver(id="rx_2", position=(400, 250, 1.5)),
        ],
    )
