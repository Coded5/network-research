import subprocess
import sys

import pandas as pd
from streamlit.testing.v1 import AppTest

from propagation_lab.scenario import default_scenario
from propagation_lab.ui import heatmap_figure


def test_heatmap_uses_strongest_tx_per_cell_and_keeps_hover_metrics():
    scenario = default_scenario()
    coverage = pd.DataFrame(
        [
            ("friis", "tx_1", 10, 20, 1.5, 3, -70, 90),
            ("friis", "tx_2", 10, 20, 1.5, 4, -50, 70),
            ("friis", "tx_1", 15, 20, 1.5, 5, -60, 80),
            ("log_distance", "tx_2", 10, 20, 1.5, 4, -5, 25),
        ],
        columns=[
            "model",
            "tx_id",
            "x_m",
            "y_m",
            "z_m",
            "distance_m",
            "rx_power_dbm",
            "path_loss_db",
        ],
    )
    fig = heatmap_figure(scenario, coverage)
    assert fig.data[0].type == "heatmap"
    assert list(fig.data[0].z[0]) == [-50, -60]
    assert fig.data[0].customdata[0][0][3] == "tx_2"
    assert len(fig.data) == 3  # RSS heatmap plus TX and RX overlays


def test_selected_tx_heatmap_filters_and_keeps_physical_grid():
    scenario = default_scenario()
    coverage = pd.DataFrame(
        [("friis", tx, 10, 20, 1.5, 3, power, 90) for tx, power in (("tx_1", -70), ("tx_2", -50))],
        columns=[
            "model",
            "tx_id",
            "x_m",
            "y_m",
            "z_m",
            "distance_m",
            "rx_power_dbm",
            "path_loss_db",
        ],
    )
    fig = heatmap_figure(scenario, coverage, "tx_1")
    assert fig.data[0].type == "heatmap"
    assert fig.data[0].z[0][0] == -70
    assert fig.data[0].customdata[0][0][3] == "tx_1"


def test_ui_import_does_not_import_streamlit():
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import propagation_lab.ui; assert 'streamlit' not in sys.modules",
        ],
        check=True,
    )


def test_switching_propagation_model_renders_without_parameter_type_error():
    from pathlib import Path

    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    selector = next(item for item in app.selectbox if item.label == "Propagation model")
    selector.select("log_distance").run()
    assert not app.exception
    assert any(item.label == "Path-loss exponent" for item in app.number_input)


def test_invalid_scenario_draft_disables_run():
    from pathlib import Path

    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    width = next(item for item in app.number_input if item.label == "Map width · m")
    app = width.set_value(0).run()
    run = next(button for button in app.button if button.label == "Run comparison")
    assert run.disabled
    assert any("Correct scenario properties" in item.value for item in app.error)


def test_restoring_original_node_value_clears_invalid_draft():
    from pathlib import Path

    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    frequency = next(item for item in app.number_input if item.label == "Frequency · Hz")
    app = frequency.set_value(0).run()
    assert next(button for button in app.button if button.label == "Run comparison").disabled
    frequency = next(item for item in app.number_input if item.label == "Frequency · Hz")
    app = frequency.set_value(2.4e9).run()
    assert not app.exception
    assert not next(button for button in app.button if button.label == "Run comparison").disabled


def test_import_discards_invalid_scenario_draft():
    from pathlib import Path

    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    width = next(item for item in app.number_input if item.label == "Map width · m")
    app = width.set_value(0).run()
    app.get("file_uploader")[0].upload(
        "scenario.json", default_scenario().model_dump_json().encode(), "application/json"
    ).run()
    app = next(button for button in app.button if button.label == "Import scenario").click().run()
    assert not app.exception
    assert next(item for item in app.number_input if item.label == "Map width · m").value == 500
    assert not next(button for button in app.button if button.label == "Run comparison").disabled


def test_node_rename_and_delete_update_scenario():
    from pathlib import Path

    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    identifier = next(item for item in app.text_input if item.label == "ID")
    app = identifier.set_value("tower_a").run()
    assert app.session_state["scenario"]["transmitters"][0]["id"] == "tower_a"
    assert app.session_state["selected"] == ("TX", "tower_a")
    next(button for button in app.button if button.label == "Delete selected").click().run()
    assert app.session_state["scenario"]["transmitters"] == []
    assert app.session_state["selected"] is None


def test_import_requires_explicit_click_and_commits_once():
    from pathlib import Path

    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    scenario = default_scenario().model_copy(update={"name": "Imported test"})
    uploader = app.get("file_uploader")[0]
    uploader.upload("scenario.json", scenario.model_dump_json().encode(), "application/json").run()
    assert app.session_state["scenario"]["name"] != "Imported test"
    next(button for button in app.button if button.label == "Import scenario").click().run()
    assert app.session_state["scenario"]["name"] == "Imported test"
    assert app.session_state["selected"] is None
    assert app.session_state["map_revision"] > 0


def test_map_move_changes_widget_revision_so_stale_coordinates_cannot_revert_it(monkeypatch):
    from types import ModuleType

    class State(dict):
        __getattr__ = dict.__getitem__
        __setattr__ = dict.__setitem__

    import propagation_lab.ui as ui

    state = State(
        {
            "scenario": default_scenario().model_dump(mode="json"),
            "selected": ("TX", "tx_1"),
            "x_0_tx_1": 333.0,
        }
    )
    streamlit = ModuleType("streamlit")
    streamlit.session_state = state
    monkeypatch.setitem(sys.modules, "streamlit", streamlit)
    assert ui._move_selected(default_scenario(), ("TX", "tx_1"), 25.0, 30.0)
    assert state["scenario"]["transmitters"][0]["position"][:2] == [25.0, 30.0]
    assert state["node_revision"] == 1
    assert "x_1_tx_1" not in state  # new widget key loads committed map position
