import math

import pytest
from pydantic import ValidationError

from propagation_lab.engine import run_isolated
from propagation_lab.ns3_adapter import Ns3Adapter
from propagation_lab.scenario import Friis, Obstacle, Scenario, Transmitter, default_scenario


def wall(id="wall", start=(5, -10), end=(5, 10), **kwargs):
    return Obstacle(id=id, start=start, end=end, **kwargs)


def scenario_with(*obstacles):
    data = default_scenario().model_dump()
    data["obstacles"] = [o.model_dump() for o in obstacles]
    return data


def test_schema_upgrade_defaults_and_obstacle_roundtrip():
    data = default_scenario().model_dump(mode="json")
    data["schema_version"] = "1.0"
    upgraded = Scenario.model_validate(data)
    assert upgraded.schema_version == "1.1"
    assert upgraded.obstacles == []
    data["obstacles"] = [wall().model_dump(mode="json")]
    with pytest.raises(ValidationError, match="1.1"):
        Scenario.model_validate(data)

    obstacle = Obstacle(id="wall", start=(1, 2), end=(1, 8))
    assert (obstacle.kind, obstacle.height_m, obstacle.blocks,
            obstacle.attenuation_db, obstacle.reflection_loss_db) == (
        "wall", 15, False, 6, 6,
    )
    data = scenario_with(Obstacle(
        id="glass", name="Glass", kind="rectangle", start=(2, 3), end=(7, 9),
        height_m=12.5, blocks=False, attenuation_db=8, reflection_loss_db=4,
    ))
    restored = Scenario.model_validate_json(Scenario.model_validate(data).model_dump_json())
    assert restored.model_dump() == Scenario.model_validate(data).model_dump()


@pytest.mark.parametrize("change", [
    {"id": "bad id"}, {"start": (math.nan, 0)}, {"start": (math.inf, 0)},
    {"height_m": 0}, {"height_m": 10001}, {"attenuation_db": -1},
    {"attenuation_db": math.inf}, {"reflection_loss_db": -1},
    {"reflection_loss_db": math.nan}, {"start": (1, 1), "end": (1, 1)},
    {"kind": "rectangle", "start": (1, 1), "end": (1, 5)},
    {"kind": "rectangle", "start": (1, 1), "end": (5, 1)},
])
def test_invalid_obstacle_values_rejected(change):
    values = {"id": "wall", "start": (0, 0), "end": (0, 5), **change}
    with pytest.raises(ValidationError):
        Obstacle(**values)


def test_obstacle_ids_material_bounds_map_and_budget():
    with pytest.raises(ValidationError, match="power fractions"):
        Obstacle(id="hot", start=(0, 0), end=(0, 1), attenuation_db=0,
                 reflection_loss_db=0)
    data = scenario_with(wall(id="tx_1", start=(100, 0), end=(100, 5)))
    with pytest.raises(ValidationError, match="unique"):
        Scenario.model_validate(data)
    data = scenario_with(Obstacle(id="out", start=(501, 0), end=(501, 1)))
    with pytest.raises(ValidationError, match="outside"):
        Scenario.model_validate(data)
    data = default_scenario().model_dump()
    data["environment"] = {"width_m": 500, "height_m": 500}
    data["sampling"] = {"resolution_m": 1, "receiver_height_m": 1}
    data["obstacles"] = [wall(id=f"w{i}", start=(i + 1, 0), end=(i + 1, 20),
                              blocks=True, reflection_loss_db=0).model_dump()
                         for i in range(32)]
    with pytest.raises(ValidationError, match="budget"):
        Scenario.model_validate(data)


@pytest.fixture(scope="module")
def adapter():
    instance = Ns3Adapter(123)
    yield instance
    instance.close()


def friis_dbm(tx, distance):
    if distance == 0:
        return tx.power_dbm + tx.antenna_gain_dbi
    fspl = 20 * math.log10(4 * math.pi * distance * tx.frequency_hz / 299792458)
    return tx.power_dbm + tx.antenna_gain_dbi - fspl


def channel(adapter, tx, obstacles=()):
    return adapter.channel(tx, Friis(), list(obstacles))[0]


@pytest.mark.integration
def test_empty_obstacles_baseline_and_zero_distance(adapter):
    tx = Transmitter(id="tx", position=(0, 0, 1))
    plain = adapter.channel(tx, Friis())[0]
    wrapped = channel(adapter, tx)
    for pos in ((10, 0, 1), (3, 4, 1)):
        assert wrapped(pos) == pytest.approx(plain(pos), abs=1e-6)
        assert wrapped(pos) == pytest.approx(friis_dbm(tx, math.dist(tx.position, pos)), abs=1e-6)
    assert wrapped(tx.position) == pytest.approx(tx.power_dbm)


