from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path


def register_edge() -> Path:
    import winreg

    root = (
        Path(sys.executable).parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parents[2] / "dist" / "JevCache"
    )
    extension = root / "extensions" / "edge"
    host = root / "browser-host" / "JevCacheNativeHost" / "JevCacheNativeHost.exe"
    if not host.is_file() or not (extension / "manifest.json").is_file():
        raise FileNotFoundError("Build the full bundle first")
    manifest = json.loads((extension / "manifest.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
    extension_id = "".join(chr(ord("a") + int(n, 16)) for n in digest)
    registration = {
        "name": "ai.typesafe.jevcache",
        "description": "Jev-Cache local Edge bridge",
        "path": str(host.resolve()),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }
    destination = root / "native-messaging.json"
    destination.write_text(json.dumps(registration, indent=2), encoding="utf-8")
    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Edge\NativeMessagingHosts\ai.typesafe.jevcache"
    ) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(destination.resolve()))
    return extension.resolve()
