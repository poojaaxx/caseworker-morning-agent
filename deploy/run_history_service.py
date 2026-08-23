#!/usr/bin/env python3
"""Deployment wrapper for the official Resident History API - NOT part of the data
pack and not claimed to be.

data-pack/services/history_service.py is a byte-identical, unmodified copy of the
file supplied with the problem (see DECISIONS.md > "Official Data Pack Integration").
It hardcodes ThreadingHTTPServer(('127.0.0.1', port), ...), which is correct for local
development but unreachable on a host like Render that requires binding to 0.0.0.0 and
listening on a platform-assigned port. Rather than edit the official file to add that,
this wrapper loads its Handler and DATA by file path and starts the HTTP server itself,
with deployment-appropriate defaults. The official file is never imported as a package
(data-pack/ is not a valid Python identifier - it has a hyphen) and never edited.

Local development is unaffected - keep using:
    python data-pack/services/history_service.py --port 8083
exactly as README.md documents. This wrapper is only referenced by render.yaml.

Usage:
    python deploy/run_history_service.py [--host 0.0.0.0] [--port PORT]
Defaults: host 0.0.0.0, port from the $PORT env var (Render sets this), else 8083.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import ModuleType

SERVICE_PATH = (
    Path(__file__).resolve().parent.parent / "data-pack" / "services" / "history_service.py"
)


def _load_official_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("official_history_service", SERVICE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load official history service from {SERVICE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8083)))
    args = parser.parse_args()

    official = _load_official_module()
    print(f"Resident History API (deployment wrapper) on http://{args.host}:{args.port} "
          f"({len(official.DATA)} residents)")
    ThreadingHTTPServer((args.host, args.port), official.Handler).serve_forever()


if __name__ == "__main__":
    main()