@pytest.mark.integration
def test_wall_crossing_loss_stacks_and_blocking_has_no_path(adapter):
    tx = Transmitter(id="tx", position=(0, 0, 1))
    rx = (10, 0, 1)
    base = channel(adapter, tx)(rx)
    one = wall(start=(5, -2), end=(5, 2), reflection_loss_db=None)
    two = wall(id="two", start=(7, -2), end=(7, 2), attenuation_db=9,
               reflection_loss_db=None)
    assert channel(adapter, tx, [one])(rx) == pytest.approx(base - 6, abs=1e-6)
    assert channel(adapter, tx, [one, two])(rx) == pytest.approx(base - 15, abs=1e-6)
    blocked = wall(blocks=True, reflection_loss_db=None)
    power, paths = channel(adapter, tx, [blocked])(rx, include_paths=True)
    assert power == -math.inf
    assert paths == []


@pytest.mark.integration
def test_reflection_path_geometry_and_incoherent_power_sum(adapter):
    tx = Transmitter(id="tx", position=(1, 2, 1))
    rx = (9, 2, 1)
    reflector = wall(id="mirror", start=(-20, 0), end=(20, 0),
                     reflection_loss_db=3)
    blocker = wall(id="block", start=(5, 1), end=(5, 3), blocks=True,
                   reflection_loss_db=None)
    power, paths = channel(adapter, tx, [reflector, blocker])(rx, include_paths=True)
    assert len(paths) == 1
    path = paths[0]
    assert path["kind"] == "reflected" and path["obstacle_id"] == "mirror"
    assert (path["bounce_x_m"], path["bounce_y_m"], path["bounce_z_m"]) == pytest.approx((5, 0, 1))
    assert path["distance_m"] == pytest.approx(math.sqrt(80))
    assert path["reflection_loss_db"] == 3
    assert power == pytest.approx(friis_dbm(tx, math.sqrt(80)) - 3, abs=1e-6)

    clear, clear_paths = channel(adapter, tx, [reflector])(rx, include_paths=True)
    assert len(clear_paths) == 2
    expected = max(p["rx_power_dbm"] for p in clear_paths) + 10 * math.log10(
        sum(10 ** ((p["rx_power_dbm"] - max(q["rx_power_dbm"] for q in clear_paths)) / 10)
            for p in clear_paths)
    )
    assert clear == pytest.approx(expected, abs=1e-6)


@pytest.mark.integration
@pytest.mark.parametrize("start,end", [
    ((5, -10), (5, 10)), ((-10, 5), (10, 5)), ((0, 0), (10, 10)),
])
def test_wall_orientation_attenuation(adapter, start, end):
    tx = Transmitter(id="tx", position=(0, 0, 1))
    rx = (10, 10, 1)
    obstacle = wall(start=start, end=end, reflection_loss_db=None)
    power = channel(adapter, tx, [obstacle])(rx)
    assert power <= channel(adapter, tx)(rx)


@pytest.mark.integration
def test_rectangle_reflective_face_only_and_leg_occlusion(adapter):
    tx = Transmitter(id="tx", position=(-2, 2, 1))
    rx = (-2, 8, 1)
    rect = Obstacle(id="rect", kind="rectangle", start=(0, 0), end=(10, 10),
                    reflection_loss_db=3)
    _, paths = channel(adapter, tx, [rect])(rx, include_paths=True)
    assert any(p["kind"] == "reflected" for p in paths)
    interior_tx = Transmitter(id="tx", position=(2, 2, 1))
    _, interior_paths = channel(adapter, interior_tx, [rect])((2, 8, 1), include_paths=True)
    assert not any(p["kind"] == "reflected" for p in interior_paths)

    tx = Transmitter(id="tx", position=(1, 2, 1))
    rx = (9, 2, 1)
    mirror = wall(id="mirror", start=(-20, 0), end=(20, 0), reflection_loss_db=3)
    clear_paths = channel(adapter, tx, [mirror])(rx, include_paths=True)[1]
    occluder = wall(id="occluder", start=(2, 0.5), end=(2, 1.5), blocks=True,
                    reflection_loss_db=None)
    occluded_paths = channel(adapter, tx, [mirror, occluder])(rx, include_paths=True)[1]
    assert sum(p["kind"] == "reflected" for p in clear_paths) == 1
    assert not any(p["kind"] == "reflected" for p in occluded_paths)


