# MVP Specification: Wireless Signal Propagation Simulator

Technical design document · Python + ns-3 + cppyy · Version 0.1

## 1. Project overview

Build an interactive wireless network simulator that allows users to create custom network scenarios, simulate radio signal propagation and attenuation using ns-3, and visualize how transmitter placement, frequency, distance, and environmental conditions affect received signal strength.

The application will be written primarily in Python, with `cppyy` providing access to ns-3's underlying C++ simulation libraries.

Primary goal: Let a user place transmitters and receivers on a 2D map, configure their radio characteristics, select a propagation model, run a simulation, and inspect the resulting signal coverage and path loss.

An important distinction: ns-3 models radio propagation through mathematical channel models. It does not, by default, solve Maxwell's equations or simulate physical wavefronts through an arbitrary environment. Therefore, this MVP will visualize signal power propagation, not electromagnetic wave interference or diffraction at the waveform level.

## 2. What the MVP should look like

Proposed scenario editor layout

Propagation Lab

Scenario 01

SCENARIO

\+ Transmitter

\+ Receiver

Nodes

&#x20;TX-1

&#x20;RX-1

&#x20;RX-2

Properties

Selected: TX-1

Frequency

2.4 GHz

TX Power

20 dBm

Propagation

Friis

Strong → Weak RSS

Illustrative UI

The interface should have three primary sections: scenario objects on the left, the interactive map in the center, and configuration properties on the right. The center map becomes a received-signal-strength heatmap after a simulation.

## 3. MVP feature requirements

| Feature                   | MVP requirements                                             | Priority |
| ------------------------- | ------------------------------------------------------------ | -------- |
| Scenario editor           | Add, delete, move and select TX/RX nodes on a 2D map         | P0       |
| Transmitter configuration | Frequency, transmit power, antenna height                    | P0       |
| Receiver configuration    | Position, height, sensitivity threshold                      | P0       |
| Propagation models        | Friis and Log-Distance                                       | P0       |
| Simulation engine         | Run ns-3 models through Python and `cppyy`                   | P0       |
| Signal heatmap            | Display received power in dBm over a spatial grid            | P0       |
| Link inspector            | Distance, path loss, RSS and link margin                     | P0       |
| Scenario persistence      | Import/export JSON scenarios                                 | P0       |
| Model comparison          | Compare the same scenario using different loss models        | P1       |
| Interference and SINR     | Multiple simultaneous transmitters and receiver interference | P1       |
| Obstacles                 | Buildings and wall attenuation                               | P2       |
| Mobility                  | Moving receivers and time-dependent results                  | P2       |
| Packet simulation         | Actual Wi-Fi traffic, delivery ratio and throughput          | P2       |

P0 defines the first working release. P1 and P2 are follow-up iterations.

## 4. Technical architecture

Use Python for the application, data model, user interface, execution orchestration and visualization. Keep C++ isolated behind the ns-3 Python binding.

Python UI — Streamlit

Scenario editor · Node placement · Model settings · Heatmap · Results

Scenario Manager — Python

Pydantic validation · JSON persistence · Configuration translation

Simulation Runner — Python

Generate sampling grid · Select propagation model · Execute simulation

cppyy / ns-3 Python bindings

ns3::MobilityModel · ns3::PropagationLossModel · ns3::Simulator

Result Processing — Python

NumPy arrays · DataFrames · Plotly heatmap · CSV / JSON export

### Recommended technology stack

| Component            | Technology | Reason                                         |
| -------------------- | ---------- | ---------------------------------------------- |
| Language             | Python 3   | Main implementation language                   |
| Simulator            | ns-3       | C++ discrete-event simulation and radio models |
| Bindings             | `cppyy`    | Access ns-3 C++ classes                        |
| UI                   | Streamlit  | Fast Python-only MVP                           |
| Visualization        | Plotly     | Interactive spatial heatmaps and charts        |
| Data validation      | Pydantic   | Structured scenario schemas                    |
| Numerical operations | NumPy      | Sampling grids, result matrices                |
| Data export          | Pandas     | CSV and analysis                               |
| Testing              | pytest     | Unit and integration tests                     |

For the first release, use a single local application rather than a distributed frontend/backend deployment.

Environment compatibility: ns-3 has used Cppyy-based Python bindings since version 3.37. ns-3's 3.46 documentation recommends `cppyy==3.5.0`. Pin the ns-3 version and use its matching Python environment to avoid ABI and reflection problems.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://www.nsnam.org\&sz=32)

ns-3+1



## 5. Scenario creator

### 5.1 Coordinate system and canvas

Use a Cartesian 2D map with coordinates in meters. The internal node position remains 3D, allowing antenna height to affect distance calculations.

