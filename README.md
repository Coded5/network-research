# Propagation Lab

Local wireless signal workbench: Python, Streamlit, Plotly, and compiled ns-3 C++
propagation models accessed through cppyy. Place radios, walls, and rectangular
objects; inspect direct, attenuated, blocked, and single-bounce reflected paths.

## Build and run

Requirements: Linux, Git, Make, CMake 3.13+, a C++20 compiler with compatible
standard-library headers, and [uv](https://docs.astral.sh/uv/). Ninja is optional.
Python 3.12 and cppyy 3.5.0 are pinned by the project environment/lockfile.
Python development headers and libraries must be available to CMake; uv's managed
Python 3.12 includes them. No ns-3 PyPI wheel is used.

```sh
make ns3       # Install dependencies, clone pinned ns-3, configure, compile C++.
make smoke     # Verify compiled ns-3 Friis against an independent reference.
make run       # Build incrementally, then open Streamlit on 127.0.0.1:8501.
make test      # Build, then run unit, UI, and real C++ integration tests.
make lint
```

First build needs network access and takes longer than incremental builds. Default
compilation parallelism is two jobs. Override with `make ns3 JOBS=4 CXX=g++-15`.
The build helper prefers `g++-15` when installed, otherwise `c++`; `CXX` takes precedence.
Tested here: GCC 15.3.0, Python 3.12.13, cppyy 3.5.0, ns-3 3.44.

### Source and build ownership

- `scripts/build_ns3.py` clones ns-3 into ignored `vendor/ns-3`, pinned to commit
  `43dce6710b8df69685e3479c1d33a571dda714ea` (release `ns-3.44`). It does not reset
  an existing checkout; a different commit produces an error instead.
- Edit the tracked C++ files under `native/obstacle-propagation/`, **not** their
  generated copies under `vendor/`. `make ns3` copies changed files into ns-3's
  `contrib/obstacle-propagation` and invokes CMake's incremental build.
- `native/obstacle-propagation/CMakeLists.txt` defines the ns-3 module and its
  propagation/mobility dependencies. The helper builds the `obstacle-propagation`
  target and required ns-3 libraries, with Python bindings enabled.
- Shared libraries, generated headers, and the Python `ns` package live under
  `vendor/ns-3/build/`. cppyy reflects the compiled class through these bindings;
  the application does not implement an independent Python propagation fallback.
- The adapter selects this build explicitly and refuses a preloaded foreign `ns`
  package. It checks the custom source fingerprint and Python ABI before loading.
  After a C++ edit, rebuild with `make ns3` and restart any running application.
  Workers use a fresh process for every simulation.
- A generated build manifest records the ns-3 commit, tracked upstream diff hash,
  custom source hash, compiler, build profile, Python ABI, and Cling arguments.
  Result metadata embeds this manifest.

cppyy's bundled Cling cannot parse this host's GCC 16 C++ headers. The helper records
the selected compiler's C++ include paths and the adapter applies those paths before
loading cppyy. GCC 15 works here without a manual environment override. An explicit
`EXTRA_CLING_ARGS` still takes precedence; retain `-std=c++20` if you override it.
Run `make smoke` after changing compiler or Python environment. There is no silent
fallback to a wheel or analytical approximation.

## Editor workflow

1. Add TX/RX nodes and edit frequency, power, gain, position, height, and sensitivity.
2. Add a wall or rectangle. Alternatively, choose its placement tool and click two
   map targets for endpoints/opposite corners. Exact geometry remains editable.
3. Configure the object's height, transmission blocking, attenuation, and reflection
   loss. Select an object to edit, translate, or delete it.
4. Select Friis or Log-Distance, configure sampling, and run the comparison.
5. Inspect receiver link status and individual stored paths. Reflected paths expose
   bounce coordinates, full 3D length, transmission loss, reflection loss, and RSS.
6. Save JSON to reopen a scenario, or download the complete result ZIP.

Edits invalidate old measurements. Invalid drafts cannot start a simulation. Map
selection uses a finite placement lattice; numeric inputs allow exact coordinates.
The heatmap displays one TX or maximum RSS across TXs, never combined transmitter
power or SINR. Transparent heatmap cells mean no valid path, not weak finite RSS.

## Propagation and reflection semantics

`ns3::ObstaclePropagationLossModel` wraps the selected ns-3 Friis/Log-Distance model.
All authoritative obstacle intersection, reflection geometry, and path-power
calculations execute in compiled C++, including grid samples.

- Walls are finite vertical surfaces between two XY endpoints, from ground level
  to the configured height. Rectangles are solid axis-aligned boxes, with four
  vertical reflecting faces. Reversed corner ordering is supported.
- Direct paths intersecting an opaque object are rejected. Transmissive objects
  add their configured attenuation **once per object per straight path leg**,
  regardless of thickness or number of crossed rectangle faces. Losses stack.
  Contact, grazing, and endpoints on a surface count conservatively as crossings.
- Each eligible face produces at most one specular single-bounce path using the
  image method. The bounce must lie inside the finite face, within its height;
  corner/endpoint reflections are excluded. Reflection legs must remain outside
  their own reflecting box and pass other objects' blocking/attenuation checks.
- A reflected path evaluates the base model **once at its full 3D path length**,
  then subtracts reflection loss and both legs' transmission losses. The distance
  in the main link table remains direct TX–RX separation; `paths.csv` records
  actual traveled distances.
- Reflection loss is a calibrated **power loss in dB**, not an amplitude coefficient
  or Fresnel calculation. Disable reflection for a purely absorbing object.
  A 0 dB reflection loss means an ideal mirror; normally pair it with blocked transmission.
  Material validation enforces `T + R <= 1`, where
  `T = 0` for blocked transmission or `10^(-attenuation_db/10)` otherwise, and
  `R = 0` when reflection is disabled or `10^(-reflection_loss_db/10)` otherwise.
- Valid paths from the **same transmitter** combine as an incoherent sum of powers.
  There is no phase-dependent constructive/destructive interference. Paths from
  different transmitters stay separate; maximum RSS does not model interference.
- No path means zero received power: `-inf` dBm, `+inf` loss, `-inf` margin, and
  `status=no_path`. CSV preserves these values rather than inventing a sensitivity
  floor. Other statuses are `direct`, `attenuated`, `direct+reflected`, and `reflected`.
- With obstacles, `path_loss_db` is effective TX power minus total received power,
  excluding antenna gain. Distance plots use a fixed +X transect at TX height;
  they are not direction-independent curves when objects are present.

This is a geometric, static, constant-material approximation. It does **not** solve
Maxwell's equations or include diffraction, multiple bounces, roofs/ground reflection,
angle/frequency-dependent material coefficients, polarization, rough scattering,
packets, mobility, or interference/SINR. Material losses need calibration for the
intended frequency and environment. Near-field Friis samples remain physically
unreliable even when a mathematical value is returned.

### Base models and units

Coordinates and heights are meters; frequency is Hz; powers are dBm; antenna gain
is dBi; losses and margin are dB. Distances are 3D. TX gain is a constant isotropic
term; RX gain is 0 dBi. Margin is received power minus receiver sensitivity.

Friis explicitly sets `Frequency`, `SystemLoss` (linear factor at least 1), and
`MinLoss=0` dB. Log-Distance sets exponent, reference distance, and reference loss.
Its default 46.6777 dB at 1 m matches ns-3's 5.15 GHz reference, **not** an automatic
calculation from TX frequency. Set a calibrated reference loss. ns-3 3.44 applies
reference loss at/below the reference distance, with additional loss beyond it.
Seed and duration persist but do not change these stationary deterministic results.

## CLI and numerical exports

After `make ns3`, use the same environment:

```sh
uv run propagation-lab --smoke
uv run propagation-lab scenarios/reflection.json --compare --output results/reflection
uv run propagation-lab scenarios/free_space.json --output results/free_space
uv run propagation-lab scenarios/log_distance.json --compare
```

Smoke evaluates actual ns-3 Friis at 100 m and 2.4 GHz, checking
−60.052008056 dBm within 0.000001 dB. Result directories must be new; existing output
is never replaced. Each package contains:

```text
scenario.json
metadata.json
receiver_results.csv
coverage_grid.csv
distance_curves.csv
paths.csv
heatmap.html
```

The standalone HTML embeds Plotly. All charts/exports use the same stored result
snapshot, not live edited settings. CSVs retain model and TX IDs; path rows also
identify receiver and reflecting obstacle. Metadata records exact base-model
attributes, custom model rules, objects, build provenance, seed, duration, grid
dimensions, simulation mode, and UTC timestamps. Comparison uses the same objects
with the selected base model and the other model's defaults, recording both.

## Validation, compatibility, and tests

Schema **1.1** adds obstacles. Existing schema 1.0 scenarios without obstacles load
automatically and export as 1.1; unsupported versions and 1.0 files claiming objects
are rejected. Node IDs remain valid; obstacle IDs share the same unique namespace.
JSON round-trips geometry and every material parameter, including disabled reflection.

Validation rejects nonfinite numbers, out-of-map geometry, degenerate walls/boxes,
invalid coefficients, and incompatible model settings. Limits: 32 TXs, 500 RXs,
32 objects, 500,000 TX-cell samples per base model, and a 20-million weighted
obstacle-check budget. Increase grid spacing for larger scenes. Antenna/object
heights are bounded by 10,000 m. Power bounds remain [−100, 100] dBm.
Grid boundaries are included, with a shorter final interval for non-divisible maps.
The default grid remains 101 × 101 samples per TX. Each simulation has a 180 s timeout.

`make test` exercises actual compiled ns-3, numerical Friis/scaling references,
attenuation and blockage, reflection geometry/visibility/height, material validation,
determinism, isolated workers, editor state, persistence, and exports.
`uv run pytest -m 'not integration'` runs checks that do not load the C++ binding.
Integration tests do not skip a broken or missing native build.
