## Contributing

### Setup
- Python 3.11+; create a virtualenv and install dev deps: `pip install -e .[dev]`.

### Development workflow
- Run `ruff format .` then `ruff check .` before sending changes.
- Run `mypy --ignore-missing-imports .` for type checks.
- Run `reuse lint` after adding or modifying files to keep licensing headers intact.
- Prefer small, focused PRs with CLI help text updated when flags/commands change.

### Testing
- Use `pytest`; mock USB devices/libusb interactions rather than touching hardware.
- Avoid running privileged USB operations (`sudo`) in tests or automation.