Default canvas properties:

| Property            | Default  | Configurable |
| ------------------- | -------- | ------------ |
| Map width           | 500 m    | Yes          |
| Map height          | 500 m    | Yes          |
| Grid spacing        | 5 m      | Yes          |
| Simulation duration | 1 second | Yes          |
| Transmitters        | 1        | Yes          |
| Receivers           | 2        | Yes          |
| Frequency           | 2.4 GHz  | Yes          |
| Transmit power      | 20 dBm   | Yes          |

The map is a coordinate plane, not a geographic map. Real-world street maps and terrain importing are excluded from the first version.

### 5.2 Node types

Transmitter (TX)

A transmitter represents a wireless radio source. Users configure:

- ID and display name.
- Position `(x, y, z)` in meters.
- Operating frequency in Hz.
- Transmit power in dBm.
- Optional antenna gain in dBi, default 0.

Receiver (RX)

A receiver represents a measurement point. Users configure its position, name and receiver sensitivity threshold.

The simulator should calculate received power and path loss for every TX–RX combination.

### 5.3 Example scenario configuration

The following is the proposed JSON data contract for saving, loading and running scenarios.

```

{
  "schema_version": "1.0",
  "name": "Free Space Propagation",
  "environment": {
    "width_m": 500,
    "height_m": 500
  },
  "transmitters": [
    {
      "id": "tx_1",
      "position": [100, 250, 10],
      "frequency_hz": 2400000000,
      "power_dbm": 20,
      "antenna_gain_dbi": 0
    }
  ],
  "receivers": [
    {
      "id": "rx_1",
      "position": [200, 250, 1.5],
      "sensitivity_dbm": -90
    },
    {
      "id": "rx_2",
      "position": [400, 250, 1.5],
      "sensitivity_dbm": -90
    }
  ],
  "propagation": {
    "model": "friis",
    "parameters": {
      "system_loss": 1.0
    }
  },
  "sampling": {
    "resolution_m": 5,
    "receiver_height_m": 1.5
  },
  "simulation": {
    "duration_s": 1.0,
    "seed": 42
  }
}

```

The scenario manager must validate node IDs, coordinates, positive frequency, power bounds, and compatible model parameters before starting any simulation.

## 6. Propagation simulation engine

The first release should support two models.

Friis Free-Space Model

Models signal attenuation in unobstructed free space, appropriate as an idealized baseline.

\\[ L\_{\mathrm{FSPL}} =20\log\_{10}\left(\frac{4\pi df}{c}\right) \\]

\\(d\\): distance in meters, \\(f\\): frequency in Hz, \\(c\\): speed of light.

Log-Distance Model

Represents attenuation using a configurable path-loss exponent.

\\[ L(d)=L(d_0)+10n\log\_{10}\left(\frac{d}{d_0}\right) \\]

\\(n\\): path-loss exponent, \\(d_0\\): reference distance.

A larger exponent generally produces faster signal attenuation as distance increases.

Both models are available in ns-3's propagation module.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://www2.nsnam.org\&sz=32)

Model Library+1



### 6.1 Using cppyy with ns-3

The simulation engine must use actual ns-3 propagation classes, not independent Python approximations for its authoritative simulation outputs.

The ns-3 installation should first expose its Python bindings. The application can then import the `ns` package, which uses `cppyy` to access C++ libraries.

Representative integration sketch:

```
import cppyyfrom ns import nsdef calculate_rx_power(    tx_position,    rx_position,    tx_power_dbm,    frequency_hz,):    tx_mobility = ns.CreateObject[        ns.ConstantPositionMobilityModel    ]()    rx_mobility = ns.CreateObject[        ns.ConstantPositionMobilityModel    ]()    tx_mobility.SetPosition(        ns.Vector(*tx_position)    )    rx_mobility.SetPosition(        ns.Vector(*rx_position)    )    model = ns.CreateObject[        ns.FriisPropagationLossModel    ]()    model.SetAttribute(        "Frequency",        ns.DoubleValue(frequency_hz)
```

This is an integration sketch, not yet runtime-tested against a pinned ns-3 installation. In particular, object creation and pointer conversion should be confirmed with the selected release.

This call evaluates a channel model directly. It does not transmit packets, schedule radio events or produce a time-dependent waveform. That distinction should be explicit in the application.

### 6.2 Simulation execution workflow

1. Validate scenario

   Parse JSON, enforce supported model configurations, and reject invalid coordinates and parameter combinations.
2. Initialize ns-3

   Create mobility objects for transmitter and receiver measurement positions. Initialize the selected propagation model and its attributes.
3. Generate sampling points

   Build a grid over the scenario area at the configured resolution.
4. Calculate received power

   For each transmitter and grid point, invoke the ns-3 propagation loss calculation.
