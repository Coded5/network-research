"""Portable result packages built exclusively from stored simulation results."""

import io
import json
import zipfile
from pathlib import Path

from propagation_lab.engine import SimulationResult


def result_zip(result: SimulationResult) -> bytes:
    from propagation_lab.ui import heatmap_figure

    selected = result.coverage[result.coverage.model == result.scenario.propagation.model]
    figure = heatmap_figure(result.scenario, selected)
    figure.update_layout(title="Maximum RSS across transmitters — not combined RF power")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("scenario.json", result.scenario.model_dump_json(indent=2))
        archive.writestr("metadata.json", json.dumps(result.metadata, indent=2))
        archive.writestr("receiver_results.csv", result.links.to_csv(index=False))
        archive.writestr("coverage_grid.csv", result.coverage.to_csv(index=False))
        archive.writestr("distance_curves.csv", result.curves.to_csv(index=False))
        archive.writestr("heatmap.html", figure.to_html(include_plotlyjs=True, full_html=True))
    return buffer.getvalue()


def export_results(result: SimulationResult, directory: str | Path) -> Path:
    directory = Path(directory)
    package = result_zip(result)
    directory.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        # Archive names are fixed by result_zip, never supplied by a scenario.
        archive.extractall(directory)
    return directory
