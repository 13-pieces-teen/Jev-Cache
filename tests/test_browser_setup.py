import base64
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from jev_cache.bridge import CONNECTION_CONFIG
from jev_cache.browser_setup import register_edge


def test_registration_installs_host_in_user_data_and_is_repeatable(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    host = bundle / "browser-host/JevCacheNativeHost/JevCacheNativeHost.exe"
    host.parent.mkdir(parents=True)
    host.write_bytes(b"owned-fixture-executable")
    (host.parent / "dependency.dll").write_bytes(b"dependency fixture")
    extension = bundle / "extensions/edge"
    extension.mkdir(parents=True)
    key = base64.b64encode(b"synthetic public key").decode()
    (extension / "manifest.json").write_text(json.dumps({"key": key}), encoding="utf-8")
    folder = tmp_path / "user-data"
    monkeypatch.setenv("JEVCACHE_DATA_DIR", str(folder))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(bundle / "JevCache.exe"))
    writes = []

    class Handle:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    def create(hive, name, reserved, flags):
        assert hive == "HKCU" and name.endswith("ai.typesafe.jevcache")
        return Handle()

    fake = SimpleNamespace(
        HKEY_CURRENT_USER="HKCU",
        KEY_WRITE=1,
        KEY_WOW64_32KEY=2,
        KEY_WOW64_64KEY=4,
        REG_SZ=1,
        CreateKeyEx=create,
        SetValueEx=lambda *args: writes.append(args[-1]),
    )
    monkeypatch.setitem(sys.modules, "winreg", fake)
    assert register_edge() == extension.resolve()
    manifest_path = folder / "native-messaging.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    assert json.loads((bundle / "native-messaging.json").read_text("utf-8")) == manifest
    installed = Path(manifest["path"])
    assert installed.is_relative_to(folder) and installed.read_bytes() == host.read_bytes()
    assert (installed.parent / "dependency.dll").is_file()
    connection = json.loads((installed.parent / CONNECTION_CONFIG).read_text("utf-8"))
    assert connection["secret_path"] == str((folder / "bridge.secret").resolve())
    assert connection["address"].startswith(r"\\.\pipe\JevCache-")
    assert set(connection) == {"version", "address", "secret_path"}
    assert writes == [str(manifest_path), str(manifest_path)]
    assert manifest["allowed_origins"] == [
        "chrome-extension://"
        + "".join(chr(ord("a") + int(n, 16)) for n in hashlib.sha256(base64.b64decode(key)).hexdigest()[:32])
        + "/"
    ]
    # Re-registering an installed version must not rewrite its in-use executable.
    previous = installed.stat().st_mtime_ns
    assert register_edge() == extension.resolve()
    assert installed.stat().st_mtime_ns == previous
