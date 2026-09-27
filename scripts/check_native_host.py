"""End-to-end stdio/named-pipe check with an empty, synthetic browser snapshot."""

import json
import os
import struct
import subprocess
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
(root / "artifacts").mkdir(exist_ok=True)
app_exe = root / "dist/JevCache/JevCache.exe"
host_exe = root / "dist/JevCache/browser-host/JevCacheNativeHost/JevCacheNativeHost.exe"
folder = root / ".local" / ("bridge-test-" + str(time.time_ns()))
env = os.environ | {"JEVCACHE_DATA_DIR": str(folder)}
app = subprocess.Popen([str(app_exe), "--start-hidden", "--quit-after", "18"], env=env)
try:
    deadline = time.monotonic() + 12
    while not (folder / "bridge.secret").exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    assert (folder / "bridge.secret").exists(), "Assistant did not initialize bridge"
    message = json.dumps(
        {
            "protocol": 1,
            "kind": "snapshot",
            "session": "controlled-protocol-test",
            "seq": 1,
            "tabs": [],
            "events": [],
        }
    ).encode()
    host = subprocess.Popen(
        [str(host_exe)],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    output, errors = host.communicate(struct.pack("<I", len(message)) + message, timeout=10)
    assert host.returncode == 0, errors.decode(errors="replace")
    assert len(output) >= 4
    length = struct.unpack("<I", output[:4])[0]
    body = json.loads(output[4 : 4 + length])
    assert body == {"protocol": 1, "commands": []}, body
    evidence = {
        "packaged_host_and_app": True,
        "stdio_and_authenticated_named_pipe": "passed",
        "actual_edge_browser_tested": False,
        "cleanup_executed": False,
    }
    (root / "artifacts/native-host-check.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence))
    app.wait(timeout=22)
finally:
    if app.poll() is None:
        app.terminate()  # Owned timed validation process, no user apps.
        app.wait(timeout=10)
