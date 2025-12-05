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
- `requirements.txt`: Python package dependencies.

## Coding Standards

### Naming Conventions
- Use `snake_case` for variables, functions, and module names.
- Use `PascalCase` for class names.
- Use `UPPER_SNAKE_CASE` for constants.
- Use descriptive, meaningful names. Avoid single-letter variables except for loop counters.

### Code Quality
- Target Python 3.10+ features and syntax.
- Use type hints for all function signatures and return types.
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

### Testing
- Write unit tests for core functionality.
- Use `pytest` as the test framework.
- Mock USB device interactions in tests.
