#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const VERSION = "0.2.0";
const TOOL_NAME = "show_quota_dashboard";
const RESOURCE_URI = "ui://codex-quota-lens/quota-dashboard-v2.html";
const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const COLLECTOR = join(ROOT, "scripts", "quota_lens.py");
const WIDGET = join(ROOT, "assets", "widget", "quota-dashboard-v2.html");

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function errorResult(id, code, message, data) {
  send({ jsonrpc: "2.0", id, error: { code, message, ...(data ? { data } : {}) } });
}

function pythonCandidates() {
  const candidates = [];
  if (process.env.PYTHON) candidates.push([process.env.PYTHON, []]);
  candidates.push(["python", []], ["python3", []]);
  if (process.platform === "win32") candidates.push(["py", ["-3"]]);
  return candidates;
}

function readSnapshot() {
  const failures = [];
  for (const [command, prefix] of pythonCandidates()) {
    const result = spawnSync(command, [...prefix, COLLECTOR, "snapshot", "--compact"], {
      cwd: ROOT,
      encoding: "utf8",
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
      windowsHide: true,
      timeout: 30_000,
      maxBuffer: 4 * 1024 * 1024,
    });
    if (result.error) {
      failures.push(`${command}: ${result.error.message}`);
      continue;
    }
    const output = (result.stdout || "").trim();
    if (!output) {
      failures.push(`${command}: collector returned no JSON`);
      continue;
    }
    try {
      const snapshot = JSON.parse(output);
      if (result.status !== 0 && snapshot.mode !== "live") {
        throw new Error(snapshot.error || `collector exited with ${result.status}`);
      }
      if (Array.isArray(snapshot.history) && snapshot.history.length > 180) {
        snapshot.history = snapshot.history.slice(-180);
      }
      return snapshot;
    } catch (error) {
      failures.push(`${command}: ${error.message}`);
    }
  }
  throw new Error(`Unable to run the local quota collector. ${failures.join("; ")}`);
}

function toolDescriptor() {
  return {
    name: TOOL_NAME,
    title: "Show Codex Quota Lens",
    description:
      "Opens an interactive local dashboard for the user's current Codex quota, burn rate, fastest qualified periods, token mix, reset time, and model/reasoning usage plan. Use whenever the user asks to open, show, inspect, or plan Codex quota.",
    inputSchema: {
      type: "object",
      properties: {
        view: {
          type: "string",
          enum: ["overview", "speed", "planner"],
          description: "Dashboard tab to open first.",
        },
      },
      additionalProperties: false,
    },
    outputSchema: {
      type: "object",
      properties: {
        view: { type: "string" },
        summary: { type: "object" },
      },
      required: ["view", "summary"],
      additionalProperties: false,
    },
    annotations: {
      readOnlyHint: true,
      openWorldHint: false,
      destructiveHint: false,
      idempotentHint: true,
    },
    _meta: {
      ui: { resourceUri: RESOURCE_URI },
      "openai/outputTemplate": RESOURCE_URI,
      "openai/toolInvocation/invoking": "Reading local quota telemetry…",
      "openai/toolInvocation/invoked": "Quota dashboard ready.",
    },
  };
}

function callTool(params) {
  if (params?.name !== TOOL_NAME) {
    return {
      isError: true,
      content: [{ type: "text", text: `Unknown tool: ${params?.name || "(missing)"}` }],
    };
  }
  const requestedView = params?.arguments?.view;
  const view = ["overview", "speed", "planner"].includes(requestedView)
    ? requestedView
    : "overview";
  try {
    const snapshot = readSnapshot();
    const quota = snapshot.quota || {};
    const result = {
      view,
      summary: {
        mode: snapshot.mode,
        generated_at: snapshot.generated_at,
        quota,
        fastest: (snapshot.fastest || []).slice(0, 3),
        source: snapshot.source,
      },
    };
    return {
      structuredContent: result,
      content: [
        {
          type: "text",
          text: `Codex Quota Lens: ${quota.remaining_percent ?? "?"}% remaining, ${quota.burn_pph ?? 0}%/h recent burn rate. Values are local observations, not an official quota API.`,
        },
      ],
      _meta: { snapshot, view, privacy: "local-numeric-telemetry-only" },
    };
  } catch (error) {
    return {
      isError: true,
      content: [{ type: "text", text: error.message }],
      structuredContent: {
        view,
        summary: { mode: "unavailable", error: error.message },
      },
    };
  }
}

function handle(message) {
  const { id, method, params } = message || {};
  if (!method) return;
  if (method === "notifications/initialized" || method.startsWith("notifications/")) return;

  if (method === "initialize") {
    send({
      jsonrpc: "2.0",
      id,
      result: {
        protocolVersion: params?.protocolVersion || "2025-06-18",
        capabilities: { tools: { listChanged: false }, resources: { listChanged: false } },
        serverInfo: { name: "codex-quota-lens", version: VERSION },
        instructions:
          "Use show_quota_dashboard for Codex allowance, burn-rate, peak-period, reset-time, token-mix, or quota-planning requests. It reads only numeric local token_count telemetry.",
      },
    });
    return;
  }
  if (method === "ping") {
    send({ jsonrpc: "2.0", id, result: {} });
    return;
  }
  if (method === "tools/list") {
    send({ jsonrpc: "2.0", id, result: { tools: [toolDescriptor()] } });
    return;
  }
  if (method === "tools/call") {
    send({ jsonrpc: "2.0", id, result: callTool(params) });
    return;
  }
  if (method === "resources/list") {
    send({
      jsonrpc: "2.0",
      id,
      result: {
        resources: [
          {
            uri: RESOURCE_URI,
            name: "Codex Quota Lens dashboard",
            title: "Codex Quota Lens",
            description: "Interactive local quota, speed, and usage-planning dashboard.",
            mimeType: "text/html;profile=mcp-app",
          },
        ],
      },
    });
    return;
  }
  if (method === "resources/read") {
    if (params?.uri !== RESOURCE_URI) {
      errorResult(id, -32002, `Resource not found: ${params?.uri || "(missing)"}`);
      return;
    }
    send({
      jsonrpc: "2.0",
      id,
      result: {
        contents: [
          {
            uri: RESOURCE_URI,
            mimeType: "text/html;profile=mcp-app",
            text: readFileSync(WIDGET, "utf8"),
            _meta: {
              ui: {
                prefersBorder: true,
                csp: { connectDomains: [], resourceDomains: [] },
              },
            },
          },
        ],
      },
    });
    return;
  }
  if (method === "resources/templates/list") {
    send({ jsonrpc: "2.0", id, result: { resourceTemplates: [] } });
    return;
  }
  errorResult(id, -32601, `Method not found: ${method}`);
}

let buffer = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  let newline;
  while ((newline = buffer.indexOf("\n")) >= 0) {
    const line = buffer.slice(0, newline).trim();
    buffer = buffer.slice(newline + 1);
    if (!line) continue;
    try {
      handle(JSON.parse(line));
    } catch (error) {
      process.stderr.write(`Invalid MCP message: ${error.message}\n`);
    }
  }
});

process.stdin.on("end", () => process.exit(0));
