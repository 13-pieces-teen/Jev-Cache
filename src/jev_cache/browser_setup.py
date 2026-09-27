from __future__ import annotations

import base64
import hashlib
import json
import shutil
import sys
from pathlib import Path

from .bridge import CONNECTION_CONFIG, pipe_credentials
from .storage import data_directory


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
    # The registered host is an installation artifact, not a transient build path.
    # A versioned directory also avoids overwriting an existing host executable.
    folder = data_directory()
    host_version = hashlib.sha256(host.read_bytes()).hexdigest()[:16]
    installed = folder / "native-host" / host_version
    installed_host = installed / host.name
    if not installed_host.is_file():
        shutil.copytree(host.parent, installed, dirs_exist_ok=True)
    address, _ = pipe_credentials()
    connection = {
        "version": 1,
        "address": address,
        # Resolve the actual file, not only its parent: Windows may redirect
        # individual files differently for the assistant and the Edge launcher.
        "secret_path": str((folder / "bridge.secret").resolve()),
    }
    temporary = installed / (CONNECTION_CONFIG + ".tmp")
    temporary.write_text(json.dumps(connection, indent=2), encoding="utf-8")
    temporary.replace(installed / CONNECTION_CONFIG)
    registration = {
        "name": "ai.typesafe.jevcache",
        "description": "Jev-Cache local Edge bridge",
        "path": str(installed_host.resolve()),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }
    destination = folder / "native-messaging.json"
    contents = json.dumps(registration, indent=2)
    destination.write_text(contents, encoding="utf-8")
    # Keep an installation manifest beside the bundle so a user can register it
    # from the Windows desktop if the development launcher redirects HKCU.
    (root / "native-messaging.json").write_text(contents, encoding="utf-8")
    for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Edge\NativeMessagingHosts\ai.typesafe.jevcache",
            0,
            winreg.KEY_WRITE | view,
        ) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(destination.resolve()))
    return extension.resolve()
