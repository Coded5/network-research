from pathlib import Path

import pandas as pd
import pytest

from propagation_lab.engine import run_isolated
from propagation_lab.scenario import Scenario


@pytest.mark.integration
def test_inet_results_match_captured_ns3_links_paths_and_grid():
    root = Path(__file__).parents[1]
    scenario = Scenario.model_validate_json((root / "scenarios" / "reflection.json").read_text())
    result = run_isolated(scenario, compare=True)
    fixtures = Path(__file__).parent / "fixtures"
    assert result.metadata["backend"] == "omnetpp_inet"
    for name, actual, index in [
        ("links", result.links, ["model", "tx_id", "rx_id"]),
        ("paths", result.paths, ["model", "tx_id", "rx_id", "kind"]),
        ("grid", result.coverage, ["model", "tx_id", "x_m", "y_m"]),
    ]:
        expected = pd.read_csv(fixtures / f"ns3_{name}.csv", comment="#").set_index(index)
        actual = actual.set_index(index).loc[expected.index]
        if name == "paths":
            expected["obstacle_id"] = expected.obstacle_id.fillna("")
        pd.testing.assert_frame_equal(
            actual, expected, check_dtype=False, check_exact=False, rtol=1e-10, atol=1e-8
        )
