import json
import sys
from types import ModuleType

import pytest

from propagation_lab import ns3_adapter


def native_manifest(tmp_path):
    source = tmp_path / "native" / "model.cc"
    source.parent.mkdir()
    source.write_text("original source")
    manifest = tmp_path / "vendor" / "ns-3" / "build" / "propagation-lab-build.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({
        "ns3_commit": ns3_adapter.NS3_COMMIT,
        "native_sha256": ns3_adapter.native_source_digest(source.parent),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
    }))
    return source


def test_missing_native_build_requests_make(monkeypatch, tmp_path):
    monkeypatch.setattr(ns3_adapter, "ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="make ns3"):
        ns3_adapter.Ns3Adapter(42)


def test_changed_cpp_source_cannot_silently_use_stale_library(monkeypatch, tmp_path):
    source = native_manifest(tmp_path)
    source.write_text("modified C++ source")
    monkeypatch.setattr(ns3_adapter, "ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="stale"):
        ns3_adapter.Ns3Adapter(42)


def test_preloaded_other_ns3_build_is_rejected(monkeypatch, tmp_path):
    native_manifest(tmp_path)
    other = ModuleType("ns")
    other.__file__ = str(tmp_path / "other" / "ns" / "__init__.py")
    monkeypatch.setitem(sys.modules, "ns", other)
    monkeypatch.setattr(ns3_adapter, "ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="Another ns-3 installation"):
        ns3_adapter.Ns3Adapter(42)
