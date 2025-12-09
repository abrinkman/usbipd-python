# usbipd-python

[![Downloads](https://img.shields.io/github/downloads/abrinkman/usbipd-python/total)](https://github.com/abrinkman/usbipd-python/releases)
[![REUSE Compliant](https://img.shields.io/badge/reuse-compliant-green.svg)](https://reuse.software/)
[![Lint](https://github.com/abrinkman/usbipd-python/actions/workflows/lint.yml/badge.svg)](https://github.com/abrinkman/usbipd-python/actions/workflows/lint.yml)

A USB/IP server written in Python 3 for sharing USB devices over the network. This implementation uses the `pyusb` library and the `libusb` backend to support cross-platform USB device access on macOS and Linux.

> **Note:** This is an early-stage implementation, primarily created for learning purposes. Simple USB devices generally work well, but more complex or HID-based devices may experience issues. HID devices are managed by OS kernel drivers on macOS and Windows, making them difficult to detach without OS-native code or custom drivers. Contributions are welcome!

## Installation

### Users

Install from PyPI:

```bash
pip install usbipd-python
usbipd --help
```

### Developers

1. Clone the repository:

   ```bash
   git clone https://github.com/abrinkman/usbipd-python.git
   cd usbipd-python
   ```

2. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install in development mode with dev dependencies:

   ```bash
   pip install -e ".[dev]"
   ```

## System Requirements

- **Python:** 3.9 or higher
- **libusb:** Install using your system package manager
  - macOS: `brew install libusb`
  - Linux (Debian/Ubuntu): `sudo apt-get install libusb-1.0-0-dev`
  - Linux (Fedora/RHEL): `sudo dnf install libusbx-devel`

## Usage

### List USB Devices

Display all available USB devices:

```bash
usbipd list
```

### Bind a Device

Bind a USB device by its bus ID to make it available for sharing:

```bash
usbipd bind --bus-id <bus-id>
```

Note that although you need to bind using the bus-id, in reality bindings are stored persistently using the device's VID:PID:serial. This means that even if the bus ID changes, devices are still recognized. Devices without a serial number are matched by VID:PID only.

### Start the Server

For MacOS and perhaps other operating systems you will need to start the server with elevated privileges, as the underlying `libusb` library requires exclusive access to USB devices:

```bash
sudo usbipd start
```

Add `-v` or `--verbose` for debug output:

```bash
sudo usbipd -v start
```

If your user lacks permissions the application will warn you for this when attaching a device. Please note that these kind of issues can lead to undefined behavior, blue screens or kernel panics on either side. You have been warned!

### Connect to the Server

Use a USB/IP client on another machine to connect and access shared devices.

## Development

### Code Quality

Run linting and formatting checks using `ruff`:

```bash
ruff check .          # Check for linting issues
ruff format --check . # Check code formatting
ruff format .         # Auto-format code
```

Run type checking:

```bash
mypy --ignore-missing-imports .
```

### Project Structure

- `usbipd.py` - Main CLI entry point
- `usb_device.py` - `USBDevice` wrapper class for `pyusb` device access
- `usbip_server.py` - `USBIPServer` class implementing the USB/IP protocol
- `binding_configuration.py` - `BindingConfiguration` class for XML-based device binding storage
- `libusb_backend.py` - Cross-platform libusb backend loader for `pyusb`

### License

Licensed under GPL-3.0. See [LICENSE](LICENSE) for details.
