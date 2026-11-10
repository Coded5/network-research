"""Streamlit editor and Plotly views; importing this module has no UI side effects."""

from __future__ import annotations

import json

import numpy as np
import plotly.graph_objects as go
from pydantic import ValidationError

from propagation_lab.scenario import (
    Friis,
    LogDistance,
    Receiver,
    Scenario,
    Transmitter,
    default_scenario,
)

COLORS = {"tx": "#d48a28", "rx": "#087e83", "grid": "#b8c9ce"}


def heatmap_figure(scenario: Scenario, coverage, tx_id: str | None = None) -> go.Figure:
    """Plot actual computed coverage for one TX, or maximum RSS across TXs."""
    coverage = coverage[coverage.model == scenario.propagation.model]
    data = coverage if tx_id is None else coverage[coverage.tx_id == tx_id]
    if tx_id is None and len(data):
        data = data.loc[data.groupby(["x_m", "y_m"], sort=False).rx_power_dbm.idxmax()]
    fig = go.Figure()
    if len(data):
        xs, ys = sorted(data.x_m.unique()), sorted(data.y_m.unique())
        power = data.pivot(index="y_m", columns="x_m", values="rx_power_dbm").reindex(
            index=ys, columns=xs
        )
        custom = np.empty((*power.shape, 4), dtype=object)
        for index, column in enumerate(["rx_power_dbm", "path_loss_db", "distance_m", "tx_id"]):
            custom[:, :, index] = data.pivot(index="y_m", columns="x_m", values=column).reindex(
                index=ys, columns=xs
            ).to_numpy()
        fig.add_trace(
            go.Heatmap(
                x=xs,
                y=ys,
                z=power.to_numpy(),
                customdata=custom,
                colorscale="Teal",
                colorbar={"title": "RSS (dBm)"},
                hovertemplate="x=%{x:.2f} m<br>y=%{y:.2f} m<br>RSS=%{customdata[0]:.2f} dBm<br>"
                "Path loss=%{customdata[1]:.2f} dB<br>Distance=%{customdata[2]:.2f} m"
                "<extra>%{customdata[3]}</extra>",
                name="Maximum RSS" if tx_id is None else tx_id,
            )
        )
    _map_layout(fig, scenario, "Computed received power")
    _add_nodes(fig, scenario)
    return fig


def _map_layout(fig: go.Figure, scenario: Scenario, title: str) -> None:
    fig.update_layout(
        title=title,
        height=560,
        margin={"l": 12, "r": 20, "t": 48, "b": 68},
        paper_bgcolor="#f3f6f7",
        plot_bgcolor="#f8fafb",
        font={"color": "#172b35", "family": "sans-serif"},
        xaxis={
            "title": "x (m)",
            "range": [0, scenario.environment.width_m],
            "gridcolor": "#dce5e7",
            "constrain": "domain",
        },
        yaxis={
            "title": "y (m)",
            "range": [0, scenario.environment.height_m],
            "gridcolor": "#dce5e7",
            "scaleanchor": "x",
            "scaleratio": 1,
        },
        legend={"orientation": "h", "x": 0, "y": -0.17, "xanchor": "left", "yanchor": "top"},
    )


def _add_nodes(fig: go.Figure, scenario: Scenario) -> None:
    for nodes, kind, color, symbol in (
        (scenario.transmitters, "TX", COLORS["tx"], "diamond"),
        (scenario.receivers, "RX", COLORS["rx"], "circle"),
    ):
        if nodes:
            fig.add_trace(
                go.Scatter(
                    x=[n.position[0] for n in nodes],
                    y=[n.position[1] for n in nodes],
                    mode="markers+text",
                    text=[n.id for n in nodes],
                    textposition="top center",
                    marker={
                        "size": 14,
                        "color": color,
                        "symbol": symbol,
                        "line": {"color": "white", "width": 1.5},
                    },
                    customdata=[[kind, n.id] for n in nodes],
                    hovertemplate=(
                        "%{customdata[0]} · %{customdata[1]}<br>"
                        "x=%{x:.1f} m, y=%{y:.1f} m<extra></extra>"
                    ),
                    name=kind,
                    showlegend=True,
                )
            )


