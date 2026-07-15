import json
import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "scripts" / "mcp-server.mjs"


class McpServerTest(unittest.TestCase):
    def run_messages(self, messages):
        payload = "\n".join(json.dumps(message) for message in messages) + "\n"
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        result = subprocess.run(
            ["node", str(SERVER)],
            input=payload,
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            timeout=20,
            check=True,
        )
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]

    def test_exposes_read_only_app_tool_and_widget(self):
        replies = self.run_messages(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18"},
                },
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}},
            ]
        )
        self.assertEqual(replies[0]["result"]["serverInfo"]["version"], "0.2.0")
        tool = replies[1]["result"]["tools"][0]
        self.assertEqual(tool["name"], "show_quota_dashboard")
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertEqual(
            tool["_meta"]["ui"]["resourceUri"],
            "ui://codex-quota-lens/quota-dashboard-v2.html",
        )
        resource = replies[2]["result"]["resources"][0]
        self.assertEqual(resource["mimeType"], "text/html;profile=mcp-app")


if __name__ == "__main__":
    unittest.main()
