import math

import pytest
from pydantic import ValidationError

from propagation_lab.scenario import Scenario, default_scenario


@pytest.mark.parametrize(
    "position",
    [(0, 0, 0), (500, 500, 10000), (-1, 0, 1), (0, 501, 1), (0, 0, -1), (math.inf, 0, 1)],
)
def test_position_validation(position):
    data = default_scenario().model_dump()
    data["transmitters"][0]["position"] = position
    if position[0] == 500:
        data["environment"] = {"width_m": 500, "height_m": 500}
    if position[1] == 501:
        data["environment"] = {"width_m": 500, "height_m": 500}
    if position[0] < 0 or position[1] > 500 or position[2] < 0 or not math.isfinite(position[0]):
        with pytest.raises(ValidationError):
            Scenario.model_validate(data)
    else:
        Scenario.model_validate(data)


@pytest.mark.parametrize(
    "field,value",
    [("id", "bad id"), ("frequency_hz", 0), ("frequency_hz", math.inf),
     ("power_dbm", 101), ("power_dbm", math.nan)],
)
def test_transmitter_validation(field, value):
    data = default_scenario().model_dump()
    data["transmitters"][0][field] = value
    with pytest.raises(ValidationError):
        Scenario.model_validate(data)


def test_duplicate_ids_across_roles_and_extra_fields_rejected():
    data = default_scenario().model_dump()
    data["receivers"][0]["id"] = data["transmitters"][0]["id"]
    with pytest.raises(ValidationError, match="unique"):
        Scenario.model_validate(data)
    data = default_scenario().model_dump()
    data["propagation"]["parameters"]["future"] = 1
    with pytest.raises(ValidationError):
        Scenario.model_validate(data)


def test_schema_version_and_import_export_roundtrip_all_fields():
    scenario = default_scenario().model_copy(update={"name": "roundtrip"})
    data = scenario.model_dump(mode="json")
    data["schema_version"] = "2.0"
    with pytest.raises(ValidationError):
        Scenario.model_validate(data)
    restored = Scenario.model_validate_json(scenario.model_dump_json())
    assert restored.model_dump() == scenario.model_dump()
    assert restored.transmitters[0].frequency_hz == scenario.transmitters[0].frequency_hz
    assert restored.propagation.parameters.model_dump() == (
        scenario.propagation.parameters.model_dump()
    )


def test_nondefault_log_distance_scenario_roundtrip():
    data = default_scenario().model_dump()
    data.update(
        name="Calibrated experiment",
        propagation={
            "model": "log_distance",
            "parameters": {
                "exponent": 3.7, "reference_distance_m": 2.5, "reference_loss_db": 53.4
            },
        },
        sampling={"resolution_m": 12.5, "receiver_height_m": 2.1},
        simulation={"duration_s": 4.5, "seed": 17},
    )
    data["transmitters"][0].update(
        name="Radio A", frequency_hz=5.8e9, power_dbm=13.5, antenna_gain_dbi=2.5
    )
    data["receivers"][0].update(name="Probe A", sensitivity_dbm=-84.5)
    scenario = Scenario.model_validate(data)
    assert Scenario.model_validate_json(scenario.model_dump_json()).model_dump() == (
        scenario.model_dump()
    )


@pytest.mark.parametrize("resolution", [0, -1, math.nan, 1e-300])
def test_invalid_or_excessive_sampling_rejected(resolution):
    data = default_scenario().model_dump()
    data["sampling"]["resolution_m"] = resolution
    with pytest.raises(ValidationError):
        Scenario.model_validate(data)


def test_empty_editor_scenario_cannot_run():
    with pytest.raises(ValueError, match="transmitter"):
        Scenario().require_runnable()