def _scenario() -> Scenario:
    import streamlit as st

    return Scenario.model_validate(st.session_state.scenario)


def _save(scenario: Scenario) -> None:
    import streamlit as st

    st.session_state.scenario = scenario.model_dump(mode="json")


def _update_node(node_id: str, kind: str, values: dict) -> bool:
    import streamlit as st

    current = _scenario().model_dump(mode="python")
    key = "transmitters" if kind == "TX" else "receivers"
    for index, node in enumerate(current[key]):
        if node["id"] == node_id:
            current[key][index] = values
            break
    try:
        updated = Scenario.model_validate(current)
        if updated.model_dump(mode="json") != _scenario().model_dump(mode="json"):
            _save(updated)
            if values["id"] != node_id:
                st.session_state.selected = (kind, values["id"])
            if st.session_state.get("draft_error_kind") == "node":
                st.session_state.pop("draft_error", None)
                st.session_state.pop("draft_error_kind", None)
            return True
        if st.session_state.get("draft_error_kind") == "node":
            st.session_state.pop("draft_error", None)
            st.session_state.pop("draft_error_kind", None)
    except ValidationError as exc:
        st.session_state.draft_error_kind = "node"
        st.session_state.draft_error = f"Correct node properties before running: {exc}"
        st.error(st.session_state.draft_error)
    return False


