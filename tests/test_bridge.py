import json
import os
import subprocess
import sys

import pytest

from jev_cache.bridge import CONNECTION_CONFIG
from jev_cache.native_host import host_credentials
from jev_cache.storage import protect_secret


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI")
def test_installed_host_uses_assistant_credential_despite_different_appdata(tmp_path, monkeypatch):
    assistant = tmp_path / "assistant-data"
    assistant.mkdir()
    secret = assistant / "bridge.secret"
    key = os.urandom(32)
    secret.write_text(protect_secret(key.hex()), encoding="utf-8")
    installed = tmp_path / "installed-host"
    installed.mkdir()
    address = r"\\.\pipe\JevCache-test-pinned-config"
    (installed / CONNECTION_CONFIG).write_text(
        json.dumps({"version": 1, "address": address, "secret_path": str(secret)}), encoding="utf-8"
    )
    other_data = tmp_path / "different-launcher-appdata"
    monkeypatch.setenv("JEVCACHE_DATA_DIR", str(other_data))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(installed / "JevCacheNativeHost.exe"))
    assert host_credentials() == (address, key)
    assert not other_data.exists(), "Installed host must not create competing credentials"


@pytest.mark.skipif(os.name != "nt", reason="Windows named pipe")
def test_rejected_client_does_not_stop_bridge_and_ping_does_not_drain_actions(tmp_path):
    program = r"""
import json, time
from multiprocessing import AuthenticationError
from multiprocessing.connection import Client
from jev_cache.bridge import Bridge, pipe_credentials
bridge = Bridge()
bridge.start()
address, key = pipe_credentials()
deadline = time.monotonic() + 4
while True:
    try:
        Client(address, family="AF_PIPE", authkey=b"intentionally-wrong-key")
    except AuthenticationError:
        break
    except OSError:
        if time.monotonic() > deadline:
            raise
        time.sleep(0.05)
with Client(address, family="AF_PIPE", authkey=key) as client:
    assert not bridge.connected
    client.send_bytes(json.dumps({"protocol": 1, "kind": "ping"}).encode())
    assert json.loads(client.recv_bytes())["commands"] == []
    assert not bridge.connected
    snapshot = {"protocol": 1, "kind": "snapshot", "session": "fixture", "seq": 1, "tabs": []}
    client.send_bytes(json.dumps(snapshot).encode())
    assert json.loads(client.recv_bytes())["commands"] == []
    assert bridge.connected and not bridge.error
    bridge.send({"id": "fixture-action"})
    client.send_bytes(json.dumps({"protocol": 1, "kind": "ping"}).encode())
    assert json.loads(client.recv_bytes())["commands"] == []
    client.send_bytes(json.dumps(snapshot | {"seq": 2}).encode())
    assert json.loads(client.recv_bytes())["commands"][0]["id"] == "fixture-action"
print("authentication_recovery_and_passive_ping_passed")
"""
    # Seed the credential before starting both ends to avoid a test-only creation race.
    (tmp_path / "bridge.secret").write_text(protect_secret(os.urandom(32).hex()), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-c", program],
        env=os.environ | {"JEVCACHE_DATA_DIR": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=12,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert result.returncode == 0, result.stderr
    assert "authentication_recovery_and_passive_ping_passed" in result.stdout