5. Calculate link metrics

   Derive path loss and link margin. Preserve separate received-power values for different transmitters.
6. Store results

   Export metadata, node-link measurements and grid measurements in structured formats.
7. Visualize

   Render heatmaps, receiver markers, a selected-link inspector and distance-versus-power plots.

For a 500 m × 500 m map sampled every 5 m, the engine evaluates approximately 10,201 grid locations per transmitter.

For deterministic models, stationary positions and unchanged parameters produce the same result on every evaluation. A duration parameter does not change those results; it becomes meaningful in later versions with mobility, stochastic fading or packet events.

## 7. Signal analysis and visualization

### 7.1 Received signal strength heatmap

A heatmap is the primary output.

Illustrative signal strength by distance

Weaker

Stronger

Conceptual heatmap only. Actual colors must come from computed ns-3 power values, with a numerical dBm legend.

The heatmap should support cursor inspection and provide precise coordinates and received power for the selected cell.

For multiple transmitters, the MVP should display one transmitter at a time or the maximum received power across transmitters. Maximum RSS must not be confused with combined RF power or interference.

### 7.2 Link inspector

When the user clicks a receiver, show its measurements relative to the selected transmitter.

TX-1 → RX-1

Illustrative values

Distance

## 100 m

Received power

## −60 dBm

Path loss

## 80 dB

Link margin

## 30 dB

Values are for UI demonstration, not a simulation output.

Computed metrics:

\\[ P\_{\mathrm{RX}}=P\_{\mathrm{TX}}+G\_{\mathrm{TX}}+G\_{\mathrm{RX}}-L \\]

\\[ \text{Link margin}=P\_{\mathrm{RX}}-P\_{\mathrm{sensitivity}} \\]

In the first version, gains are treated as constant isotropic-antenna terms. The link inspector should also show the exact propagation model and parameters used.

### 7.3 Additional graphs

Support a plot of received power against distance and a comparison overlay between Friis and Log-Distance.

Illustrative comparison of path loss with distance

Example analytical curves, not results from an executed ns-3 simulation.

Free space (n=2)Log-distance (n=3)

40 dB60 dB80 dB100 dB120 dB102050100200500

These plots make it possible to observe how the selected propagation model affects signal loss without changing the node layout.

## 8. Results and export

Each simulation should generate a reproducible result package.

```
results/
  scenario_001/
    scenario.json
    metadata.json
    receiver_results.csv
    coverage_grid.csv
    heatmap.html
```

Recommended CSV format:

| x_m | y_m | tx_id | rx_power_dbm | path_loss_db |
| --- | --- | ----- | ------------ | ------------ |
| 0   | 0   | tx_1  | …            | …            |
| 5   | 0   | tx_1  | …            | …            |
| 10  | 0   | tx_1  | …            | …            |

Metadata must include ns-3 version, selected model, attributes, random seed, simulation mode and timestamps. This allows results to be reproduced and compared later.

## 9. Suggested codebase structure

```
propagation-lab/
├── app.py
├── pyproject.toml
├── README.md
│
├── src/
│   └── propagation_lab/
│       ├── models/
│       │   ├── scenario.py
│       │   ├── node.py
│       │   └── results.py
│       │
│       ├── engine/
│       │   ├── ns3_adapter.py
│       │   ├── propagation.py
│       │   ├── grid_sampler.py
│       │   └── runner.py
│       │
│       ├── services/
│       │   ├── scenario_store.py
│       │   ├── validation.py
│       │   └── export.py
│       │
│       └── ui/
│           ├── editor.py
│           ├── property_panel.py
│           ├── heatmap.py
│           └── charts.py
│
├── scenarios/
│   ├── free_space.json
│   └── log_distance.json
│
└── tests/
    ├── test_scenario.py
    ├── test_propagation.py
    ├── test_grid.py
    └── test_integration.py
```

The `ns3_adapter.py` module must be the only place that knows how to construct and operate ns-3 C++ objects. The remaining code should work with ordinary Python objects.

This separation is particularly important for testing and future compatibility when the project upgrades ns-3.

## 10. Development milestones

Milestone 1 — ns-3 integration

Establish a working environment and load ns-3 through Python.

Deliverable: A CLI program that creates a transmitter and receiver, selects Friis propagation, and prints received power calculated by ns-3.

Acceptance: Output agrees with an independently calculated Friis reference within a defined numerical tolerance for distances in the model's valid operating range.

Milestone 2 — Scenario and grid engine

Implement Pydantic schemas, JSON loading and the coordinate sampling system.

Deliverable: Run a complete scenario from JSON and export the resulting signal-strength grid.

Acceptance: Increasing transmitter-receiver distance reduces received power for default deterministic models.

