"""Owned local R4 backend process used by the bridge and finite acceptance runner."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import sys
from threading import Event
import time


ROOT = Path(__file__).resolve().parents[1]
for source in (
    ROOT / "packages" / "twinpulse_core" / "src",
    ROOT / "packages" / "twinpulse_provider" / "src",
    ROOT / "packages" / "twinpulse_app" / "src",
):
    sys.path.insert(0, str(source))

from twinpulse_app import CommandBroker, LocalApiServer  # noqa: E402
from twinpulse_core import fixed_warehouse_bundle  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--ready-file", type=Path, required=True)
    args = parser.parse_args()
    product_secret = os.environ.pop("TWINPULSE_PRODUCT_BOOTSTRAP", "")
    engine_secret = os.environ.pop("TWINPULSE_ENGINE_BOOTSTRAP", "")
    if len(product_secret) < 32 or len(engine_secret) < 32:
        raise SystemExit("Bootstrap environment is missing")

    broker = CommandBroker()
    artifact = broker.register_artifact("fixed_warehouse_v1", fixed_warehouse_bundle())
    server = LocalApiServer(
        broker,
        product_bootstrap_secret=product_secret,
        engine_bootstrap_secret=engine_secret,
        port=args.port,
    )
    server.start()
    stop = Event()

    def request_stop(_signal: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    ready = {
        "pid": os.getpid(), "base_url": server.base_url,
        "artifact_id": artifact.artifact_id, "revision": artifact.revision,
    }
    args.ready_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.ready_file.with_suffix(args.ready_file.suffix + ".tmp")
    temporary.write_text(json.dumps(ready, sort_keys=True), encoding="utf-8")
    temporary.replace(args.ready_file)
    print(f"TWINPULSE_BACKEND_READY port={server.port}", flush=True)
    try:
        while not stop.wait(0.2):
            pass
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
