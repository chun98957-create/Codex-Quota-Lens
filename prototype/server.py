#!/usr/bin/env python3
"""Local-only prototype server for Codex Quota Lens.

The collector reads a strict allowlist of numeric telemetry fields from Codex
JSONL session events. Prompt, response, reasoning, tool, and file content is
never returned by the API or retained in memory.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import statistics
import threading
from collections import defaultdict
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


UTC = dt.timezone.utc
MAX_POINTS = 240
MAX_EVENTS = 50_000
HISTORY_DAYS = 28
SPEED_WINDOW_MINUTES = 15
MIN_SPEED_SPAN_MINUTES = 5
MIN_SPEED_SAMPLES = 3
MIN_HEATMAP_SAMPLES = 3
TOKEN_EVENT_PATTERN = re.compile(rb'"payload"\s*:\s*\{\s*"type"\s*:\s*"token_count"')


def _epoch(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number / 1000 if number > 10_000_000_000 else number
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return _epoch(float(text))
        except ValueError:
            try:
                return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return None
    return None


def _iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return dt.datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z")


def _number(mapping: dict[str, Any] | None, key: str) -> float:
    if not isinstance(mapping, dict):
        return 0.0
    value = mapping.get(key, 0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def _token_fields(value: dict[str, Any] | None) -> dict[str, int]:
    return {
        "input_tokens": int(_number(value, "input_tokens")),
        "cached_input_tokens": int(_number(value, "cached_input_tokens")),
        "output_tokens": int(_number(value, "output_tokens")),
        "reasoning_output_tokens": int(_number(value, "reasoning_output_tokens")),
        "total_tokens": int(_number(value, "total_tokens")),
    }


def _median(values: Iterable[float]) -> float:
    items = list(values)
    return float(statistics.median(items)) if items else 0.0


class TelemetryStore:
    """Incrementally collects only token-count and rate-limit telemetry."""

    def __init__(self, codex_home: Path):
        self.codex_home = codex_home.expanduser().resolve()
        self.sessions_dir = self.codex_home / "sessions"
        self._offsets: dict[Path, int] = {}
        self._snapshots: list[dict[str, Any]] = []
        self._token_events: list[dict[str, Any]] = []
        self._seen_snapshots: set[tuple[Any, ...]] = set()
        self._seen_tokens: set[tuple[Any, ...]] = set()
        self._lock = threading.RLock()
        self.files_scanned = 0
        self.parse_errors = 0

    def scan(self) -> None:
        with self._lock:
            paths = sorted(self.sessions_dir.rglob("*.jsonl")) if self.sessions_dir.exists() else []
            self.files_scanned = len(paths)
            for path in paths:
                self._scan_file(path)
            self._snapshots = sorted(self._snapshots, key=lambda item: item["timestamp"])[-MAX_EVENTS:]
            self._token_events = sorted(self._token_events, key=lambda item: item["timestamp"])[-MAX_EVENTS:]

    def _scan_file(self, path: Path) -> None:
        try:
            size = path.stat().st_size
            offset = self._offsets.get(path, 0)
            if size < offset:
                offset = 0
            with path.open("rb") as handle:
                handle.seek(offset)
                while raw_line := handle.readline():
                    # Avoid decoding or parsing ordinary message/tool/content events.
                    if not TOKEN_EVENT_PATTERN.search(raw_line):
                        continue
                    try:
                        event = json.loads(raw_line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        self.parse_errors += 1
                        continue
                    self._consume_token_event(event)
                self._offsets[path] = handle.tell()
        except (OSError, PermissionError):
            self.parse_errors += 1

    def _consume_token_event(self, event: dict[str, Any]) -> None:
        payload = event.get("payload")
        if event.get("type") != "event_msg" or not isinstance(payload, dict):
            return
        if payload.get("type") != "token_count":
            return
        timestamp = _epoch(event.get("timestamp"))
        if timestamp is None:
            return

        info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
        rate_limits = payload.get("rate_limits") if isinstance(payload.get("rate_limits"), dict) else {}
        primary = rate_limits.get("primary") if isinstance(rate_limits.get("primary"), dict) else None

        if primary and isinstance(primary.get("used_percent"), (int, float)):
            used = max(0.0, min(100.0, float(primary["used_percent"])))
            reset_at = _epoch(primary.get("resets_at"))
            window = int(_number(primary, "window_minutes"))
            key = (round(timestamp, 3), round(used, 5), reset_at, window)
            if key not in self._seen_snapshots:
                self._seen_snapshots.add(key)
                self._snapshots.append(
                    {
                        "timestamp": timestamp,
                        "used_percent": used,
                        "reset_at": reset_at,
                        "window_minutes": window,
                        "limit_id": str(rate_limits.get("limit_id") or ""),
                        "limit_name": str(rate_limits.get("limit_name") or ""),
                        "plan_type": str(rate_limits.get("plan_type") or ""),
                    }
                )

        last_usage = info.get("last_token_usage") if isinstance(info.get("last_token_usage"), dict) else None
        if last_usage:
            tokens = _token_fields(last_usage)
            if tokens["total_tokens"] > 0:
                key = (round(timestamp, 3), *tokens.values())
                if key not in self._seen_tokens:
                    self._seen_tokens.add(key)
                    self._token_events.append({"timestamp": timestamp, **tokens})

    @staticmethod
    def _same_epoch(left: dict[str, Any], right: dict[str, Any]) -> bool:
        left_reset = left.get("reset_at")
        right_reset = right.get("reset_at")
        if left_reset and right_reset:
            return abs(left_reset - right_reset) < 90
        return right["used_percent"] + 0.25 >= left["used_percent"]

    def _current_epoch(self, snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not snapshots:
            return []
        current = [snapshots[-1]]
        for item in reversed(snapshots[:-1]):
            if not self._same_epoch(item, current[-1]):
                break
            current.append(item)
        return list(reversed(current))

    def _burn_rate(self, snapshots: list[dict[str, Any]], now: float) -> tuple[float, int]:
        if len(snapshots) < 2:
            return 0.0, 0
        for minutes in (60, 180, 360):
            window = [item for item in snapshots if item["timestamp"] >= now - minutes * 60]
            if len(window) < 2:
                continue
            span_hours = (window[-1]["timestamp"] - window[0]["timestamp"]) / 3600
            if span_hours < 5 / 60:
                continue
            delta = window[-1]["used_percent"] - window[0]["used_percent"]
            return max(0.0, delta / span_hours), minutes
        return 0.0, 0

    def _intervals(self, snapshots: list[dict[str, Any]], now: float) -> list[dict[str, Any]]:
        cutoff = now - HISTORY_DAYS * 24 * 3600
        bucket_seconds = SPEED_WINDOW_MINUTES * 60
        buckets: dict[tuple[int, int | None], list[dict[str, Any]]] = defaultdict(list)
        for item in snapshots:
            if item["timestamp"] < cutoff:
                continue
            bucket_start = int(item["timestamp"] // bucket_seconds) * bucket_seconds
            reset_at = item.get("reset_at")
            reset_key = round(reset_at / 60) if reset_at else None
            buckets[(bucket_start, reset_key)].append(item)

        intervals: list[dict[str, Any]] = []
        for items in buckets.values():
            items.sort(key=lambda item: item["timestamp"])
            if len(items) < 2:
                continue
            left, right = items[0], items[-1]
            seconds = right["timestamp"] - left["timestamp"]
            delta = right["used_percent"] - left["used_percent"]
            if seconds < MIN_SPEED_SPAN_MINUTES * 60 or seconds > bucket_seconds or delta <= 0:
                continue
            if not self._same_epoch(left, right):
                continue
            rate = min(100.0, delta / (seconds / 3600))
            midpoint = left["timestamp"] + seconds / 2
            local = dt.datetime.fromtimestamp(midpoint)
            intervals.append(
                {
                    "start": left["timestamp"],
                    "end": right["timestamp"],
                    "midpoint": midpoint,
                    "burn_pph": rate,
                    "delta_percent": delta,
                    "sample_count": len(items),
                    "local_date": local.strftime("%Y-%m-%d"),
                }
            )
        return sorted(intervals, key=lambda item: item["midpoint"])

    @staticmethod
    def _downsample(items: list[dict[str, Any]], limit: int = MAX_POINTS) -> list[dict[str, Any]]:
        if len(items) <= limit:
            return items
        step = math.ceil(len(items) / limit)
        sampled = items[::step]
        if sampled[-1] is not items[-1]:
            sampled.append(items[-1])
        return sampled

    def _heatmap(self, intervals: list[dict[str, Any]]) -> dict[str, Any]:
        hours = list(range(0, 24, 3))
        cells: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for item in intervals:
            local = dt.datetime.fromtimestamp(item["midpoint"])
            hour_bucket = (local.hour // 3) * 3
            cells[(hour_bucket, local.weekday())].append(item)
        values = [
            [round(_median(item["burn_pph"] for item in cells[(hour, weekday)]), 1) for weekday in range(7)]
            for hour in hours
        ]
        counts = [
            [len(cells[(hour, weekday)]) for weekday in range(7)]
            for hour in hours
        ]
        reliable = [
            [count >= MIN_HEATMAP_SAMPLES for count in row]
            for row in counts
        ]
        date_ranges: list[list[str]] = []
        for hour in hours:
            row: list[str] = []
            for weekday in range(7):
                dates = sorted({item["local_date"] for item in cells[(hour, weekday)]})
                if not dates:
                    row.append("")
                elif len(dates) == 1:
                    row.append(dates[0])
                else:
                    row.append(f"{dates[0]} 至 {dates[-1]}")
            date_ranges.append(row)
        return {
            "days": ["一", "二", "三", "四", "五", "六", "日"],
            "hours": hours,
            "values": values,
            "counts": counts,
            "reliable": reliable,
            "date_ranges": date_ranges,
            "max": max((value for row in values for value in row), default=0.0),
            "history_days": HISTORY_DAYS,
            "window_minutes": SPEED_WINDOW_MINUTES,
            "minimum_samples": MIN_HEATMAP_SAMPLES,
            "observed_windows": len(intervals),
        }

    def _fastest(self, intervals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cell_counts: dict[tuple[int, int], int] = defaultdict(int)
        for item in intervals:
            local = dt.datetime.fromtimestamp(item["midpoint"])
            cell_counts[(local.weekday(), (local.hour // 3) * 3)] += 1
        eligible = []
        for item in intervals:
            local = dt.datetime.fromtimestamp(item["midpoint"])
            cell_count = cell_counts[(local.weekday(), (local.hour // 3) * 3)]
            if item["sample_count"] >= MIN_SPEED_SAMPLES and cell_count >= MIN_HEATMAP_SAMPLES:
                eligible.append({**item, "cell_window_count": cell_count})
        ranked = sorted(eligible, key=lambda item: item["burn_pph"], reverse=True)
        chosen: list[dict[str, Any]] = []
        for item in ranked:
            start = dt.datetime.fromtimestamp(item["start"])
            end = dt.datetime.fromtimestamp(item["end"])
            chosen.append(
                {
                    "start": _iso(item["start"]),
                    "end": _iso(item["end"]),
                    "label": f"{start:%Y-%m-%d %H:%M}–{end:%H:%M}",
                    "burn_pph": round(item["burn_pph"], 1),
                    "delta_percent": round(item["delta_percent"], 1),
                    "sample_count": item["sample_count"],
                    "cell_window_count": item["cell_window_count"],
                    "window_minutes": SPEED_WINDOW_MINUTES,
                }
            )
            if len(chosen) == 3:
                break
        return chosen

    def snapshot(self) -> dict[str, Any]:
        self.scan()
        with self._lock:
            if not self._snapshots:
                return {
                    "mode": "unavailable",
                    "generated_at": _iso(dt.datetime.now(UTC).timestamp()),
                    "error": "没有找到可用的 token_count / rate-limit 事件。",
                    "source": {
                        "files_scanned": self.files_scanned,
                        "parse_errors": self.parse_errors,
                        "privacy": "仅提取数字额度与 token 字段",
                    },
                }

            now = dt.datetime.now(UTC).timestamp()
            all_snapshots = list(self._snapshots)
            latest = all_snapshots[-1]
            epoch = self._current_epoch(all_snapshots)
            burn_pph, burn_window = self._burn_rate(epoch, now)
            remaining = max(0.0, 100.0 - latest["used_percent"])
            reset_at = latest.get("reset_at")
            hours_until_reset = max(0.0, (reset_at - now) / 3600) if reset_at else None
            budget_pph = remaining / hours_until_reset if hours_until_reset and hours_until_reset > 0 else 0.0
            exhausts_at = now + remaining / burn_pph * 3600 if burn_pph > 0 else None

            history_cutoff = now - 24 * 3600
            history_source = [item for item in epoch if item["timestamp"] >= history_cutoff]
            if len(history_source) < 2:
                history_source = epoch[-MAX_POINTS:]
            history = [
                {
                    "timestamp": _iso(item["timestamp"]),
                    "remaining_percent": round(100.0 - item["used_percent"], 2),
                }
                for item in self._downsample(history_source)
            ]

            intervals = self._intervals(all_snapshots, now)
            latest_tokens = self._token_events[-1] if self._token_events else None
            recent_tokens = [item for item in self._token_events if item["timestamp"] >= history_cutoff]
            token_totals = {
                key: sum(item[key] for item in recent_tokens)
                for key in _token_fields({}).keys()
            }

            return {
                "mode": "live",
                "generated_at": _iso(now),
                "quota": {
                    "used_percent": round(latest["used_percent"], 2),
                    "remaining_percent": round(remaining, 2),
                    "window_minutes": latest["window_minutes"],
                    "resets_at": _iso(reset_at),
                    "hours_until_reset": round(hours_until_reset, 3) if hours_until_reset is not None else None,
                    "burn_pph": round(burn_pph, 2),
                    "burn_window_minutes": burn_window,
                    "budget_pph": round(budget_pph, 2),
                    "forecast_exhausts_at": _iso(exhausts_at),
                    "plan_type": latest["plan_type"],
                    "limit_name": latest["limit_name"],
                },
                "history": history,
                "tokens": {
                    "latest": {key: value for key, value in latest_tokens.items() if key != "timestamp"} if latest_tokens else None,
                    "last_24h": token_totals,
                    "events_last_24h": len(recent_tokens),
                },
                "heatmap": self._heatmap(intervals),
                "fastest": self._fastest(intervals),
                "source": {
                    "files_scanned": self.files_scanned,
                    "rate_limit_events": len(all_snapshots),
                    "token_events": len(self._token_events),
                    "parse_errors": self.parse_errors,
                    "latest_event_at": _iso(latest["timestamp"]),
                    "privacy": "仅提取数字额度与 token 字段",
                },
            }


class AppHandler(SimpleHTTPRequestHandler):
    store: TelemetryStore

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route == "/api/snapshot":
            try:
                payload = self.store.snapshot()
                body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:  # pragma: no cover - last-resort local diagnostic
                body = json.dumps({"mode": "error", "error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            return
        if route == "/":
            self.send_response(302)
            self.send_header("Location", "/prototype/index.html")
            self.end_headers()
            return
        super().do_GET()

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format_string % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Codex Quota Lens prototype")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    args = parser.parse_args()

    repository_dir = Path(__file__).resolve().parent.parent
    store = TelemetryStore(args.codex_home)
    store.scan()
    AppHandler.store = store
    handler = partial(AppHandler, directory=str(repository_dir))

    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Codex Quota Lens: http://127.0.0.1:{args.port}/")
    print(f"Telemetry source: {store.sessions_dir}")
    print("Privacy: only numeric token-count and rate-limit fields are read")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
