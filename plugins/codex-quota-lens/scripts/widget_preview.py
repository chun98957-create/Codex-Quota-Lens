#!/usr/bin/env python3
"""Serve the MCP widget with live local data for visual development."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from quota_lens import AppHandler, TelemetryStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview the Codex Quota Lens MCP widget")
    parser.add_argument("--port", type=int, default=4184)
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    widget_dir = root / "assets" / "widget"
    AppHandler.store = TelemetryStore(args.codex_home)
    handler = partial(AppHandler, directory=str(widget_dir))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Widget preview: http://127.0.0.1:{args.port}/quota-dashboard-v2.html?preview=1")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
