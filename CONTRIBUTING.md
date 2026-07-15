# Contributing

Thanks for helping build Codex Quota Lens.

## Ground rules

- Never commit real Codex session files or copied user prompts.
- Fixtures must be synthetic and must not contain usernames, emails, secrets, repository URLs, or absolute user paths.
- New source adapters must use an explicit field allowlist.
- Predictions must expose uncertainty, sample size, and source quality.
- Model and rate information must be versioned and cite an official source.

## Pull requests

Describe:

1. The user problem.
2. What changed and what is intentionally out of scope.
3. Privacy and schema compatibility impact.
4. Tests performed.
5. Screenshots using synthetic data for UI changes.

Keep pull requests narrow. Schema changes require fixtures for both the previous and new version.

