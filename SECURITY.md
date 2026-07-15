# Security Policy

## Scope

Codex Quota Lens reads local telemetry-like session events. Reports involving unintended collection of prompt content, source code, credentials, absolute paths, network exposure, or unsafe update behavior are high priority.

## Reporting

Do not open a public issue containing real Codex session files, prompts, source code, API keys, cookies, account identifiers, or full filesystem paths.

Before the repository publishes a private security contact, create a minimal public issue that says only that you need a private reporting channel. Maintainers should then enable GitHub Private Vulnerability Reporting.

## Data handling promise

- Raw prompts, responses, reasoning, tool arguments, tool outputs, and file contents are outside the collection allowlist.
- The default product does not upload analytics.
- Export uses aggregated data unless a user explicitly selects otherwise.
- Project and session identifiers are locally salted hashes.

## Supported versions

During design and pre-release development, only the latest commit on `main` is supported.

