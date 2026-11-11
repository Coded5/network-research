import json

import pytest

from propagation_lab import omnet_adapter


def native_manifest(tmp_path):
    source = tmp_path / "native" / "omnet" / "model.cc"
    source.parent.mkdir(parents=True)
    source.write_text("original source")
    manifest = tmp_path / "build" / "omnet" / "build.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({
        "omnet_commit": omnet_adapter.OMNET_COMMIT,
        "inet_commit": omnet_adapter.INET_COMMIT,
        "native_sha256": omnet_adapter.native_source_digest(source.parent),
    }))
    return source


def test_missing_native_build_requests_make(monkeypatch, tmp_path):
    monkeypatch.setattr(omnet_adapter, "ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="make omnet"):
        omnet_adapter.OmnetAdapter(42)


def test_changed_cpp_source_cannot_silently_use_stale_library(monkeypatch, tmp_path):
    source = native_manifest(tmp_path)
    source.write_text("modified C++ source")
    monkeypatch.setattr(omnet_adapter, "ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="stale"):
        omnet_adapter.OmnetAdapter(42)


def test_other_pinned_build_is_rejected(monkeypatch, tmp_path):
    native_manifest(tmp_path)
    monkeypatch.setattr(omnet_adapter, "ROOT", tmp_path)
    manifest = tmp_path / "build" / "omnet" / "build.json"
    data = json.loads(manifest.read_text())
    data["inet_commit"] = "wrong"
    manifest.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match="stale"):
        omnet_adapter.OmnetAdapter(42)
