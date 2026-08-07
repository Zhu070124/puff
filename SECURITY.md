# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

## Security Architecture

### Path Sandbox

All file system operations are restricted to a configurable root directory. Path traversal attacks (e.g., `../../../etc/passwd`) are detected and blocked. Every path is resolved and validated against the sandbox boundary before any read or write.

### API Key Isolation

API keys and secrets are never logged, never returned in API responses, and never written to disk in plaintext. Keys are loaded from environment variables or a secure configuration store. The server masks sensitive values in error messages and debug output.

### Rate Limiting

Per-client rate limiting prevents brute-force and denial-of-service attacks. Limits are configurable and apply independently to each connecting client. Excessive requests return HTTP 429 with a `Retry-After` header.

### File Permissions

Operations within the sandbox are gated by explicit read/write/execute permission checks. The permission model is deny-by-default — a path has no access unless explicitly granted.

## Reporting a Vulnerability

If you discover a security vulnerability, please **do not** open a public issue.

Send details to the maintainer directly. Include:

- A description of the vulnerability
- Steps to reproduce
- Affected versions
- Any suggested mitigations

You should receive a response within 72 hours. Once confirmed, we will:

1. Acknowledge the report and assign a severity
2. Develop and test a fix
3. Release a patch
4. Publish an advisory (crediting the reporter if desired)

## Best Practices for Deployments

- Always run Puff behind a reverse proxy (nginx, Caddy) in production.
- Use environment variables for all secrets; never hardcode credentials.
- Keep the sandbox root on a dedicated volume with no sensitive system files.
- Enable rate limiting with conservative defaults.
- Regularly update to the latest patch release.
