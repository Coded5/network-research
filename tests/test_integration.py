import math

import pytest

from propagation_lab.engine import run, run_isolated
from propagation_lab.ns3_adapter import Ns3Adapter
from propagation_lab.scenario import Friis, LogDistance, Receiver, Scenario, Transmitter

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def adapter():
    instance = Ns3Adapter(42)
    yield instance
    instance.close()


@pytest.fixture
def small_scenario():
    return Scenario(
        environment={"width_m": 100, "height_m": 100},
        transmitters=[Transmitter(id="tx", position=(0, 0, 1), frequency_hz=2.4e9)],
        receivers=[Receiver(id="rx", position=(100, 0, 1))],
        sampling={"resolution_m": 50},
    )


def test_friis_matches_free_space_reference_and_parameter_effects(adapter):
    tx = Transmitter(id="tx", position=(0, 0, 1), frequency_hz=2.4e9)
    power_at, _ = adapter.channel(tx, Friis())
    expected = 20 * math.log10(299792458 / (4 * math.pi * 100 * 2.4e9))
    baseline = power_at((100, 0, 1))
    assert baseline == pytest.approx(20 + expected, abs=1e-6)
    doubled_distance = power_at((200, 0, 1))
    assert power_at((100, 0, 1)) - doubled_distance == pytest.approx(6.0206, abs=1e-3)
    tx.frequency_hz *= 2
    high_frequency, _ = adapter.channel(tx, Friis())
    assert power_at((100, 0, 1)) - high_frequency((100, 0, 1)) == pytest.approx(6.0206, abs=1e-3)
    tx.frequency_hz /= 2
    tx.power_dbm += 10
    high_power, _ = adapter.channel(tx, Friis())
    assert high_power((100, 0, 1)) - baseline == pytest.approx(10)
    tx.power_dbm -= 10
    tx.antenna_gain_dbi = 3
    gain, _ = adapter.channel(tx, Friis())
    assert gain((100, 0, 1)) - baseline == pytest.approx(3)
    lossy, _ = adapter.channel(tx, Friis(parameters={"system_loss": 2}))
    assert power_at((100, 0, 1)) - lossy((100, 0, 1)) == pytest.approx(10 * math.log10(2))


def test_log_distance_exponent_and_reference_behavior(adapter):
    tx = Transmitter(id="tx", position=(0, 0, 1), power_dbm=20)
    model = LogDistance(parameters={
        "exponent": 3, "reference_distance_m": 10, "reference_loss_db": 40,
    })
    power_at, _ = adapter.channel(tx, model)
    assert power_at((5, 0, 1)) == pytest.approx(-20)
    assert power_at((10, 0, 1)) == pytest.approx(-20)
    assert power_at((20, 0, 1)) == pytest.approx(-20 - 30 * math.log10(2))
    steeper, _ = adapter.channel(tx, LogDistance(parameters={
        "exponent": 4, "reference_distance_m": 10, "reference_loss_db": 40,
    }))
    assert steeper((20, 0, 1)) < power_at((20, 0, 1))


def test_run_metadata_shapes_and_coordinate_updates(small_scenario):
    first = run(small_scenario)
    again = run(small_scenario)
    assert {k: v for k, v in first.metadata.items() if k not in {"started_at", "completed_at"}} == {
        k: v for k, v in again.metadata.items() if k not in {"started_at", "completed_at"}
    }
    assert first.coverage.shape == (9, 8)
    assert first.links.shape == (1, 7)
    assert first.curves.shape == (120, 5)
    moved_rx = small_scenario.model_copy(deep=True)
    moved_rx.receivers[0].position = (50, 50, 1)
    assert run(moved_rx).coverage.equals(first.coverage)
    assert not run(moved_rx).links.equals(first.links)
    moved_tx = small_scenario.model_copy(deep=True)
    moved_tx.transmitters[0].position = (50, 0, 1)
    assert not run(moved_tx).coverage.equals(first.coverage)


def test_shared_coordinates_across_grid_resolutions(small_scenario):
    coarse = run(small_scenario).coverage.set_index(["x_m", "y_m"])
    fine_scenario = small_scenario.model_copy(deep=True)
    fine_scenario.sampling.resolution_m = 25
    fine = run(fine_scenario).coverage.set_index(["x_m", "y_m"])
    for coordinate in [(0.0, 0.0), (50.0, 50.0), (100.0, 100.0)]:
        assert coarse.loc[coordinate, "rx_power_dbm"] == pytest.approx(
            fine.loc[coordinate, "rx_power_dbm"]
        )


def test_run_isolated_executes_worker_process(small_scenario):
    direct, isolated = run(small_scenario), run_isolated(small_scenario)
    assert isolated.metadata["simulation_mode"] == direct.metadata["simulation_mode"]
    assert isolated.metadata["grid_shape"] == direct.metadata["grid_shape"]
    assert isolated.coverage.equals(direct.coverage)
    assert isolated.links.equals(direct.links)
    assert isolated.curves.equals(direct.curves)


def test_comparison_preserves_each_transmitter_and_link_metrics(small_scenario):
    small_scenario.transmitters.append(Transmitter(
        id="tx_other", position=(100, 100, 10), power_dbm=13, antenna_gain_dbi=4,
    ))
    result = run(small_scenario, compare=True)
    assert len(result.coverage) == 36
    assert len(result.links) == 4
    assert set(result.coverage.model) == {"friis", "log_distance"}
    assert set(result.coverage.tx_id) == {"tx", "tx_other"}
    for tx in result.scenario.transmitters:
        rows = result.links[result.links.tx_id == tx.id]
        for row in rows.itertuples():
            assert row.path_loss_db == pytest.approx(
                tx.power_dbm + tx.antenna_gain_dbi - row.rx_power_dbm
            )
            assert row.link_margin_db == pytest.approx(row.rx_power_dbm + 90)
            assert row.distance_m == pytest.approx(
                math.dist(tx.position, result.scenario.receivers[0].position)
            )
    assert result.metadata["models"]["log_distance"]["attributes_by_tx"]["tx"]["Exponent"] == 3
    small_scenario.transmitters[0].position = (50, 50, 10)
    assert result.scenario.transmitters[0].position == (0, 0, 1)


def test_duration_and_seed_do_not_change_static_model_outputs(small_scenario):
    first = run(small_scenario)
    small_scenario.simulation.seed = 123
    small_scenario.simulation.duration_s = 100
    second = run(small_scenario)
    assert first.coverage.equals(second.coverage)
    assert first.links.equals(second.links)
