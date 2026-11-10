"""Build the pinned ns-3 source and this repository's compiled propagation module."""

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from propagation_lab.ns3_adapter import NS3_COMMIT, NS3_VERSION, native_source_digest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "vendor" / "ns-3"


def command(*args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def compiler_headers(compiler):
    probe = command(compiler, "-E", "-x", "c++", "-", "-v", input="", capture_output=True,
                    text=True, env={**os.environ, "LC_ALL": "C"})
    headers = []
    for line in probe.stderr.splitlines():
        path = line.strip()
        if "/c++" in path and Path(path).is_dir():
            headers.append(path)
    flags = ["-std=c++20"]
    if headers:
        flags.append("-nostdinc++")
        for path in headers:
            flags.extend(["-isystem", path])
    return shlex.join(flags)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    compiler = os.environ.get("CXX") or shutil.which("g++-15") or shutil.which("c++")
    if not compiler:
        parser.error("Install a C++20 compiler and CMake; see README.md")
    if not SOURCE.exists():
        SOURCE.parent.mkdir(parents=True, exist_ok=True)
        command("git", "clone", "--depth", "1", "--branch", "ns-3.44",
                "https://github.com/nsnam/ns-3-dev-git.git", SOURCE)
    commit = command("git", "-C", SOURCE, "rev-parse", "HEAD", capture_output=True,
                     text=True).stdout.strip()
    if commit != NS3_COMMIT:
        parser.error(
            f"Expected ns-3 commit {NS3_COMMIT}; found {commit}. Checkout was not changed."
        )
    overlay = ROOT / "native" / "obstacle-propagation"
    for path in sorted(overlay.rglob("*")):
        if not path.is_file():
            continue
        target = SOURCE / "contrib" / "obstacle-propagation" / path.relative_to(overlay)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes() != path.read_bytes():
            shutil.copy2(path, target)
    env = {**os.environ, "EXTRA_CLING_ARGS": os.environ.get("EXTRA_CLING_ARGS")
           or compiler_headers(compiler)}
    cache = SOURCE / "cmake-cache"
    manifest = SOURCE / "build" / "propagation-lab-build.json"
    manifest.unlink(missing_ok=True)
    configure = [
        "cmake", "-S", SOURCE, "-B", cache,
        "-DCMAKE_BUILD_TYPE=Release", f"-DCMAKE_CXX_COMPILER={compiler}",
        f"-DPython3_EXECUTABLE={sys.executable}", "-DNS3_PYTHON_BINDINGS=ON",
        "-DNS3_ENABLED_MODULES=obstacle-propagation", "-DNS3_EXAMPLES=OFF", "-DNS3_TESTS=OFF",
        "-DNS3_WARNINGS_AS_ERRORS=OFF", "-DNS3_PRECOMPILE_HEADERS=OFF",
    ]
    if not cache.exists() and shutil.which("ninja"):
        configure.extend(["-G", "Ninja"])
    command(*configure, env=env)
    command("cmake", "--build", cache, "--target", "obstacle-propagation",
            "--parallel", args.jobs, env=env)
    if not (SOURCE / "build" / "bindings" / "python" / "ns" / "__init__.py").is_file():
        parser.error("CMake did not generate Python bindings; install Python development headers")
    diff = command("git", "-C", SOURCE, "diff", "HEAD", "--binary", capture_output=True).stdout
    compiler_version = command(compiler, "--version", capture_output=True, text=True).stdout
    metadata = {
        "ns3_version": NS3_VERSION,
        "ns3_commit": commit,
        "ns3_diff_sha256": hashlib.sha256(diff).hexdigest(),
        "native_sha256": native_source_digest(ROOT / "native"),
        "compiler": compiler_version.splitlines()[0],
        "cling_args": env["EXTRA_CLING_ARGS"],
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "build_type": "Release",
    }
    temporary = manifest.with_suffix(".tmp")
    temporary.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest)
    print(f"Built ns-3 {NS3_VERSION} + obstacle-propagation; run make smoke or make run.")


if __name__ == "__main__":
    main()
