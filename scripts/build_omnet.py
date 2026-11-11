"""Build pinned OMNeT++/INET sources and the native propagation plugin."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from propagation_lab.omnet_adapter import (
    INET_COMMIT,
    INET_VERSION,
    OMNET_COMMIT,
    OMNET_VERSION,
    native_source_digest,
)

ROOT = Path(__file__).resolve().parents[1]
OMNET = ROOT / "vendor" / "omnetpp"
INET = ROOT / "vendor" / "inet"
NATIVE = ROOT / "native" / "omnet"
BUILD = ROOT / "build" / "omnet"
MANIFEST = BUILD / "build.json"


def command(*args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def pin(source, url, tag, commit):
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        command("git", "clone", "--depth", "1", "--branch", tag, url, source)
    actual = command("git", "-C", source, "rev-parse", "HEAD", capture_output=True,
                     text=True).stdout.strip()
    if actual != commit:
        raise RuntimeError(
            f"Expected {source.name} commit {commit}; found {actual}; checkout unchanged"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    pin(OMNET, "https://github.com/omnetpp/omnetpp.git", "omnetpp-6.2.0", OMNET_COMMIT)
    pin(INET, "https://github.com/inet-framework/inet.git", "v4.6.0", INET_COMMIT)

    compiler = os.environ.get("CXX") or shutil.which("g++-15") or shutil.which("c++")
    if not compiler:
        parser.error("Install a C++17 compiler; see README.md")
    env = {
        **os.environ,
        "PATH": os.pathsep.join((
            str(OMNET / "bin"), str(ROOT / ".venv" / "bin"),
            str(Path(compiler).parent), os.environ["PATH"],
        )),
        "OMNETPP_ROOT": str(OMNET),
        "__omnetpp_root_dir": str(OMNET),
        "OMNETPP_RELEASE": (OMNET / "Version").read_text().strip(),
        "INET_ROOT": str(INET),
        "PYTHON3": sys.executable,
        "PYTHONPATH": os.pathsep.join([str(OMNET / "python"), os.environ.get("PYTHONPATH", "")]),
        "LD_LIBRARY_PATH": os.pathsep.join([str(OMNET / "lib"),
                                           os.environ.get("LD_LIBRARY_PATH", "")]),
    }
    configuration = "\n".join((
        "WITH_QTENV=no", "WITH_OSG=no", "WITH_OSGEARTH=no",
        "WITH_SCAVE_PYTHON_BINDINGS=no", "WITH_PARSIM=no", "WITH_LIBXML=no",
        "WITH_NETBUILDER=yes", "WITH_BACKTRACE=no", "SHARED_LIBS=yes",
        "PREFER_CLANG=no", f"CXX={Path(compiler).name}", "CXXFLAGS=-std=c++17", "",
    ))
    configure_user = OMNET / "configure.user"
    if not configure_user.exists() or configure_user.read_text() != configuration:
        configure_user.write_text(configuration, encoding="utf-8")
        command("./configure", cwd=OMNET, env=env)
    elif not (OMNET / "Makefile.inc").is_file():
        command("./configure", cwd=OMNET, env=env)
    command("make", "MODE=release", "-j" + str(args.jobs), "base", cwd=OMNET, env=env)

    featuretool = OMNET / "bin" / "opp_featuretool"
    state = INET / ".oppfeaturestate"
    enabled = {
        feature.attrib["id"] for feature in ET.parse(state).getroot()
        if feature.attrib.get("enabled") == "true"
    } if state.exists() else set()
    if enabled != {"PhysicalLayerCommon", "PhysicalLayerWirelessCommon"}:
        command(featuretool, "disable", "all", cwd=INET, env=env)
        command(featuretool, "enable", "-f", "PhysicalLayerWirelessCommon", cwd=INET, env=env)
    command("make", "MODE=release", "-j" + str(args.jobs), cwd=INET, env=env)

    cmake = BUILD / "cmake"
    command("cmake", "-S", NATIVE, "-B", cmake, "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_CXX_COMPILER={compiler}", f"-DOMNETPP_ROOT={OMNET}",
            f"-DINET_ROOT={INET}", env=env)
    command("cmake", "--build", cmake, "--parallel", args.jobs, env=env)

    diff_hashes = {}
    for label, source in (("omnet", OMNET), ("inet", INET)):
        diff = command("git", "-C", source, "diff", "HEAD", "--binary",
                       capture_output=True).stdout
        diff_hashes[label + "_diff_sha256"] = hashlib.sha256(diff).hexdigest()
    metadata = {
        "omnet_version": OMNET_VERSION, "omnet_commit": OMNET_COMMIT,
        "inet_version": INET_VERSION, "inet_commit": INET_COMMIT,
        "native_sha256": native_source_digest(NATIVE),
        "compiler": command(compiler, "--version", capture_output=True,
                             text=True).stdout.splitlines()[0],
        "build_type": "Release", **diff_hashes,
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    temporary = MANIFEST.with_suffix(".tmp")
    temporary.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    temporary.replace(MANIFEST)


if __name__ == "__main__":
    MANIFEST.unlink(missing_ok=True)
    main()
