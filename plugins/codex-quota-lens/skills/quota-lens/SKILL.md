---
name: quota-lens
description: Inspect the user's local Codex quota, burn rate, fastest usage periods, token mix, reset time, and usage-plan scenarios. Use when the user asks about Codex allowance, quota, remaining usage, depletion risk, usage speed, peak periods, or planning across models and reasoning effort.
---

# Codex Quota Lens

Use the bundled read-only collector to inspect numeric Codex quota telemetry. Never parse or quote raw prompts, responses, reasoning, tool calls, or file content.

## Get a live snapshot

1. Resolve this skill's plugin root two directories above this file.
2. Run `python <plugin-root>/scripts/quota_lens.py snapshot`.
3. If `python` is unavailable, try `python3`, then `py -3`.
4. Treat a nonzero exit with JSON output as an unavailable-data result and explain the collector's `error` field.

Report these values when present:

- remaining and used percentage;
- reset time and time remaining;
- recent burn rate versus the sustainable budget rate;
- projected exhaustion time only when the sample supports it;
- the three fastest qualified 15-minute periods;
- the 28-day weekday heatmap with date ranges, window counts, and reliability;
- latest and 24-hour token totals;
- data quality, sample count, and freshness.

Label rate-limit values as local observations and forecasts as estimates. Do not call this an official quota API. Mention that the local Codex event schema may change.
Do not present a weekday heatmap cell as a stable pattern unless it contains at least three valid 15-minute windows. Treat sparse cells as insufficient data. Fastest-period rankings must come from a reliable heatmap cell and each ranked window must contain at least three quota snapshots.

## Build a usage plan

Use the snapshot as the user's baseline. If the user supplies a model, reasoning effort, or daily task count, compare scenarios as relative estimates rather than exact charges. Keep at least a 10% reserve by default. State the assumptions and prefer a range when history is sparse.

When no scenario is provided, offer three compact plans:

- conservative: lower-cost model or lower reasoning for routine tasks;
- balanced: higher effort only for ambiguous or high-value tasks;
- intensive: prioritize current work and clearly show early-exhaustion risk.

## Open the dashboard

Only when the user asks to open, show, or launch the dashboard, start:

`python <plugin-root>/scripts/quota_lens.py serve --port 4173`

The server must stay bound to `127.0.0.1`. Open `http://127.0.0.1:4173/` after it starts. If the port is occupied, choose another local port and tell the user which one.

## Privacy boundary

The collector allowlists only `token_count` events and numeric token/rate-limit fields. It does not return conversation content and does not transmit data. Do not weaken this boundary without explicit user approval.
