# usbipd-python

[![Downloads](https://img.shields.io/github/downloads/abrinkman/usbipd-python/total)](https://github.com/abrinkman/usbipd-python/releases)
[![REUSE Compliant](https://img.shields.io/badge/reuse-compliant-green.svg)](https://reuse.software/)
[![Lint](https://github.com/abrinkman/usbipd-python/actions/workflows/lint.yml/badge.svg)](https://github.com/abrinkman/usbipd-python/actions/workflows/lint.yml)

A USB/IP server written in Python for sharing USB devices over the network, based on usbipd concepts. Works on MacOS using the `pyusb` library, but any system that supports `pyusb` should work.

Note: this is a very early proof-of-concept implementation, which was mainly built for learning purposes with
Copilot assistance. It seems to work, more or less, for simple USB devices like a joystick, but more complex devices may not work correctly. Use at your own risk.

## Preparing the environment

Make sure you have a Python environment present, with the required packages present. Or create a venv:

1. Create venv:
   ```bash
   python3 -m venv .venv
   ```
2. Load the venv:
   ```bash
   source .venv/bin/activate
   ```
3. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```

## Running the application

1. List USB devices:
   ```bash
   ./usbipd.py list
   ```
2. Bind a USB device by its bus ID:
   ```bash
    ./usbipd.py bind --bus-id <bus-id>
   ```
3. Start the USBIP server:
   ```bash
    sudo ./usbipd.py start
    ```
    Note: Root privileges may be required to access USB devices on MacOS.
4. Connect to the server from a client using USB/IP tools.
