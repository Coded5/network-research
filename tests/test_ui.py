import subprocess
import sys

import numpy as np
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


def test_no_path_heatmap_masks_infinite_received_power():
    scenario = default_scenario()
    coverage = pd.DataFrame(
        [
            ("friis", "tx_1", 10, 20, 1.5, 3, float("-inf"), float("inf")),
            ("friis", "tx_2", 10, 20, 1.5, 3, float("-inf"), float("inf")),
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
    assert np.isnan(fig.data[0].z[0][0])


def test_obstacle_create_edit_delete_and_import_roundtrip():
    import json
    from pathlib import Path

    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    next(button for button in app.button if button.label == "＋ Wall").click().run()
    assert not app.exception
    assert app.session_state["scenario"]["obstacles"][0]["kind"] == "wall"
    name = next(item for item in app.text_input if item.label == "Name")
    name.set_value("North wall").run()
    assert app.session_state["scenario"]["obstacles"][0]["name"] == "North wall"
    next(item for item in app.number_input if item.label == "Attenuation · dB").set_value(11).run()
    assert app.session_state["scenario"]["obstacles"][0]["attenuation_db"] == 11
    dumped = json.dumps(app.session_state["scenario"])
    app.get("file_uploader")[0].upload("scenario.json", dumped.encode(), "application/json").run()
    next(button for button in app.button if button.label == "Import scenario").click().run()
    assert app.session_state["scenario"]["obstacles"][0]["name"] == "North wall"
    assert app.session_state["scenario"]["obstacles"][0]["attenuation_db"] == 11
    next(button for button in app.button if button.label.startswith("obstacle_1  ·")).click().run()
    next(button for button in app.button if button.label == "Delete selected").click().run()
    assert app.session_state["scenario"]["obstacles"] == []


def test_rectangle_obstacle_can_edit_geometry_and_material():
    from pathlib import Path

    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    next(button for button in app.button if button.label == "＋ Rectangle").click().run()
    assert not app.exception
    assert app.session_state["scenario"]["obstacles"][0]["kind"] == "rectangle"
    next(item for item in app.number_input if item.label == "Start x · m").set_value(120).run()
    obstacle = app.session_state["scenario"]["obstacles"][0]
    assert obstacle["start"][0] == 120
    next(item for item in app.number_input if item.label == "Attenuation · dB").set_value(9).run()
    assert app.session_state["scenario"]["obstacles"][0]["attenuation_db"] == 9
    assert not app.exception


def test_invalid_obstacle_draft_blocks_run_until_geometry_is_fixed():
    from pathlib import Path

    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    next(button for button in app.button if button.label == "＋ Rectangle").click().run()
    next(item for item in app.number_input if item.label == "End x · m").set_value(200).run()
    assert next(button for button in app.button if button.label == "Run comparison").disabled
    next(item for item in app.number_input if item.label == "End x · m").set_value(300).run()
    assert not next(button for button in app.button if button.label == "Run comparison").disabled
    assert not app.exception


def test_stored_reflection_paths_render_with_pandas_index(monkeypatch):
    import streamlit as st

    from propagation_lab.ui import _draw_stored_paths

    paths = pd.DataFrame([{
        "tx_id": "tx_1", "rx_id": "rx_1", "kind": "reflected", "obstacle_id": "mirror",
        "bounce_x_m": 150.0, "bounce_y_m": 200.0,
    }])
    rendered = []
    monkeypatch.setattr(st, "plotly_chart", lambda figure, **kwargs: rendered.append(figure))
    _draw_stored_paths(default_scenario(), paths)
    path = rendered[0].data[-1]
    assert path.x == (100, 150, 200)
    assert path.y == (250, 200, 250)
    assert path.showlegend is True


def test_translate_obstacle_exits_placement_mode():
    from pathlib import Path

    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run()
    next(button for button in app.button if button.label == "＋ Wall").click().run()
    next(radio for radio in app.radio if radio.label == "Map action").set_value("Place wall").run()
    next(button for button in app.button if button.label == "Translate obstacle").click().run()
    assert not app.exception
    mode = next(radio for radio in app.radio if radio.label == "Map action").value
    assert mode == "Select / move"
