import subprocess

import pytest

from propagation_lab.engine import run_isolated, sample_axis
from propagation_lab.scenario import Scenario, default_scenario


def test_grid_includes_both_boundaries_and_short_last_interval():
    assert sample_axis(100, 50).tolist() == [0, 50, 100]
    assert sample_axis(100, 30).tolist() == [0, 30, 60, 90, 100]


def test_default_grid_is_101_by_101():
    scenario = default_scenario()
    assert len(sample_axis(scenario.environment.width_m, scenario.sampling.resolution_m)) == 101
    assert len(sample_axis(scenario.environment.height_m, scenario.sampling.resolution_m)) == 101


def test_scenario_without_transmitter_is_not_runnable():
    with pytest.raises(ValueError, match="transmitter"):
        Scenario().require_runnable()


def test_worker_failure_is_reported_without_analytical_fallback(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "binding failed"),
    )
    with pytest.raises(RuntimeError, match="binding failed"):
        run_isolated(default_scenario())


def test_worker_timeout_is_reported(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match="180 seconds"):
        run_isolated(default_scenario())