@pytest.mark.integration
def test_height_interpolation_and_reciprocity(adapter):
    obstacle = wall(start=(5, -2), end=(5, 2), height_m=4,
                    reflection_loss_db=None)
    low_tx = Transmitter(id="tx", position=(0, 0, 1))
    rx = (10, 0, 5)
    # Crossing height is 3m, so obstacle attenuates; at 5m it clears wall.
    attenuated = channel(adapter, low_tx, [obstacle])(rx)
    clear_tx = Transmitter(id="tx", position=(0, 0, 5))
    clear = channel(adapter, clear_tx, [obstacle])(rx)
    assert attenuated == pytest.approx(friis_dbm(low_tx, math.dist(low_tx.position, rx)) - 6)
    assert clear == pytest.approx(friis_dbm(clear_tx, 10), abs=1e-6)

    forward = channel(adapter, low_tx, [obstacle])(rx)
    reverse_tx = Transmitter(id="reverse", position=rx)
    reverse = channel(adapter, reverse_tx, [obstacle])((0, 0, 1))
    assert forward == pytest.approx(reverse, abs=1e-6)


@pytest.mark.integration
def test_blocked_link_recovers_if_reflector_height_and_length_valid(adapter):
    tx = Transmitter(id="tx", position=(1, 2, 1))
    rx = (9, 2, 1)
    blocker = wall(id="block", start=(5, 1), end=(5, 3), height_m=5,
                   blocks=True, reflection_loss_db=None)
    mirror = wall(id="mirror", start=(-20, 0), end=(20, 0), height_m=5,
                  reflection_loss_db=3)
    assert channel(adapter, tx, [blocker])(rx) == -math.inf
    power, paths = channel(adapter, tx, [blocker, mirror])(rx, include_paths=True)
    assert len(paths) == 1 and paths[0]["kind"] == "reflected"
    assert power == pytest.approx(friis_dbm(tx, math.sqrt(80)) - 3, abs=1e-6)
    short = wall(id="short", start=(4.9, 0), end=(5, 0), reflection_loss_db=3)
    assert not channel(adapter, tx, [blocker, short])(rx, include_paths=True)[1]
    low = wall(id="low", start=(-20, 0), end=(20, 0), height_m=0.5,
               reflection_loss_db=3)
    assert not channel(adapter, tx, [blocker, low])(rx, include_paths=True)[1]


@pytest.mark.integration
def test_tall_ray_wall_top_grazing_and_determinism(adapter):
    tx = Transmitter(id="tx", position=(5, 0, 1))
    wall_at_x5 = wall(start=(5, -2), end=(5, 2), height_m=4,
                      blocks=True, reflection_loss_db=None)
    assert channel(adapter, tx, [wall_at_x5])((5, 0, 3)) == -math.inf
    tx_above = Transmitter(id="above", position=(0, 0, 9))
    assert math.isfinite(channel(adapter, tx_above, [wall_at_x5])((10, 0, 9)))
    rx = (10, 0, 1)
    grazing = wall(start=(5, 0), end=(5, 2), blocks=True, reflection_loss_db=None)
    assert channel(adapter, tx, [grazing])(rx) == -math.inf
    result = channel(adapter, tx, [wall_at_x5])(rx, include_paths=True)
    assert result == channel(adapter, tx, [wall_at_x5])(rx, include_paths=True)


@pytest.mark.integration
def test_isolated_obstacle_run_preserves_scenario_and_results():
    data = default_scenario().model_dump()
    data["environment"] = {"width_m": 20, "height_m": 20}
    data["sampling"] = {"resolution_m": 10, "receiver_height_m": 1.5}
    data["transmitters"] = [Transmitter(id="tx", position=(0, 10, 1)).model_dump()]
    data["receivers"] = []
    data["obstacles"] = [wall(start=(10, 0), end=(10, 20), blocks=True,
                              reflection_loss_db=None).model_dump()]
    scenario = Scenario.model_validate(data)
    first = run_isolated(scenario)
    second = run_isolated(scenario)
    assert first.scenario.model_dump() == scenario.model_dump()
    assert first.coverage.equals(second.coverage)
    assert first.metadata["models"] == second.metadata["models"]
    assert first.coverage.loc[first.coverage.x_m == 20, "rx_power_dbm"].eq(-math.inf).all()


