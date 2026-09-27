"""Short observer-only resource check. No optimization or API calls."""

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import psutil

parser = argparse.ArgumentParser()
parser.add_argument("--seconds", type=int, default=35)
parser.add_argument("--exe", type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
folder = root / ".local" / ("profile-" + str(time.time_ns()))
env = os.environ | {"JEVCACHE_DATA_DIR": str(folder)}
command = [str(args.exe)] if args.exe else [sys.executable, "-m", "jev_cache"]
command += ["--start-hidden", "--quit-after", str(args.seconds)]
child = subprocess.Popen(command, cwd=root, env=env)
samples = []
try:
    started = time.monotonic()
    previous_cpu = None
    previous_time = None
    while child.poll() is None and time.monotonic() - started < args.seconds + 8:
        now = time.monotonic()
        processes = [psutil.Process(child.pid)]
        processes += processes[0].children(recursive=True)
        rss = uss = cpu = 0
        for process in processes:
            try:
                memory = process.memory_full_info()
                rss += memory.rss
                uss += memory.uss
                ticks = process.cpu_times()
                cpu += ticks.user + ticks.system
            except psutil.Error:
                pass
        if now - started > 8 and previous_cpu is not None:
            samples.append(
                {
                    "elapsed": round(now - started, 2),
                    "rss_mib": rss / 1024**2,
                    "private_resident_uss_mib": uss / 1024**2,
                    "one_core_cpu_percent": max(0, (cpu - previous_cpu) / (now - previous_time) * 100),
                    "processes": len(processes),
                }
            )
        previous_cpu, previous_time = cpu, now
        time.sleep(2)
    child.wait(timeout=10)
finally:
    if child.poll() is None:
        child.terminate()  # Exact owned timed validation process only.
        child.wait(timeout=10)
values = sorted(s["private_resident_uss_mib"] for s in samples)
result = {
    "mode": "details_hidden_floating_visible",
    "duration_seconds": args.seconds,
    "packaged": bool(args.exe),
    "edge_connected": False,
    "jev_called": False,
    "samples": samples,
    "p95_private_resident_uss_mib": values[min(len(values) - 1, int(len(values) * 0.95))] if values else None,
    "mean_one_core_cpu_percent": statistics.mean(s["one_core_cpu_percent"] for s in samples)
    if samples
    else None,
    "formal_24h_acceptance": False,
}
(root / "artifacts").mkdir(exist_ok=True)
path = root / "artifacts" / ("profile-packaged.json" if args.exe else "profile-source.json")
path.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in result.items() if k != "samples"}, indent=2))