def _edit_properties(scenario: Scenario, selected: tuple[str, str] | None) -> None:
    import streamlit as st

    st.subheader("Properties")
    prefix = f"config_{st.session_state.get('config_revision', 0)}_"
    with st.expander("Scenario & model", expanded=selected is None):
        name = st.text_input("Scenario name", scenario.name, key=prefix + "name")
        width = st.number_input(
            "Map width · m", min_value=0.0, value=float(scenario.environment.width_m),
            key=prefix + "width",
        )
        height = st.number_input(
            "Map height · m", min_value=0.0, value=float(scenario.environment.height_m),
            key=prefix + "height",
        )
        model = st.selectbox(
            "Propagation model",
            ["friis", "log_distance"],
            index=0 if scenario.propagation.model == "friis" else 1,
            key=prefix + "model",
        )
        params = scenario.propagation.parameters
        if model == "friis":
            system_loss = st.number_input(
                "System loss",
                min_value=1.0,
                value=float(params.system_loss) if isinstance(scenario.propagation, Friis) else 1.0,
                key=prefix + "system_loss",
            )
            propagation_values = {"model": "friis", "parameters": {"system_loss": system_loss}}
        else:
            exponent = st.number_input(
                "Path-loss exponent",
                min_value=0.0,
                max_value=10.0,
                value=float(params.exponent)
                if isinstance(scenario.propagation, LogDistance)
                else 3.0,
                key=prefix + "exponent",
            )
            reference_distance = st.number_input(
                "Reference distance · m",
                min_value=0.0,
                value=float(params.reference_distance_m)
                if isinstance(scenario.propagation, LogDistance)
                else 1.0,
                key=prefix + "reference_distance",
            )
            reference_loss = st.number_input(
                "Reference loss · dB",
                min_value=0.0,
                max_value=300.0,
                value=float(params.reference_loss_db)
                if isinstance(scenario.propagation, LogDistance)
                else 46.6777,
                key=prefix + "reference_loss",
            )
            propagation_values = {
                "model": "log_distance",
                "parameters": {
                    "exponent": exponent,
                    "reference_distance_m": reference_distance,
                    "reference_loss_db": reference_loss,
                },
            }
            st.caption("Reference loss is a fixed user value; it does not vary with frequency.")
        resolution = st.number_input(
            "Grid spacing · m", min_value=0.0, value=float(scenario.sampling.resolution_m),
            key=prefix + "resolution",
        )
        rx_height = st.number_input(
            "Grid receiver height · m",
            min_value=0.0,
            max_value=10000.0,
            value=float(scenario.sampling.receiver_height_m),
            key=prefix + "rx_height",
        )
        duration = st.number_input(
            "Duration · s", min_value=0.0, value=float(scenario.simulation.duration_s),
            key=prefix + "duration",
        )
        seed = st.number_input(
            "Seed", min_value=1, max_value=2**32 - 1, value=int(scenario.simulation.seed), step=1,
            key=prefix + "seed",
        )
        st.caption(
            "Static channel evaluations: no packets, waveforms, or interference. "
            "Seed and duration do not affect deterministic results."
        )
        values = scenario.model_dump(mode="python")
        values.update(
            name=name,
            environment={"width_m": width, "height_m": height},
            propagation=propagation_values,
            sampling={"resolution_m": resolution, "receiver_height_m": rx_height},
            simulation={"duration_s": duration, "seed": seed},
        )
        try:
            candidate = Scenario.model_validate(values)
            if st.session_state.get("draft_error_kind") == "scenario":
                st.session_state.pop("draft_error", None)
                st.session_state.pop("draft_error_kind", None)
            if candidate.model_dump(mode="json") != scenario.model_dump(mode="json"):
                _save(candidate)
                st.rerun()
        except ValidationError as exc:
            st.session_state.draft_error_kind = "scenario"
            st.session_state.draft_error = f"Correct scenario properties before running: {exc}"
            st.error(st.session_state.draft_error)

    if selected:
        kind, node_id = selected
        widget_id = f"{st.session_state.get('node_revision', 0)}_{node_id}"
        nodes = scenario.transmitters if kind == "TX" else scenario.receivers
        node = next((n for n in nodes if n.id == node_id), None)
        if node is not None:
            with st.expander(f"{kind} · {node_id}", expanded=True):
                new_id = st.text_input("ID", node.id, key="id_" + widget_id)
                name = st.text_input("Name", node.name, key="name_" + widget_id)
                x = st.number_input(
                    "x · m",
                    0.0,
                    float(scenario.environment.width_m),
                    float(node.position[0]),
                    key="x_" + widget_id,
                )
                y = st.number_input(
                    "y · m",
                    0.0,
                    float(scenario.environment.height_m),
                    float(node.position[1]),
                    key="y_" + widget_id,
                )
                z = st.number_input(
                    "Height · m", 0.0, 10000.0, float(node.position[2]), key="z_" + widget_id
                )
                data = {"id": new_id, "name": name, "position": (x, y, z)}
                if kind == "TX":
                    data.update(
                        frequency_hz=st.number_input(
                            "Frequency · Hz",
                            min_value=0.0,
                            max_value=1e12,
                            value=float(node.frequency_hz),
                            format="%.0f",
                            key="f_" + widget_id,
                        ),
                        power_dbm=st.number_input(
                            "TX power · dBm",
                            -100.0,
                            100.0,
                            float(node.power_dbm),
                            key="p_" + widget_id,
                        ),
                        antenna_gain_dbi=st.number_input(
                            "Antenna gain · dBi",
                            -100.0,
                            100.0,
                            float(node.antenna_gain_dbi),
                            key="g_" + widget_id,
                        ),
                    )
                else:
                    data["sensitivity_dbm"] = st.number_input(
                        "Sensitivity · dBm",
                        -200.0,
                        100.0,
                        float(node.sensitivity_dbm),
                        key="s_" + widget_id,
                    )
                if _update_node(node_id, kind, data):
                    if new_id != node_id:
                        st.session_state.node_revision = (
                            st.session_state.get("node_revision", 0) + 1
                        )
                    st.rerun()


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="Propagation Lab", page_icon="⌁", layout="wide")
    st.markdown(
        "<style>.block-container{padding-top:1.4rem} "
        "code,.mono{font-family:ui-monospace,monospace}</style>",
        unsafe_allow_html=True,
    )
    st.title("Propagation Lab")
    st.caption("Static wireless channel evaluation · Cartesian coordinates in metres")
    if "scenario" not in st.session_state:
        st.session_state.scenario = default_scenario().model_dump(mode="json")
    if "selected" not in st.session_state:
        st.session_state.selected = ("TX", "tx_1")
    scenario = _scenario()
    left, center, right = st.columns([0.9, 2.3, 1.15], gap="medium")
    with right:
        _edit_properties(scenario, st.session_state.selected)

    with left:
        st.subheader("Scenario objects")
        st.caption(scenario.name)
        for kind, nodes in (("TX", scenario.transmitters), ("RX", scenario.receivers)):
            st.markdown(f"**{kind} · {len(nodes)}**")
            for node in nodes:
                if st.button(
                    f"{node.id}  ·  {node.name or kind}",
                    key="select_" + node.id,
                    use_container_width=True,
                ):
                    st.session_state.selected = (kind, node.id)
                    st.rerun()
        col_a, col_b = st.columns(2)
        if col_a.button(
            "＋ TX", use_container_width=True, disabled=len(scenario.transmitters) >= 32
        ):
            if _append_node("TX", scenario):
                st.rerun()
        if col_b.button("＋ RX", use_container_width=True, disabled=len(scenario.receivers) >= 500):
            if _append_node("RX", scenario):
                st.rerun()
        if st.session_state.selected:
            kind, node_id = st.session_state.selected
            if st.button("Delete selected", type="secondary", use_container_width=True):
                values = scenario.model_dump(mode="python")
                key = "transmitters" if kind == "TX" else "receivers"
                values[key] = [n for n in values[key] if n["id"] != node_id]
                _save(Scenario.model_validate(values))
                st.session_state.selected = None
                st.session_state.node_revision = st.session_state.get("node_revision", 0) + 1
                _reset_map_selection()
                st.rerun()
        st.divider()
        st.download_button(
            "Export scenario JSON",
            scenario.model_dump_json(indent=2),
            "scenario.json",
            "application/json",
            use_container_width=True,
        )
        upload_key = "scenario_upload_" + str(st.session_state.get("upload_revision", 0))
        uploaded = st.file_uploader("Import scenario JSON", type="json", key=upload_key)
        if st.button("Import scenario", disabled=uploaded is None):
            try:
                if uploaded is None:
                    return
                imported = Scenario.model_validate_json(uploaded.getvalue())
                _save(imported)
                st.session_state.selected = None
                st.session_state.pop("draft_error", None)
                st.session_state.pop("draft_error_kind", None)
                st.session_state.node_revision = st.session_state.get("node_revision", 0) + 1
                st.session_state.upload_revision = st.session_state.get("upload_revision", 0) + 1
                st.session_state.config_revision = st.session_state.get("config_revision", 0) + 1
                st.session_state.metric_tx = (
                    "" if not imported.transmitters else imported.transmitters[0].id
                )
                st.session_state.metric_rx = (
                    "" if not imported.receivers else imported.receivers[0].id
                )
                st.session_state.map_revision = st.session_state.get("map_revision", 0) + 1
                st.success("Scenario imported.")
                st.rerun()
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                st.error(f"Invalid scenario JSON: {exc}")

    with center:
        st.subheader("Map")
        mode = st.radio(
            "Map action",
            ["Select / move", "Place TX", "Place RX"],
            horizontal=True,
            label_visibility="collapsed",
        )
        is_current = st.session_state.get("result_scenario") == scenario.model_dump(mode="json")
        result = st.session_state.get("result") if is_current else None
        if result:
            options = ["Maximum RSS", *[n.id for n in scenario.transmitters]]
            pending_tx = st.session_state.pop("pending_coverage_tx", None)
            if pending_tx:
                st.session_state.coverage_source = pending_tx
            choice = st.selectbox(
                "Coverage source", options, key="coverage_source", label_visibility="collapsed"
            )
            st.caption(
                "Maximum RSS selects strongest individual transmitter; it is not combined RF power."
            )
            coverage = result.coverage[result.coverage.model == scenario.propagation.model]
            fig = heatmap_figure(scenario, coverage, None if choice == "Maximum RSS" else choice)
            _add_placement_lattice(fig, scenario)
        else:
            fig = go.Figure()
            _add_placement_lattice(fig, scenario)
            _map_layout(fig, scenario, "Place nodes · click map")
            _add_nodes(fig, scenario)
        map_key = "scenario_map_" + str(st.session_state.get("map_revision", 0))
        event = st.plotly_chart(
            fig,
            use_container_width=True,
            on_select="rerun",
            selection_mode="points",
            key=map_key,
        )
        if isinstance(event, dict):  # AppTest supplies the selection state as a plain mapping.
            selection = event.get("selection", {})
            points = selection.get("points", [])
        else:
            points = event.selection.points if event and event.selection else []
        if points:
            point = points[-1]
            meta = point.get("customdata") or []
            if mode.startswith("Place"):
                kind = mode[-2:]
                node_id = _append_node(kind, scenario, (point.get("x", 0), point.get("y", 0)))
                if node_id is not None:
                    st.session_state.selected = (kind, node_id)
                    st.session_state.node_revision = st.session_state.get("node_revision", 0) + 1
                    _reset_map_selection()
                    st.rerun()
            elif len(meta) >= 2 and meta[0] in ("TX", "RX"):
                st.session_state.selected = (meta[0], meta[1])
                if meta[0] == "TX":
                    st.session_state.pending_coverage_tx = meta[1]
                    st.session_state.metric_tx = meta[1]
                else:
                    st.session_state.metric_rx = meta[1]
                _reset_map_selection()
                st.rerun()
            elif st.session_state.selected and "x" in point and "y" in point:
                if _move_selected(scenario, st.session_state.selected, point["x"], point["y"]):
                    _reset_map_selection()
                    st.rerun()
        if not result:
            st.caption("No computed heatmap yet. Muted map dots are placement targets only.")
        draft_error = st.session_state.get("draft_error")
        if draft_error:
            st.warning("Run comparison is disabled until invalid properties are corrected.")
        if st.button(
            "Run comparison", type="primary", use_container_width=True, disabled=bool(draft_error)
        ):
            try:
                if st.session_state.get("draft_error"):
                    st.error("Correct invalid properties before running.")
                    return
                scenario.require_runnable()
                from propagation_lab.engine import run_isolated

                with st.spinner("Evaluating propagation models…"):
                    result = run_isolated(scenario, compare=True)
                st.session_state.result = result
                st.session_state.result_scenario = result.scenario.model_dump(mode="json")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        if result:
            st.download_button(
                "Export result package",
                _result_zip(result),
                "propagation-results.zip",
                "application/zip",
            )

    # Results are always read from the immutable run snapshot, never live edited values.
    scenario = _scenario()
    result = st.session_state.get("result")
    snapshot = st.session_state.get("result_scenario")
    if result and snapshot == scenario.model_dump(mode="json"):
        st.divider()
        st.subheader("Measurements")
        model = scenario.propagation.model
        model_metadata = result.metadata.get("models", {}).get(model, {})
        with st.expander("Model metadata & parameters"):
            st.json(model_metadata)
        links = result.links[result.links.model == model]
        if scenario.transmitters and scenario.receivers and len(links):
            tx = st.selectbox("Transmitter", [n.id for n in scenario.transmitters], key="metric_tx")
            rx = st.selectbox("Receiver", [n.id for n in scenario.receivers], key="metric_rx")
            link = links[(links.tx_id == tx) & (links.rx_id == rx)]
            if len(link):
                row = link.iloc[0]
                cols = st.columns(4)
                for col, label, value, unit in zip(
                    cols,
                    ("Distance", "RSS", "Path loss", "Link margin"),
                    (row.distance_m, row.rx_power_dbm, row.path_loss_db, row.link_margin_db),
                    ("m", "dBm", "dB", "dB"),
                ):
                    col.metric(label, f"{value:.2f} {unit}")
        curves = result.curves
        if len(curves):
            chosen_tx = st.selectbox(
                "Distance plot TX", [n.id for n in scenario.transmitters], key="curve_tx"
            )
            fig = go.Figure()
            for model_name, group in curves[curves.tx_id == chosen_tx].groupby("model"):
                fig.add_scatter(
                    x=group.distance_m,
                    y=group.rx_power_dbm,
                    mode="lines",
                    name=model_name,
                    hovertemplate="%{x:.1f} m · %{y:.2f} dBm<extra>%{fullData.name}</extra>",
                )
            fig.update_layout(
                title="Received power vs distance · model comparison",
                xaxis_title="Distance (m)",
                yaxis_title="Received power (dBm)",
                height=360,
                paper_bgcolor="#f3f6f7",
                font={"color": "#172b35"},
            )
            st.plotly_chart(fig, use_container_width=True)
    elif st.session_state.get("result"):
        st.info("Scenario changed; previous results are stale. Run comparison again.")


