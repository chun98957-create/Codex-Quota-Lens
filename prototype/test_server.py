import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from server import TelemetryStore, UTC


class TelemetryStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.session = self.home / "sessions" / "2026" / "07" / "15" / "session.jsonl"
        self.session.parent.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def append_event(self, timestamp: float, used: float, reset_at: float, tokens: int) -> None:
        event = {
            "timestamp": dt.datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z"),
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {
                        "input_tokens": tokens,
                        "cached_input_tokens": tokens // 2,
                        "output_tokens": tokens // 4,
                        "reasoning_output_tokens": tokens // 8,
                        "total_tokens": tokens + tokens // 4,
                    }
                },
                "rate_limits": {
                    "plan_type": "test",
                    "primary": {
                        "used_percent": used,
                        "window_minutes": 300,
                        "resets_at": int(reset_at),
                    },
                },
            },
        }
        with self.session.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")

    def test_incremental_snapshot_uses_only_telemetry(self):
        now = dt.datetime.now(UTC).timestamp()
        reset_at = now + 4 * 3600
        self.append_event(now - 3600, 30, reset_at, 1000)
        self.append_event(now - 1800, 35, reset_at, 1500)
        self.append_event(now - 600, 40, reset_at, 2000)
        with self.session.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"type": "event_msg", "payload": {"type": "user_message", "message": "SECRET"}}) + "\n")

        store = TelemetryStore(self.home)
        result = store.snapshot()

        self.assertEqual(result["mode"], "live")
        self.assertEqual(result["quota"]["remaining_percent"], 60)
        self.assertGreater(result["quota"]["burn_pph"], 0)
        self.assertEqual(result["tokens"]["latest"]["input_tokens"], 2000)
        self.assertNotIn("SECRET", json.dumps(result))

        self.append_event(now - 60, 45, reset_at, 2500)
        updated = store.snapshot()
        self.assertEqual(updated["quota"]["remaining_percent"], 55)
        self.assertEqual(updated["source"]["rate_limit_events"], 4)
        self.assertEqual(updated["fastest"], [])

    def test_speed_history_uses_fixed_windows_and_sample_thresholds(self):
        now = dt.datetime.now(UTC).timestamp()
        reset_at = now + 4 * 3600
        base = int((now - 2 * 3600) // (15 * 60)) * (15 * 60)
        used = 10.0
        tokens = 1000

        # Three valid 15-minute windows in the same three-hour heatmap cell.
        for bucket_index in range(3):
            start = base + bucket_index * 15 * 60
            for offset in (60, 360, 660):
                self.append_event(start + offset, used, reset_at, tokens)
                used += 1
                tokens += 100

        # This otherwise-valid window is outside the 28-day history cutoff.
        old_base = base - 40 * 24 * 3600
        old_reset = old_base + 4 * 3600
        for offset in (60, 360, 660):
            self.append_event(old_base + offset, 20 + offset / 300, old_reset, tokens)
            tokens += 100

        result = TelemetryStore(self.home).snapshot()
        heatmap = result["heatmap"]

        self.assertEqual(heatmap["history_days"], 28)
        self.assertEqual(heatmap["window_minutes"], 15)
        self.assertEqual(sum(sum(row) for row in heatmap["counts"]), 3)
        self.assertTrue(any(any(row) for row in heatmap["reliable"]))
        self.assertEqual(len(result["fastest"]), 3)
        self.assertTrue(all(item["sample_count"] == 3 for item in result["fastest"]))
        self.assertTrue(all(item["label"].startswith(str(dt.datetime.fromtimestamp(base).year)) for item in result["fastest"]))


if __name__ == "__main__":
    unittest.main()
