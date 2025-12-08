# Copilot Instructions

## Project Context
- This is a Python 3 command-line application called `usbipd-python`.
- The application implements a USB/IP server for sharing USB devices over the network.
- It uses the `pyusb` library for USB device interaction and implements the USB/IP protocol.
- Licensed under GPL-3.0.

## Project Structure
- `usbipd.py`: Main entry point and CLI implementation using `argparse`.
- `usb_device.py`: `USBDevice` class wrapping `pyusb` device access.
- `usbip_server.py`: `USBIPServer` class implementing the USB/IP protocol.
- `binding_configuration.py`: `BindingConfiguration` class for XML-based device binding storage.
- `libusb_backend.py`: Cross-platform libusb backend loader for pyusb.
- `requirements.txt`: Python package dependencies.
- `requirements-dev.txt`: Development dependencies (ruff, mypy).

## Coding Standards

### Naming Conventions
- Use `snake_case` for variables, functions, and module names.
- Use `PascalCase` for class names.
- Use `UPPER_SNAKE_CASE` for constants.
- Use descriptive, meaningful names. Avoid single-letter variables except for loop counters.

### Code Quality
- Target Python 3.9+ compatibility (use `Optional[T]` from typing, not `T | None`).
- Use type hints for all function signatures and return types.
- Use `from typing import Optional` for optional types (Python 3.9 compatibility).
- Write modular, reusable code with clear separation of concerns.
- Handle errors gracefully with appropriate error messages to stderr.
- Use `argparse` for command-line argument parsing.
- Exit with appropriate exit codes (0 for success, non-zero for errors).

### Documentation
- Include docstrings for all modules, classes, and functions.
- Use Google-style docstrings with Args, Returns, and Raises sections.
- Add inline comments only for complex logic.

### CLI Design
- Follow Unix conventions for command-line tools.
- Provide helpful `--help` output for all commands and subcommands.
- Use subcommands for different operations (e.g., `list`, `bind`, `start`).
- Support `-v/--verbose` flag for debug logging.

### Error Handling
- Catch specific exceptions rather than bare `except:`.
- Provide user-friendly error messages.
- Log detailed errors at debug level for troubleshooting.
- Handle USB permission errors with helpful messages about sudo requirements.

### Security
- Never hardcode sensitive information.
- Validate all user input before processing.
- Handle USB permissions errors gracefully with helpful messages.

### Dependencies
- Keep dependencies minimal to reduce installation complexity.
- Pin dependency versions in `requirements.txt`.
- Document system-level dependencies (e.g., `libusb`).

## USB/IP Protocol
- Protocol version: 1.1.1 (0x0111)
- Default port: 3240
- All protocol fields are big-endian (network byte order)
- Key operations: OP_REQ_DEVLIST, OP_REP_DEVLIST, OP_REQ_IMPORT, OP_REP_IMPORT
- URB commands: USBIP_CMD_SUBMIT, USBIP_CMD_UNLINK, USBIP_RET_SUBMIT, USBIP_RET_UNLINK

## Device Binding
- Users specify devices by bus ID (e.g., `20-4.3`) for bind/unbind commands
- Bindings are stored using VID:PID:serial for persistent identification
- Devices without serial numbers are matched by VID:PID only
- When starting the server, devices are matched by VID:PID:serial and resolved to current bus ID

## Libusb Backend
- Use the `libusb_backend.py` module for cross-platform libusb backend loading
- Always create a fresh backend for device enumeration to handle idle devices
- The backend handles bundled libusb libraries on macOS, Windows, and Linux
- Import with `from libusb_backend import get_backend`

## Development Workflow

### Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running the Application
```bash
./usbipd.py list                    # List USB devices
./usbipd.py bind --bus-id <id>      # Bind a device
sudo ./usbipd.py start              # Start server (requires root on macOS)
./usbipd.py -v start                # Start with verbose logging
```

### System Requirements
- macOS or Linux
- `libusb` installed (`brew install libusb` on macOS)
- Root/sudo access for USB device claiming

### Linting and Formatting
- Use `ruff` for linting and formatting.
- Run `ruff check .` to check for linting issues.
- Run `ruff format .` to format code.
- Always verify changes pass both checks before completing work.

### Testing
- Write unit tests for core functionality.
- Use `pytest` as the test framework.
- Mock USB device interactions in tests.

## Verification
- **Linting**: Run `ruff check .` to ensure no linting errors.
- **Formatting**: Run `ruff format --check .` to ensure code is properly formatted.
- **Type Checking**: Run `mypy --ignore-missing-imports .` to verify type hints.
