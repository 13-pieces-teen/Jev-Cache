"""Launch only our bundle, capture its own window, and require clean timed exit."""

import json
import os
import subprocess
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
(root / "artifacts").mkdir(exist_ok=True)
folder = root / ".local" / ("packaged-smoke-" + str(time.time_ns()))
artifacts = folder / "capture"
env = os.environ | {"JEVCACHE_DATA_DIR": str(folder)}
app = subprocess.Popen(
    [
        str(root / "dist/JevCache/JevCache.exe"),
        "--screenshot",
        str(artifacts / "packaged-main.png"),
        "--quit-after",
        "11",
    ],
    env=env,
)
try:
    assert app.wait(timeout=28) == 0, "Packaged app exited with an error"
    state = json.loads((artifacts / "smoke-state.json").read_text(encoding="utf-8"))
    assert state["sample"]["total"] > 0 and state["item_count"] > 0
    assert not state["provider_configured"] and not state["fake_data"]
    assert (folder / "app.log").read_text(encoding="utf-8") == ""
    for path in artifacts.iterdir():
        (root / "artifacts" / path.name).write_bytes(path.read_bytes())
    print(json.dumps({"packaged_start_and_exit": "passed", **state}))
finally:
    if app.poll() is None:
        app.terminate()  # Only this owned, disposable validation instance.
        app.wait(timeout=10)