@pytest.mark.integration
@pytest.mark.parametrize("start,end,tx_position,rx_position,bounce,length", [
    ((0, 0), (10, 0), (1, 2, 1), (9, 2, 1), (5, 0, 1), math.sqrt(80)),
    ((0, 0), (0, 10), (2, 1, 1), (2, 9, 1), (0, 5, 1), math.sqrt(80)),
    ((0, 0), (10, 10), (1, 3, 1), (3, 5, 1), (3, 3, 1), 4),
    ((10, 10), (0, 0), (1, 3, 1), (3, 5, 1), (3, 3, 1), 4),
])
def test_specular_image_geometry_for_rotated_and_reversed_walls(
    adapter, start, end, tx_position, rx_position, bounce, length
):
    tx = Transmitter(id="tx", position=tx_position)
    mirror = wall(start=start, end=end, blocks=True, reflection_loss_db=3)
    _, paths = channel(adapter, tx, [mirror])(rx_position, include_paths=True)
    reflected = [path for path in paths if path["kind"] == "reflected"]
    assert len(reflected) == 1
    path = reflected[0]
    assert tuple(path[f"bounce_{axis}_m"] for axis in "xyz") == pytest.approx(bounce)
    assert path["distance_m"] == pytest.approx(length)
    assert path["rx_power_dbm"] == pytest.approx(friis_dbm(tx, length) - 3, abs=1e-6)


@pytest.mark.integration
@pytest.mark.parametrize("screens,loss", [("first", 7), ("second", 11), ("both", 18)])
def test_reflected_path_adds_both_leg_losses_and_evaluates_full_distance(adapter, screens, loss):
    tx = Transmitter(id="tx", position=(1, 2, 1))
    objects = [wall(id="mirror", start=(0, 0), end=(10, 0), blocks=True, reflection_loss_db=3)]
    if screens in ("first", "both"):
        objects.append(wall(id="first", start=(3, 0.5), end=(3, 1.5),
                            attenuation_db=7, reflection_loss_db=None))
    if screens in ("second", "both"):
        objects.append(wall(id="second", start=(7, 0.5), end=(7, 1.5),
                            attenuation_db=11, reflection_loss_db=None))
    _, paths = channel(adapter, tx, objects)((9, 2, 1), include_paths=True)
    path = next(path for path in paths if path["kind"] == "reflected")
    assert path["transmission_loss_db"] == loss
    assert path["rx_power_dbm"] == pytest.approx(friis_dbm(tx, math.sqrt(80)) - 3 - loss)
    assert next(path for path in paths if path["kind"] == "direct")["transmission_loss_db"] == 0


@pytest.mark.integration
def test_reflection_uses_interpolated_height_and_is_reciprocal(adapter):
    tx = Transmitter(id="tx", position=(1, 2, 1))
    rx = (9, 2, 5)
    mirror = wall(start=(0, 0), end=(10, 0), height_m=3, blocks=True, reflection_loss_db=3)
    forward, paths = channel(adapter, tx, [mirror])(rx, include_paths=True)
    reflected = next(path for path in paths if path["kind"] == "reflected")
    assert reflected["bounce_z_m"] == pytest.approx(3)
    assert reflected["distance_m"] == pytest.approx(math.sqrt(96))
    reverse_tx = Transmitter(id="reverse", position=rx)
    reverse = channel(adapter, reverse_tx, [mirror])(tx.position)
    assert reverse == pytest.approx(forward)
    low = mirror.model_copy(update={"height_m": 2.9})
    assert not any(path["kind"] == "reflected" for path in
                   channel(adapter, tx, [low])(rx, include_paths=True)[1])


@pytest.mark.integration
def test_vertical_and_coincident_rays_only_intersect_actual_wall_surface(adapter):
    blocking = wall(start=(5, 0), end=(5, 10), height_m=4,
                    blocks=True, reflection_loss_db=None)
    off_wall = Transmitter(id="tx", position=(1, 2, 1))
    assert channel(adapter, off_wall, [blocking])(off_wall.position) == 20
    assert channel(adapter, off_wall, [blocking])((1, 2, 4)) == pytest.approx(
        friis_dbm(off_wall, 3)
    )
    above_wall = Transmitter(id="above", position=(5, 2, 10))
    assert channel(adapter, above_wall, [blocking])((5, 2, 1)) == -math.inf


@pytest.mark.integration
def test_rectangular_transmission_is_charged_once_not_per_face(adapter):
    tx = Transmitter(id="tx", position=(0, 2, 1))
    rectangle = Obstacle(id="box", kind="rectangle", start=(4, 0), end=(6, 4),
                         height_m=5, attenuation_db=6, reflection_loss_db=None)
    assert channel(adapter, tx, [rectangle])((10, 2, 1)) == pytest.approx(friis_dbm(tx, 10) - 6)