Milestone 3 — Interactive scenario creator

Implement map-based node placement, property editing, scenario validation and JSON persistence.

Deliverable: A scenario can be created without manually editing code or JSON.

Acceptance: Saving and reopening a scenario preserves every supported parameter.

Milestone 4 — Visualization and model comparison

Implement heatmaps, receiver metrics and plots for comparing propagation models.

Deliverable: A complete local application with scenario creation, execution, visualization and exports.

Acceptance: All output charts are generated from the same stored simulation results, with correct units and model metadata.

## 11. Acceptance testing

| Test                            | Expected behavior                                                          |
| ------------------------------- | -------------------------------------------------------------------------- |
| Friis at 2.4 GHz                | Results follow free-space loss with distance                               |
| Double distance                 | Path loss increases by approximately 6.02 dB in the far-field Friis regime |
| Double frequency                | Path loss increases by approximately 6.02 dB in the same regime            |
| Increase TX power by 10 dB      | Received power increases by 10 dB for deterministic linear loss models     |
| Log-Distance exponent increases | Greater loss at distances beyond the reference distance                    |
| Move receiver                   | Heatmap remains unchanged, link metrics update                             |
| Change transmitter position     | Signal heatmap changes correspondingly                                     |
| Load saved scenario             | Input values restore correctly                                             |
| Invalid frequency               | Scenario validation rejects it                                             |
| Same deterministic scenario     | Repeated runs yield equivalent results                                     |
| Different sampling resolution   | Measurements at shared coordinates remain consistent                       |

Use these as automated tests where possible, not merely manual checks.

## 12. Limitations and design decisions

There are four technical decisions worth establishing from the beginning.

First, propagation is not packet simulation. The MVP evaluates signal attenuation using ns-3's propagation models. It is not yet simulating TCP, IP, Wi-Fi association, retransmissions or throughput. A future extension can use ns-3 Wi-Fi PHY/channel models and actual packet transmissions.

Second, arbitrary obstacle rendering is not equivalent to obstacle simulation. Drawing a wall on a map does not automatically cause attenuation in ns-3. Obstacle geometry requires a suitable building-aware model or an explicit validated loss model. Arbitrary per-wall attenuation is excluded from this release.

Third, the initial heatmap is static. For stationary transmitters and receivers using deterministic path-loss models, a heatmap represents spatial signal power rather than temporal evolution. Animated radio-wave fronts would be a separate, illustrative feature and should not be presented as physical wave propagation computed by ns-3.

Fourth, execution isolation matters. Cppyy and C++ simulation state are more difficult to cleanly reset than ordinary Python application state. A dedicated worker process per simulation run is preferable as the system grows. The UI should not hold long-lived C++ objects in Streamlit session state.

## 13. Future extensions

After the MVP works reliably, the following progression would add meaningful scientific and networking capabilities.

| Release | Added capability                  | Relevant ns-3 concepts               |
| ------- | --------------------------------- | ------------------------------------ |
| v0.2    | Fading and stochastic propagation | Nakagami, random loss                |
| v0.3    | Indoor/urban scenarios            | Buildings, 3GPP channel models       |
| v0.4    | Dynamic receiver mobility         | Mobility models, scheduled events    |
| v0.5    | Actual Wi-Fi communication        | Wi-Fi PHY/MAC, applications          |
| v0.6    | Interference and SINR analysis    | Spectrum-aware channel modeling      |
| v1.0    | Network performance analysis      | Packet delivery, throughput, latency |

For frequency-dependent power spectral density and interference analysis, ns-3's Spectrum module provides dedicated channel abstractions. Those are more appropriate than trying to derive full interference behavior from independent RSS heatmaps.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://fossies.org\&sz=32)

Fossies



## 14. Definition of done

The MVP is complete when a user can open the application, create a scenario by placing at least one transmitter and multiple receivers, configure Friis or Log-Distance propagation, run the simulation through ns-3's C++ libraries using `cppyy`, and see a scientifically interpretable RSS heatmap.

The user must also be able to inspect individual links, compare the selected models, save and reopen a scenario, and export numerical results.

Recommended development order: Prove the ns-3/C++ binding works before building the UI. Binding compatibility is the biggest initial technical risk. Once a reliable Python-to-ns-3 calculation is working, the scenario editor and heatmap are comparatively straightforward.

This scope produces a useful signal-propagation research tool without prematurely building a full network emulator or an electromagnetic field solver.

Suggested Obsidian note — Idyll: `Propagation Lab MVP: Python/Streamlit scenario editor + cppyy/ns-3 propagation engine; v0.1 focuses on static RSS/path-loss heatmaps, not physical wavefronts or packet simulation.`