def _append_node(
    kind: str, scenario: Scenario, xy: tuple[float, float] | None = None
) -> str | None:
    values = scenario.model_dump(mode="python")
    nodes_key = "transmitters" if kind == "TX" else "receivers"
    prefix = kind.lower()
    occupied = {n["id"] for n in [*values["transmitters"], *values["receivers"]]}
    i = 1
    while f"{prefix}_{i}" in occupied:
        i += 1
    x, y = xy or (scenario.environment.width_m / 2, scenario.environment.height_m / 2)
    node = (
        Transmitter(id=f"{prefix}_{i}", position=(x, y, 10))
        if kind == "TX"
        else Receiver(id=f"{prefix}_{i}", position=(x, y, scenario.sampling.receiver_height_m))
    )
    values[nodes_key].append(node.model_dump(mode="python"))
    try:
        _save(Scenario.model_validate(values))
        import streamlit as st

        return node.id
    except ValidationError as exc:
        import streamlit as st

        st.error(f"Cannot add node; correct scenario limits: {exc}")


def _move_selected(scenario: Scenario, selected: tuple[str, str], x: float, y: float) -> bool:
    kind, node_id = selected
    nodes = scenario.transmitters if kind == "TX" else scenario.receivers
    node = next((n for n in nodes if n.id == node_id), None)
    if node:
        data = node.model_dump()
        data["position"] = (x, y, node.position[2])
        try:
            if _update_node(node_id, kind, data):
                import streamlit as st

                st.session_state.node_revision = st.session_state.get("node_revision", 0) + 1
                return True
        except ValidationError as exc:
            import streamlit as st

            st.error(f"Cannot move node: {exc}")
    return False


def _add_placement_lattice(fig: go.Figure, scenario: Scenario) -> None:
    xs = np.linspace(
        0, scenario.environment.width_m, max(2, min(31, int(scenario.environment.width_m) + 1))
    )
    ys = np.linspace(
        0, scenario.environment.height_m, max(2, min(31, int(scenario.environment.height_m) + 1))
    )
    gx, gy = np.meshgrid(xs, ys)
    fig.add_trace(
        go.Scatter(
            x=gx.ravel(),
            y=gy.ravel(),
            mode="markers",
            marker={"size": 14, "color": COLORS["grid"], "opacity": 0.01},
            customdata=[["GRID", ""] for _ in gx.ravel()],
            hoverinfo="none",
            name="placement grid",
            showlegend=False,
        )
    )


def _reset_map_selection() -> None:
    import streamlit as st

    st.session_state.map_revision = st.session_state.get("map_revision", 0) + 1


def _result_zip(result):
    from propagation_lab.export import result_zip

    return result_zip(result)
