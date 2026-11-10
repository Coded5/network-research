# Propagation Lab

Local wireless signal propagation workbench: Python, Streamlit, Plotly, and real
ns-3 C++ propagation models accessed through cppyy. Place transmitters and receivers,
inspect static RSS coverage and individual links, compare models, and export results.

## Install and run

The tested binding is **ns3==3.44.post0 + cppyy==3.5.0 + Python 3.12** on Linux
x86-64. The ns3 PyPI wheel includes the simulation libraries and Python bindings;
no separate ns-3 source build is needed. Python 3.14 is not supported by this pin.
Use a C++ compiler and standard-library headers compatible with cppyy's bundled Cling.

```sh
uv sync --extra dev
uv run propagation-lab --smoke
uv run streamlit run app.py
```

Or use Python 3.12's `venv` and `pip install -e '.[dev]'`. Run every command in the
same environment. The smoke command performs an actual ns-3 Friis calculation at
100 m and 2.4 GHz and checks −60.052008056 dBm within 0.000001 dB.

### Compiler compatibility

cppyy 3.5.0's Cling cannot parse some newer standard-library headers. On this
Arch Linux host, GCC 16 headers caused a binding crash; GCC 15 headers worked with
this override, inherited by simulation workers:

```sh
export EXTRA_CLING_ARGS="-std=c++20 -nostdinc++ -isystem /usr/lib/gcc/x86_64-pc-linux-gnu/15.3.0/include/c++ -isystem /usr/lib/gcc/x86_64-pc-linux-gnu/15.3.0/include/c++/x86_64-pc-linux-gnu"
uv run propagation-lab --smoke
```

Use paths belonging to your installed compatible compiler, not these paths blindly.
On systems with compatible default headers, no override is needed. If overriding
`EXTRA_CLING_ARGS`, keep `-std=c++20`. Test the smoke command before starting the UI.
No analytical fallback hides a missing or broken ns-3 installation.

## Workflow

1. Add a transmitter or receiver, select a node, and edit its properties.
2. Use the map tools to place or move nodes; exact coordinates remain editable.
3. Configure map bounds, sampling height/spacing, and Friis or Log-Distance parameters.
4. Run the simulation. Choose one transmitter or maximum RSS for the heatmap.
5. Inspect receivers and model-comparison curves. Download the scenario JSON or
   the complete result ZIP. Import JSON to reopen all supported settings.

Scenario edits invalidate displayed results. Run again to update the measurements.
The editor never retains ns-3 objects. Each run uses a fresh subprocess, with a
180-second timeout and errors surfaced to the UI/CLI.

### CLI and exports

```sh
uv run propagation-lab scenarios/free_space.json --compare --output results/free_space
uv run propagation-lab scenarios/log_distance.json --output results/log_distance
uv run pytest
uv run ruff check .
```

Output directories must be new; existing results are never replaced. Each package contains:

```text
scenario.json
metadata.json
receiver_results.csv
coverage_grid.csv
distance_curves.csv
heatmap.html
```

CSV rows retain separate `model` and `tx_id` fields. The HTML heatmap is standalone
(Plotly is embedded) and shows maximum RSS for the selected propagation model.
Metadata records binding versions, exact ns-3 attributes per transmitter/model,
seed, duration, grid dimensions, simulation mode, and UTC start/end timestamps.
Comparisons evaluate the same layout with the selected parameters and the other
model's defaults; both parameter sets are recorded. All charts use stored ns-3 results.

## Model semantics and limits

- Coordinates and antenna heights are meters; frequencies are Hz; powers are dBm;
  antenna gains are dBi; path loss and link margin are dB. All distances are 3D.
- Friis sets `Frequency`, `SystemLoss` (at least 1), and `MinLoss=0` explicitly.
  `SystemLoss` is a linear factor, not dB.
  Near-field and coincident samples are model evaluations, not physically valid
  free-space predictions. Friis clamps negative path loss at 0 dB.
- Log-Distance sets `Exponent`, `ReferenceDistance`, and `ReferenceLoss` explicitly.
  Reference loss defaults to 46.6777 dB at 1 m, matching ns-3's model default;
  **it is not automatically recomputed from transmitter frequency**. Set a calibrated
  reference loss for the intended frequency/environment. ns-3 3.44 applies reference
  loss at and below the reference distance, with additional distance loss beyond it.
- Transmitter gain is a constant isotropic term added to transmit power. Receiver
  gain is 0 dBi. Path loss excludes transmitter gain; margin is RSS minus sensitivity.
- Maximum RSS is the largest individual transmitter value, **not combined power,
  interference, or SINR**. Models do not account for arbitrary obstacles.
- These are deterministic, stationary propagation-model evaluations, not packets,
  wavefronts, electromagnetic interference/diffraction, Wi-Fi throughput, or time
  evolution. Duration and seed are persisted but do not change these model outputs.
- Grid includes map edges; non-divisible dimensions have a shorter final interval.
  The default 500 × 500 m map with 5 m spacing has 10,201 samples per transmitter.
- Validation rejects nonfinite values, out-of-map nodes, duplicate IDs, unsupported
  model parameters, nonpositive frequency/spacing, and grids above 500,000 TX-cell
  evaluations per model. Scenarios allow up to 32 transmitters and 500 receivers.
  Power is bounded to [−100, 100] dBm; antenna gain to [−100, 100] dBi; antenna height
  to [0, 10,000] m. At least one transmitter is required to simulate.
- Map point selection uses Streamlit's Plotly selection support; property inputs
  provide keyboard-accessible exact placement. No geographic mapping is included.

## Code and tests

`scenario.py` owns validation and JSON contracts. `ns3_adapter.py` is the only
module that imports/operates ns-3 C++ classes. `engine.py` samples grids, computes
links and curves, and isolates execution. `ui.py` builds figures; `app.py` owns
editor state; `export.py` packages immutable result snapshots; `cli.py` runs scenarios.

Tests cover validation/persistence, grid boundaries, Friis reference agreement,
distance/frequency/power scaling, Log-Distance exponent effects, deterministic
runs, receiver/transmitter moves, shared sampling coordinates, subprocess execution,
exports, and editor behavior. Integration tests exercise installed ns-3; they do not
silently substitute Python equations. Run `pytest -m 'not integration'` for checks
that do not require loading the C++ binding.

Follow-up scope: fading, obstacles, mobility, packets, and interference/SINR.
