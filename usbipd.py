#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2024 abrinkman
# SPDX-License-Identifier: GPL-3.0-or-later
"""
usbipd - USB over IP daemon utility for macOS.
"""

import argparse
import logging
import sys

import usb.backend.libusb1 as libusb1
import usb.core
import usb.util

from binding_configuration import BindingConfiguration
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
            else "N/A"
        )
    except (usb.core.USBError, ValueError):
        serial_number = "N/A"

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
    backend = libusb1.get_backend()
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
        state = "Bound" if config.is_bound(device["bus_id"]) else "Not bound"
        bus_id = device["bus_id"][:14]
        manufacturer = device["manufacturer"][:20]
        product = device["product"][:26]
        serial = device["serial_number"][:20]
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

    Args:
        bus_id: The bus ID of the device to bind (format: bus-port, e.g., 1-3).
    """
    try:
        usb_device = USBDevice(bus_id)
        device_info = usb_device.get_basic_info()

        # Save binding to configuration
        config = BindingConfiguration()
        added = config.add_binding(
            bus_id=device_info["bus_id"],
            vendor_id=device_info["vendor_id"],
            product_id=device_info["product_id"],
        )

        if added:
            print(f"Device bound successfully: {bus_id}")
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

    removed = config.remove_binding(bus_id)

    if removed:
        print(f"Device unbound successfully: {bus_id}")
    else:
        print(f"Device is not bound: {bus_id}")
        sys.exit(1)


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
        bus_id = binding["bus_id"]
        try:
            usb_device = USBDevice(bus_id)
            server.export_device(bus_id, usb_device.device)
            print(f"Exported device: {bus_id}")
            exported_count += 1
        except (ValueError, LookupError) as error:
            print(
                f"Warning: Could not export device {bus_id}: {error}", file=sys.stderr
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
