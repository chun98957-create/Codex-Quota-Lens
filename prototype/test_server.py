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


if __name__ == "__main__":
    unittest.main()
