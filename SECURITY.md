# Security Policy

## Security model

XFI AI is an administrative AI gateway and control-plane. Treat the following as security-sensitive:

- AI provider API keys and XFI client tokens;
- `XFI_AI_ADMIN_KEY` and GitHub credentials used by Code Agent;
- VPS SSH credentials and agent sockets;
- project files modified by the administrative editors;
- audit logs and provider fingerprints.

Secrets must remain outside Git and must not be included in issue reports, logs, prompts, screenshots, or Pull Requests.

## Built-in protections

- administrative access uses an explicit admin key or short-lived HMAC session;
- API keys are validated and rate-limited;
- provider detection returns safe metadata rather than storing the tested key;
- Code Agent works through reviewed changes and Pull Requests;
- sensitive paths are blocked from agent editing;
- project editors validate paths, file hashes, file size, syntax/type checks, and roll back failed changes;
- service restarts use explicit allowlists;
- shell commands are executed with fixed argument vectors and without shell interpolation;
- CI runs tests, lint, security checks, dependency audit, and shell validation.

## Reporting a vulnerability

Do not publish credentials or an exploitable proof of concept in a public issue.

For a security report, provide:

1. affected component and file/endpoint;
2. impact and attack prerequisites;
3. minimal reproduction steps without real secrets;
4. suggested mitigation, if known.

Rotate any credential that may have been exposed before reporting the incident.

## Development rule

Security-sensitive changes must preserve the existing CI security checks. Never disable Bandit, dependency auditing, tests, or shell validation to make a build pass.
