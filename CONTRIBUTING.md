# Contributing

We welcome contributions to `JobTrackerSync`! Please follow these guidelines to get started.

---

## Development Setup

To set up a local development environment:

```bash
git clone https://github.com/hsummerhays/JobTrackerSync.git
cd JobTrackerSync

python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

---

## Code Style

Follow the existing Python code style. Prefer writing small, focused functions with descriptive names, and maintain high standards of code readability and commentary.

---

## Contribution Workflow

1. **Open an Issue**: Discuss any major proposed changes or bugs by opening an issue first.
2. **Keep Parsers Isolated**: Keep provider-specific parsing code isolated to prevent one provider's changes from breaking others.
3. **Add Regression Tests**: Ensure any changes or additions to the parsers include appropriate unit/regression tests in the `tests/` directory.
4. **Run Tests**: Verify that the entire test suite passes before submitting:
   ```bash
   pytest
   ```

---

## Pull Request Checklist

Before submitting a Pull Request, please ensure:

- [ ] Tests have been added or updated for new features
- [ ] All existing unit tests pass successfully
- [ ] Parser modifications are isolated and provider-specific
- [ ] Documentation (`README.md`, architecture guides, etc.) has been updated if user-facing behavior changed
