# Contributing to Puff

## Code Style

- Follow [PEP 8](https://peps.python.org/pep-0008/) with **4-space indentation** (no tabs)
- Keep functions small and single-purpose
- Use descriptive variable names; avoid single-letter names except in comprehensions
- Add docstrings for public functions and classes
- No dependencies unless strictly necessary — prefer stdlib

## Commit Format

Use conventional commit messages:

```
type: description
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `style`

Examples:

```
feat: add streaming response support
fix: handle empty SOUL.md gracefully
docs: update environment variable table
```

## PR Process

1. **Fork** the repository
2. **Branch** from `main` — name it `feat/short-description` or `fix/short-description`
3. **Implement** your change, following the code style above
4. **Test** — run `python tests/` before opening the PR (see below)
5. **Open a PR** against `main` with a clear description of what changed and why
6. **Review** — a maintainer will review within a few days; be responsive to feedback

## Testing

Before submitting a PR:

```bash
# Run all tests
python -m pytest tests/ -v

# Or if pytest is not installed (stdlib only)
python tests/
```

All existing tests must pass. Add new tests for new functionality.

## Need Help?

Open an issue on GitHub. We respond within a few days.
