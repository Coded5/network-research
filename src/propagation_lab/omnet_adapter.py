"""Process boundary for compiled OMNeT++/INET propagation calculations."""

import hashlib
import json
import math
import os
import select
import subprocess
import tempfile
import time
from pathlib import Path

from propagation_lab.scenario import Friis, Obstacle, Propagation, Transmitter

OMNET_VERSION = "6.2.0"
OMNET_COMMIT = "83e173e93acd814572c5db562027a0a66029ef06"
INET_VERSION = "4.6.0"
INET_COMMIT = "2b58f3450aec99a9e3068fd4f7915230ebf59ae0"
ROOT = Path(__file__).resolve().parents[2]


def native_source_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in {".cc", ".h", ".ned", ".ini", ".cmake"} and (
            path.name != "CMakeLists.txt"
        ):
            continue
        digest.update(str(path.relative_to(directory)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class OmnetAdapter:
    def __init__(self, seed: int):
        build = ROOT / "build" / "omnet"
        manifest = build / "build.json"
        if not manifest.is_file():
            raise RuntimeError("OMNeT++/INET build is missing. Run make omnet first.")
        try:
            self.build_info = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError("Cannot read native build manifest. Run make omnet.") from exc
        if (
            self.build_info.get("omnet_commit") != OMNET_COMMIT
            or self.build_info.get("inet_commit") != INET_COMMIT
            or self.build_info.get("native_sha256")
            != native_source_digest(ROOT / "native" / "omnet")
        ):
            raise RuntimeError("OMNeT++/INET build is stale. Run make omnet.")
        self.version = self.build_info["omnet_version"]
        self.inet_version = self.build_info["inet_version"]
        omnet, inet = ROOT / "vendor" / "omnetpp", ROOT / "vendor" / "inet"
        self._stderr = tempfile.TemporaryFile()
        self._buffer = b""
        self._logs = []
        self._active = None
        self._next_channel = 0
        native = ROOT / "native" / "omnet"
        command = [
            str(omnet / "bin" / "opp_run"), "-u", "Cmdenv",
            "-n", os.pathsep.join([str(native), str(inet / "src")]),
            "-l", str(inet / "src" / "INET"),
            "-l", str(build / "propagation_lab_omnet"),
            "-f", str(native / "omnetpp.ini"), f"--seed-set={seed}",
            f"--result-dir={build / 'results'}",
        ]
        env = {**os.environ, "LD_LIBRARY_PATH": os.pathsep.join(
            [str(omnet / "lib"), str(inet / "src"), os.environ.get("LD_LIBRARY_PATH", "")]
        )}
        try:
            self._process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._stderr,
                bufsize=0, cwd=build, env=env,
            )
            if self._response() != ["READY", "1"]:
                raise RuntimeError("Unsupported OMNeT++ worker protocol")
        except (OSError, RuntimeError) as exc:
            self.close()
            raise RuntimeError(f"Cannot start OMNeT++/INET worker. Run make omnet. {exc}") from exc

    def _failure(self, message):
        self._stderr.seek(0)
        errors = self._stderr.read().decode("utf-8", errors="replace")[-4000:]
        return RuntimeError(f"{message}\n{''.join(self._logs[-20:])}{errors}")

    def _response(self):
        deadline = time.monotonic() + 30
        while True:
            while b"\n" not in self._buffer:
                remaining = deadline - time.monotonic()
                ready, _, _ = select.select([self._process.stdout], [], [], max(0, remaining))
                if remaining <= 0 or not ready:
                    raise self._failure("OMNeT++ worker exceeded its 30-second response timeout")
                chunk = os.read(self._process.stdout.fileno(), 65536)
                if not chunk:
                    raise self._failure("OMNeT++/INET worker ended before returning a result")
                self._buffer += chunk
                if len(self._buffer) > 1_048_576:
                    raise self._failure("OMNeT++ worker returned an oversized response")
            line, self._buffer = self._buffer.split(b"\n", 1)
            text = line.decode("utf-8", errors="replace")
            if text.startswith("PLAB "):
                return text[5:].split()
            self._logs.append(text + "\n")
            self._logs = self._logs[-20:]

    def _send(self, command):
        try:
            self._process.stdin.write(command.encode("ascii"))
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise self._failure("Cannot send a request to the OMNeT++ worker") from exc

    def channel(self, tx: Transmitter, propagation: Propagation,
                obstacles: list[Obstacle] | None = None):
        tx_values = Transmitter.model_validate(tx.model_dump())
        objects = [Obstacle.model_validate(obj.model_dump()) for obj in obstacles or []]
        self._next_channel += 1
        channel_id = self._next_channel
        if isinstance(propagation, Friis):
            system_loss = propagation.parameters.system_loss
            exponent, reference_distance, reference_loss = 3, 1, 46.6777
            attributes = {
                "Frequency": tx_values.frequency_hz,
                "Alpha": 2.0,
                "SystemLoss": system_loss,
                "Implementation": "inet::physicallayer::FreeSpacePathLoss",
            }
        else:
            system_loss = 1
            parameters = propagation.parameters
            exponent = parameters.exponent
            reference_distance = parameters.reference_distance_m
            reference_loss = parameters.reference_loss_db
            attributes = {
                "Exponent": exponent, "ReferenceDistance": reference_distance,
                "ReferenceLoss": reference_loss,
                "Implementation": "INET FreeSpacePathLoss normalized to explicit reference loss",
            }
        if objects:
            attributes["Wrapper"] = "propagationlab::ObstaclePropagation"

        def rx_power(position, include_paths=False):
            input_power = float(tx.power_dbm + tx.antenna_gain_dbi)
            coordinates = tuple(float(value) for value in position)
            if len(coordinates) != 3 or not all(
                math.isfinite(v) for v in (*coordinates, input_power)
            ):
                raise ValueError("Positions and input power must be finite")
            if self._active != (channel_id, input_power):
                values = [
                    propagation.model, *tx_values.position, input_power, tx_values.frequency_hz,
                    system_loss, exponent, reference_distance, reference_loss, len(objects),
                ]
                request = "CONFIG " + " ".join(map(str, values)) + "\n"
                for obj in objects:
                    request += " ".join(map(str, [
                        int(obj.kind == "rectangle"), *obj.start, *obj.end, obj.height_m,
                        int(obj.blocks), obj.attenuation_db,
                        -1 if obj.reflection_loss_db is None else obj.reflection_loss_db,
                    ])) + "\n"
                self._send(request)
                if self._response() != ["OK"]:
                    raise self._failure("Invalid OMNeT++ channel configuration response")
                self._active = (channel_id, input_power)
            self._send("POWER " + " ".join(map(str, [*coordinates, int(include_paths)])) + "\n")
            response = self._response()
            if len(response) != 3 or response[0] != "POWER":
                raise self._failure("Invalid OMNeT++ power response")
            power, count = float(response[1]), int(response[2])
            if (not math.isfinite(power) and power != -math.inf) or not 0 <= count <= 129:
                raise self._failure("Invalid received power or path count")
            if (power == -math.inf) != (count == 0):
                raise self._failure("Inconsistent OMNeT++ no-path result")
            paths = []
            for _ in range(count if include_paths else 0):
                row = self._response()
                if len(row) != 10 or row[0] != "PATH" or row[1] not in ("direct", "reflected"):
                    raise self._failure("Invalid OMNeT++ path response")
                kind, index = row[1], int(row[2])
                values = [float(value) for value in row[3:]]
                if not all(math.isfinite(value) for value in values):
                    raise self._failure("Nonfinite OMNeT++ path measurements")
                reflected = kind == "reflected"
                if (reflected and not 0 <= index < len(objects)) or (not reflected and index != -1):
                    raise self._failure("Invalid reflecting object index")
                distance, rss, reflection, transmission, x, y, z = values
                paths.append({
                    "kind": kind, "obstacle_id": objects[index].id if reflected else "",
                    "distance_m": distance, "rx_power_dbm": rss,
                    "reflection_loss_db": reflection, "transmission_loss_db": transmission,
                    "bounce_x_m": x if reflected else None,
                    "bounce_y_m": y if reflected else None,
                    "bounce_z_m": z if reflected else None,
                })
            if self._response() != ["END"]:
                raise self._failure("Missing OMNeT++ response terminator")
            return (power, paths) if include_paths else power

        return rx_power, attributes

    def close(self):
        process = getattr(self, "_process", None)
        if process:
            if process.poll() is None:
                try:
                    self._send("QUIT\n")
                    process.wait(timeout=5)
                except (OSError, RuntimeError, subprocess.TimeoutExpired):
                    process.kill()
                    process.wait()
            process.stdin.close()
            process.stdout.close()
            self._process = None
        self._stderr.close()
