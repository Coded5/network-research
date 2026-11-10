import io
import json
import zipfile

import pandas as pd
import pytest

from propagation_lab.engine import (
    COVERAGE_COLUMNS,
    CURVE_COLUMNS,
    LINK_COLUMNS,
    SimulationResult,
)
from propagation_lab.export import export_results, result_zip
from propagation_lab.scenario import Scenario, Transmitter


def stored_result():
    scenario = Scenario(transmitters=[Transmitter(id="tx_1", position=(0, 0, 10))])
    return SimulationResult(
        scenario,
        {"ns3_version": "3.44.post0", "models": {"friis": {}}, "seed": 42},
        pd.DataFrame(
            [("friis", "tx_1", 0, 0, 1.5, 8.5, -40, 60)], columns=COVERAGE_COLUMNS
        ),
        pd.DataFrame(columns=LINK_COLUMNS),
        pd.DataFrame([("friis", "tx_1", 10, -40, 60)], columns=CURVE_COLUMNS),
    )


def test_package_preserves_snapshot_metadata_and_numerical_results():
    result = stored_result()
    with zipfile.ZipFile(io.BytesIO(result_zip(result))) as archive:
        assert set(archive.namelist()) == {
            "scenario.json", "metadata.json", "receiver_results.csv",
            "coverage_grid.csv", "distance_curves.csv", "paths.csv", "heatmap.html",
        }
        assert Scenario.model_validate_json(archive.read("scenario.json")) == result.scenario
        assert json.loads(archive.read("metadata.json")) == result.metadata
        coverage = pd.read_csv(archive.open("coverage_grid.csv"))
        pd.testing.assert_frame_equal(coverage, result.coverage)
        assert list(pd.read_csv(archive.open("receiver_results.csv"))) == LINK_COLUMNS
        assert "plotly.js" in archive.read("heatmap.html").decode()


def test_disk_export_never_replaces_existing_results(tmp_path):
    target = tmp_path / "run"
    export_results(stored_result(), target)
    original = (target / "scenario.json").read_bytes()
    with pytest.raises(FileExistsError):
        export_results(stored_result(), target)
    assert (target / "scenario.json").read_bytes() == original
