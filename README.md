# Propagation Lab

Local wireless signal workbench: Python, Streamlit, Plotly, and a compiled
OMNeT++/INET propagation plugin. Place radios, walls, and rectangular objects;
inspect direct, attenuated, blocked, and single-bounce reflected paths.

## Build and run

Requirements: Linux, Git, Make, CMake, a C++17 compiler, and
[uv](https://docs.astral.sh/uv/). The build downloads pinned OMNeT++ 6.2.0 and
INET 4.6.0 sources; first build needs network access and can take a while.

```sh
make omnet      # Install Python dependencies and build OMNeT++/INET/plugin.
make smoke      # Check actual OMNeT++/INET Friis against an independent reference.
make run        # Build, then open Streamlit on 127.0.0.1:8501.
make test       # Build, then run unit, UI, and native integration tests.
make lint
```

Build parallelism defaults to two jobs. Override with `make omnet JOBS=4 CXX=g++`.
No working build is assumed until these commands succeed in your environment.

### Source and build ownership

- `scripts/build_omnet.py` clones OMNeT++ and INET into ignored `vendor/`, pinned
  to OMNeT++ commit `83e173e93acd814572c5db562027a0a66029ef06` and INET commit
  `2b58f3450aec99a9e3068fd4f7915230ebf59ae0`. Existing checkouts are not reset.
- Edit tracked plugin sources under `native/omnet/`, not generated vendor files.
  The helper configures headless OMNeT++, selects INET's physical-layer feature,
  builds INET, then compiles the plugin with CMake.
- Compiled libraries and the build manifest live in ignored `build/omnet/`.
  The manifest records upstream versions/commits, custom-source hash, compiler,
  and build profile. The adapter checks provenance and refuses stale builds.
- Runtime uses a headless `opp_run` Cmdenv network and a line-based worker
  protocol. Each isolated run starts a fresh process. There is no Python formula
  fallback; native integration tests fail when the build is missing or broken.

## Editor workflow

1. Add TX/RX nodes and edit frequency, power, gain, position, height, and sensitivity.
2. Add a wall or rectangle. Alternatively, choose its placement tool and click two
   map targets for endpoints/opposite corners. Exact geometry remains editable.
3. Configure object height, transmission blocking, attenuation, and reflection loss.
   Select an object to edit, translate, or delete it.
4. Select Friis or Log-Distance, configure sampling, and run the comparison.
5. Inspect receiver link status and stored paths. Reflected paths expose bounce
   coordinates, full 3D length, transmission/reflection loss, and RSS.
6. Save JSON to reopen a scenario, or download the complete result ZIP.

Edits invalidate old measurements. Invalid drafts cannot start a simulation. Map
selection uses a finite placement lattice; numeric inputs allow exact coordinates.
The heatmap displays one TX or maximum RSS across TXs, never combined transmitter
power or SINR. Transparent heatmap cells mean no valid path, not weak finite RSS.

## Propagation and reflection semantics

The compiled plugin calls authoritative INET propagation models and ports the
existing obstacle geometry unchanged. Friis uses INET `FreeSpacePathLoss` with
exponent 2 and clamps gain to at most 1. Log-Distance uses the same INET model
with the configured exponent, normalized at the configured reference distance,
then applies configured reference loss. Frequency intentionally cancels from
Log-Distance calibration, preserving fixed reference-loss behavior.

- Walls are finite vertical surfaces between two XY endpoints, from ground level
  to configured height. Rectangles are solid axis-aligned boxes with four vertical
  reflecting faces. Reversed corner ordering is supported.
- Direct paths intersecting an opaque object are rejected. Transmissive objects
  add configured attenuation once per object per straight path leg, regardless of
  thickness or crossed rectangle faces. Losses stack. Contact, grazing, and
  endpoints on a surface count conservatively as crossings.
- Each eligible face produces at most one specular single-bounce path using the
  image method. Bounce must lie inside the finite face and below its height;
  corner/endpoint reflections are excluded. Reflection legs must remain outside
  their reflecting box and pass other objects' blocking/attenuation checks.
- A reflected path evaluates the base model once at full 3D path length, then
  subtracts reflection loss and both legs' transmission losses. Main link distance
  remains direct TX–RX separation; `paths.csv` records traveled distances.
- Reflection loss is calibrated power loss in dB, not amplitude coefficient or
  Fresnel calculation. Disable reflection for purely absorbing objects. A 0 dB
  reflection loss means ideal mirror; normally pair it with blocked transmission.
  Material validation enforces `T + R <= 1`, where `T = 0` for blocked
  transmission or `10^(-attenuation_db/10)` otherwise, and `R = 0` when reflection
  is disabled or `10^(-reflection_loss_db/10)` otherwise.
- Valid paths from the same transmitter combine as an incoherent sum of powers.
  There is no phase-dependent interference. Paths from different transmitters stay
  separate; maximum RSS does not model interference.
- No path means zero received power: `-inf` dBm, `+inf` loss, `-inf` margin, and
  `status=no_path`. CSV preserves these values rather than inventing a sensitivity
  floor. Other statuses are `direct`, `attenuated`, `direct+reflected`, and `reflected`.
- With obstacles, `path_loss_db` is effective TX power minus total received power,
  excluding antenna gain. Distance plots use a fixed +X transect at TX height;
  they are not direction-independent curves when objects are present.

This is a geometric, static, constant-material approximation. It does not solve
Maxwell's equations or include diffraction, multiple bounces, roofs/ground
reflection, angle/frequency-dependent material coefficients, polarization, rough
scattering, packets, mobility, or interference/SINR. Material losses need
calibration for the intended frequency and environment. Near-field Friis samples
remain physically unreliable even when a mathematical value is returned.

### Base models and units

Coordinates/heights use meters; frequency uses Hz; power uses dBm; antenna gain
uses dBi; losses/margin use dB. Distances are 3D. TX gain is a constant isotropic
term; RX gain is 0 dBi. Margin is received power minus receiver sensitivity.

Friis configures INET `FreeSpacePathLoss` with exponent 2 and `SystemLoss` (linear factor at least 1).
Log-Distance sets exponent, reference distance, and reference loss. Default
reference loss 46.6777 dB at 1 m matches the prior 5.15 GHz reference, not an
automatic calculation from TX frequency. Set a calibrated reference loss. Seed
and duration persist but do not change stationary deterministic results.

## CLI and numerical exports

After `make omnet`, use the same environment:

```sh
.venv/bin/propagation-lab --smoke
.venv/bin/propagation-lab scenarios/reflection.json --compare --output results/reflection
.venv/bin/propagation-lab scenarios/free_space.json --output results/free_space
.venv/bin/propagation-lab scenarios/log_distance.json --compare
```

Smoke evaluates actual OMNeT++/INET Friis at 100 m and 2.4 GHz, checking
−60.052008056 dBm within 0.000001 dB. Result directories must be new; existing
output is never replaced. Each package contains:

```text
scenario.json
metadata.json
receiver_results.csv
coverage_grid.csv
distance_curves.csv
paths.csv
heatmap.html
```

The standalone HTML embeds Plotly. Charts/exports use one stored result snapshot,
not live edited settings. CSV columns remain stable. Metadata records exact model
attributes, custom model rules, objects, build provenance, seed, duration, grid
dimensions, simulation mode, and UTC timestamps. Comparison uses the same objects
with the selected base model and the other model's defaults, recording both.

## Validation, compatibility, and tests

Schema 1.1 adds obstacles. Existing schema 1.0 scenarios without obstacles load
automatically and export as 1.1; unsupported versions and 1.0 files claiming
objects are rejected. Node IDs remain valid; obstacle IDs share the same unique
namespace. JSON round-trips geometry and every material parameter, including
disabled reflection.

Validation rejects nonfinite numbers, out-of-map geometry, degenerate walls/boxes,
invalid coefficients, and incompatible model settings. Limits: 32 TXs, 500 RXs,
32 objects, 500,000 TX-cell samples per base model, and a 20-million weighted
obstacle-check budget. Increase grid spacing for larger scenes. Antenna/object
heights are bounded by 10,000 m. Power bounds remain [−100, 100] dBm. Grid
boundaries are included, with shorter final interval for non-divisible maps.
Default grid is 101 × 101 samples per TX. Each simulation has a 180 s timeout.

`make test` exercises actual compiled OMNeT++/INET, numerical Friis/scaling
references, attenuation/blockage, reflection geometry/visibility/height, material
validation, determinism, isolated workers, editor state, persistence, and exports.
`.venv/bin/python -m pytest -m 'not integration'` runs checks without native
integration. Integration tests do not skip a missing or broken native build.

## Licensing

OMNeT++ is licensed under Academic Public License 1.1. Its terms limit commercial
use and some funded research; check the current OMNeT++ license and obtain required
permissions for your use case. INET is LGPL-3.0. This project does not claim that
all research use is permitted or free of restrictions.
