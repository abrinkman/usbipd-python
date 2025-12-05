# usbipd-python

A USB/IP server written in Python for sharing USB devices over the network, based on usbipd concepts. Works on MacOS using the `pyusb` library, but any system that supports `pyusb` should work.

Note: this is a very early proof-of-concept implementation, which was mainly built for learning purposes with
Copilot assistance. Use at your own risk.

## Instructions for running

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
