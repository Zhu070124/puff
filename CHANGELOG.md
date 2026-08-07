# Changelog

All notable changes to Puff will be documented in this file.

## [1.0.0] — 2026-08-08

### Added
- **Path sandbox security** — all file operations are confined to an allowed directory tree, preventing path traversal and unauthorized access.
- **SOUL hot reload** — skills and personality definitions reload at runtime without restarting the server.
- **Rate limiter** — configurable per-client rate limiting to protect against abuse.
- **File permissions** — fine-grained access control for read/write/execute operations within the sandbox.
- **Docker support** — `Dockerfile` and `docker-compose.yml` for containerized deployment.
- **22 tests** — test suite covering API endpoints, sandbox enforcement, and core functionality.
- **Graceful shutdown** — clean signal handling for SIGINT and SIGTERM, draining connections before exit.
- **MIT license** — permissive open-source licensing.
- **CI/CD** — GitHub Actions workflow running the test suite on push and pull request.
- **SECURITY.md** — vulnerability reporting and security policy documentation.
