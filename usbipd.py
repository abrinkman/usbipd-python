#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025 abrinkman
# SPDX-License-Identifier: GPL-3.0-or-later
"""
usbipd - USB over IP daemon utility for macOS.
"""

import argparse
import logging
import sys

import usb.core
import usb.util

from binding_configuration import BindingConfiguration
from libusb_backend import get_backend
from usb_device import USBDevice
from usbip_server import USBIPServer


def setup_logging(verbose: bool = False) -> None:
    """
    Configure logging for the application.

    Args:
        verbose: If True, enable debug logging.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _clean_usb_string(value: str) -> str:
    """
    Clean a USB string by removing null characters and everything after.

    Some USB devices return strings with embedded null characters and garbage
    data. This function truncates at the first null character.

    Args:
        value: The raw USB string.

    Returns:
        The cleaned string, truncated at the first null character.
    """
    if "\x00" in value:
        return value.split("\x00")[0]
    return value


def get_usb_device_info(device: usb.core.Device) -> dict:
    """
    Extract relevant information from a USB device.

    Args:
        device: A USB device object from pyusb.

    Returns:
        A dictionary containing device information.
    """
    try:
        manufacturer = (
            _clean_usb_string(usb.util.get_string(device, device.iManufacturer))
            if device.iManufacturer
            else "Unknown"
        )
    except (usb.core.USBError, ValueError):
        manufacturer = "Unknown"

    try:
        product = (
            _clean_usb_string(usb.util.get_string(device, device.iProduct))
            if device.iProduct
            else "Unknown"
        )
    except (usb.core.USBError, ValueError):
        product = "Unknown"

    try:
        serial_number = (
            _clean_usb_string(usb.util.get_string(device, device.iSerialNumber))
            if device.iSerialNumber
            else ""
        )
    except (usb.core.USBError, ValueError):
        serial_number = ""

    # Use full port path for unique bus ID (e.g., 1-4.3 for bus 1, port 4, port 3)
    if device.port_numbers:
        port_path = ".".join(str(p) for p in device.port_numbers)
        bus_id = f"{device.bus}-{port_path}"
    else:
        bus_id = f"{device.bus}-0"

    return {
        "bus_id": bus_id,
        "vendor_id": f"{device.idVendor:04x}",
        "product_id": f"{device.idProduct:04x}",
        "manufacturer": manufacturer,
        "product": product,
        "serial_number": serial_number,
    }


def list_usb_devices() -> list[dict]:
    """
    Find and list all connected USB devices.

    Uses a fresh libusb backend to ensure devices that went idle
    are properly re-enumerated.

    Returns:
        A list of dictionaries containing information about each USB device.
    """
    # Create a fresh backend to force re-enumeration of USB devices
    # This fixes issues where idle devices are not listed
    backend = get_backend()
    devices = usb.core.find(find_all=True, backend=backend)
    device_list = []

    for device in devices:
        device_info = get_usb_device_info(device)
        device_list.append(device_info)

    return device_list


def print_usb_devices(devices: list[dict], config: BindingConfiguration) -> None:
    """
    Print USB device information in a formatted table.

    Args:
        devices: A list of device information dictionaries.
        config: The binding configuration to check device state.
    """
    if not devices:
        print("No USB devices found.")
        return

    print(
        f"{'BUSID':<14} {'VID:PID':<12} {'Manufacturer':<20} {'Product':<26} "
        f"{'Serial':<20} {'State':<10}"
    )
    print("-" * 105)

    for device in devices:
        vid_pid = f"{device['vendor_id']}:{device['product_id']}"
        is_device_bound = config.is_bound(
            device["vendor_id"], device["product_id"], device["serial_number"]
        )
        state = "Bound" if is_device_bound else "Not bound"
        bus_id = device["bus_id"][:14]
        manufacturer = device["manufacturer"][:20]
        product = device["product"][:26]
        serial = device["serial_number"][:20] if device["serial_number"] else "N/A"
        print(
            f"{bus_id:<14} "
            f"{vid_pid:<12} "
            f"{manufacturer:<20} "
            f"{product:<26} "
            f"{serial:<20} "
            f"{state:<10}"
        )


def command_list() -> None:
    """Handle the 'list' command to display all connected USB devices."""
    print("USB Device List")
    print("=" * 110)
    config = BindingConfiguration()
    devices = list_usb_devices()
    print_usb_devices(devices, config)
    print(f"\nTotal devices found: {len(devices)}")


def command_bind(bus_id: str) -> None:
    """
    Handle the 'bind' command to bind a USB device for sharing.

    The device is identified by bus ID but stored using VID:PID:serial
    for persistent identification across reconnects.

    Args:
        bus_id: The bus ID of the device to bind (format: bus-port, e.g., 1-3).
    """
    try:
        usb_device = USBDevice(bus_id)
        device_info = usb_device.get_basic_info()

        # Clean serial number (remove null chars and use empty string if N/A)
        serial_number = device_info["serial_number"]
        if serial_number:
            serial_number = serial_number.split("\x00")[0]

        # Save binding to configuration using VID:PID:serial
        config = BindingConfiguration()
        added = config.add_binding(
            vendor_id=device_info["vendor_id"],
            product_id=device_info["product_id"],
            serial_number=serial_number,
        )

        if added:
            device_id = f"{device_info['vendor_id']}:{device_info['product_id']}"
            if serial_number:
                device_id += f":{serial_number}"
            print(f"Device bound successfully: {device_id} (at {bus_id})")
            print(usb_device.get_device_information())
        else:
            print(f"Device is already bound: {bus_id}")
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
    except LookupError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)


def command_unbind(bus_id: str | None = None, unbind_all: bool = False) -> None:
    """
    Handle the 'unbind' command to remove USB device binding(s).

    The bus ID is used to identify the device, but the binding is removed
    based on VID:PID:serial stored in the configuration.

    Args:
        bus_id: The bus ID of the device to unbind (format: bus-port.port..., e.g., 1-4.3).
        unbind_all: If True, remove all bindings.
    """
    config = BindingConfiguration()

    if unbind_all:
        count = config.clear_all_bindings()
        if count > 0:
            print(f"Removed {count} device binding(s).")
        else:
            print("No devices were bound.")
        return

    if not bus_id:
        print("Error: --bus-id or --all is required.", file=sys.stderr)
        sys.exit(1)

    # Look up the device to get its VID:PID:serial
    try:
        usb_device = USBDevice(bus_id)
        device_info = usb_device.get_basic_info()
        serial_number = device_info["serial_number"]
        if serial_number:
            serial_number = serial_number.split("\x00")[0]

        removed = config.remove_binding(
            device_info["vendor_id"], device_info["product_id"], serial_number
        )

        if removed:
            device_id = f"{device_info['vendor_id']}:{device_info['product_id']}"
            if serial_number:
                device_id += f":{serial_number}"
            print(f"Device unbound successfully: {device_id} (at {bus_id})")
        else:
            print(f"Device is not bound: {bus_id}")
            sys.exit(1)
    except (ValueError, LookupError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)


def _find_device_by_binding(binding: dict) -> tuple[str, usb.core.Device] | None:
    """
    Find a connected USB device matching the binding's VID:PID:serial.

    Args:
        binding: A binding dictionary with vendor_id, product_id, and serial_number.

    Returns:
        A tuple of (bus_id, device) if found, None otherwise.
    """
    backend = get_backend()
    devices = usb.core.find(find_all=True, backend=backend)

    target_vid = int(binding["vendor_id"], 16)
    target_pid = int(binding["product_id"], 16)
    target_serial = binding.get("serial_number", "")

    for device in devices:
        if device.idVendor != target_vid or device.idProduct != target_pid:
            continue

        # Get device serial number
        device_serial = ""
        try:
            if device.iSerialNumber:
                device_serial = usb.util.get_string(device, device.iSerialNumber)
                if device_serial:
                    device_serial = device_serial.split("\x00")[0]
        except (usb.core.USBError, ValueError):
            pass

        # Match: both have no serial, or serials match
        if target_serial == device_serial:
            # Build bus ID
            if device.port_numbers:
                port_path = ".".join(str(p) for p in device.port_numbers)
                bus_id = f"{device.bus}-{port_path}"
            else:
                bus_id = f"{device.bus}-0"
            return (bus_id, device)

    return None


def command_start() -> None:
    """Handle the 'start' command to start the USBIP server."""
    server = USBIPServer()

    # Load bound devices from configuration and export them
    config = BindingConfiguration()
    bindings = config.get_all_bindings()

    if not bindings:
        print(
            "No devices are bound. Use 'usbipd bind --bus-id <bus-id>' to bind devices first."
        )
        sys.exit(1)

    exported_count = 0
    for binding in bindings:
        device_id = f"{binding['vendor_id']}:{binding['product_id']}"
        if binding.get("serial_number"):
            device_id += f":{binding['serial_number']}"

        result = _find_device_by_binding(binding)
        if result is None:
            print(f"Warning: Device {device_id} not found", file=sys.stderr)
            continue

        bus_id, device = result
        try:
            server.export_device(bus_id, device)
            print(f"Exported device: {device_id} (at {bus_id})")
            exported_count += 1
        except (ValueError, LookupError) as error:
            print(
                f"Warning: Could not export device {device_id}: {error}",
                file=sys.stderr,
            )

    if exported_count == 0:
        print(
            "No devices could be exported. Check that bound devices are still connected."
        )
        sys.exit(1)

    try:
        print(f"\nStarting USBIP server with {exported_count} device(s)...")
        server.start()
    except KeyboardInterrupt:
        print("\nServer stopped by user.")
        server.stop()
    except Exception as error:
        print(f"Failed to start USBIP server: {error}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Main entry point for usbipd."""
    parser = argparse.ArgumentParser(
        prog="usbipd",
        description="USB over IP daemon utility for macOS - manage and share USB devices.",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose (debug) logging",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # List command
    subparsers.add_parser("list", help="List all connected USB devices")

    # Bind command
    bind_parser = subparsers.add_parser("bind", help="Bind a USB device for sharing")
    bind_parser.add_argument(
        "-b",
        "--bus-id",
        required=True,
        help="Bus ID of the device to bind (format: bus-port, e.g., 1-3)",
    )

    # Unbind command
    unbind_parser = subparsers.add_parser("unbind", help="Remove a USB device binding")
    unbind_group = unbind_parser.add_mutually_exclusive_group(required=True)
    unbind_group.add_argument(
        "-b",
        "--bus-id",
        help="Bus ID of the device to unbind (format: bus-port.port..., e.g., 1-4.3)",
    )
    unbind_group.add_argument(
        "-a",
        "--all",
        action="store_true",
        dest="unbind_all",
        help="Remove all device bindings",
    )

    # Start command
    subparsers.add_parser("start", help="Start the USBIP server with bound devices")

    args = parser.parse_args()

    # Setup logging
    setup_logging(verbose=args.verbose)

    if args.command == "list":
        command_list()
    elif args.command == "bind":
        command_bind(args.bus_id)
    elif args.command == "unbind":
        command_unbind(bus_id=args.bus_id, unbind_all=args.unbind_all)
    elif args.command == "start":
        command_start()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
