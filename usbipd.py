#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025 Alexander Brinkman
# SPDX-License-Identifier: GPL-3.0-or-later
"""usbipd - USB over IP daemon utility for macOS."""

import argparse
import logging
import sys
from importlib.metadata import PackageNotFoundError, version
from typing import Optional

from binding_configuration import BindingConfiguration
from usb_device import USBDevice, USBDeviceManager
from usbip_server import USBIPServer


def get_version() -> str:
    """Get the package version.

    Returns:
        The version string, or 'unknown' if not installed as a package.
    """
    try:
        return version("usbipd-python")
    except PackageNotFoundError:
        return "unknown (not installed as package)"


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application.

    Args:
        verbose: If True, enable debug logging.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def print_devices_table(devices: list[USBDevice], config: BindingConfiguration) -> None:
    """Print USB device information in a formatted table.

    Args:
        devices: A list of USBDevice objects.
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
        vid_pid = f"{device.vendor_id:04x}:{device.product_id:04x}"
        is_device_bound = config.is_bound(
            f"{device.vendor_id:04x}",
            f"{device.product_id:04x}",
            device.serial_number or "",
        )
        state = "Bound" if is_device_bound else "Not bound"
        bus_id = device.bus_id[:14]
        manufacturer = (device.manufacturer or "Unknown")[:20]
        product = (device.product or "Unknown")[:26]
        serial = (device.serial_number or "N/A")[:20]
        print(
            f"{bus_id:<14} {vid_pid:<12} {manufacturer:<20} {product:<26} {serial:<20} {state:<10}"
        )


def command_list() -> None:
    """Handle the 'list' command to display all connected USB devices."""
    print("USB Device List")
    print("=" * 110)

    config = BindingConfiguration()
    manager = USBDeviceManager()
    devices = manager.list_devices()

    print_devices_table(devices, config)
    print(f"\nTotal devices found: {len(devices)}")


def command_bind(bus_id: str) -> None:
    """Handle the 'bind' command to bind a USB device for sharing.

    The device is identified by bus ID but stored using VID:PID:serial
    for persistent identification across reconnects.

    Args:
        bus_id: The bus ID of the device to bind (format: bus-port, e.g., 1-3).
    """
    manager = USBDeviceManager()
    usb_device = manager.find_by_bus_id(bus_id)

    if usb_device is None:
        print(f"Error: Device not found: {bus_id}", file=sys.stderr)
        sys.exit(1)

    # Save binding to configuration using VID:PID:serial
    config = BindingConfiguration()
    added = config.add_binding(
        vendor_id=f"{usb_device.vendor_id:04x}",
        product_id=f"{usb_device.product_id:04x}",
        serial_number=usb_device.serial_number or "",
    )

    if added:
        print(f"Device bound successfully: {usb_device.device_id} (at {bus_id})")
        print(usb_device.get_detailed_info())
    else:
        print(f"Device is already bound: {bus_id}")


def command_unbind(bus_id: Optional[str] = None, unbind_all: bool = False) -> None:
    """Handle the 'unbind' command to remove USB device binding(s).

    The bus ID is used to identify the device, but the binding is removed
    based on VID:PID:serial stored in the configuration.

    Args:
        bus_id: The bus ID of the device to unbind (format: bus-port.port...).
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
    manager = USBDeviceManager()
    usb_device = manager.find_by_bus_id(bus_id)

    if usb_device is None:
        print(f"Error: Device not found: {bus_id}", file=sys.stderr)
        sys.exit(1)

    removed = config.remove_binding(
        f"{usb_device.vendor_id:04x}",
        f"{usb_device.product_id:04x}",
        usb_device.serial_number or "",
    )

    if removed:
        print(f"Device unbound successfully: {usb_device.device_id} (at {bus_id})")
    else:
        print(f"Device is not bound: {bus_id}")
        sys.exit(1)


def command_start(host: Optional[str] = None, ipv4_only: bool = False) -> None:
    """Handle the 'start' command to start the USBIP server."""
    if host is not None:
        server = USBIPServer(host=host)
    elif ipv4_only:
        server = USBIPServer(host="0.0.0.0")
    else:
        server = USBIPServer()
    manager = USBDeviceManager()

    # Load bound devices from configuration and export them
    config = BindingConfiguration()
    bindings = config.get_all_bindings()

    if not bindings:
        print("No devices are bound. Use 'usbipd bind --bus-id <bus-id>' to bind devices first.")
        sys.exit(1)

    exported_count = 0
    for binding in bindings:
        device_id = f"{binding['vendor_id']}:{binding['product_id']}"
        if binding.get("serial_number"):
            device_id += f":{binding['serial_number']}"

        usb_device = manager.find_by_binding(binding)
        if usb_device is None:
            print(f"Warning: Device {device_id} not found", file=sys.stderr)
            continue

        try:
            server.export_device(usb_device)
            print(f"Exported device: {device_id} (at {usb_device.bus_id})")
            exported_count += 1
        except (ValueError, LookupError) as error:
            print(
                f"Warning: Could not export device {device_id}: {error}",
                file=sys.stderr,
            )

    if exported_count == 0:
        print("No devices could be exported. Check that bound devices are still connected.")
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
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {get_version()}",
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
    start_parser = subparsers.add_parser("start", help="Start the USBIP server with bound devices")
    start_group = start_parser.add_mutually_exclusive_group()
    start_group.add_argument(
        "-4",
        help="Bind to IPv4 only (defaults to dual-stack)",
        dest="ipv4_only",
        action="store_true",
    )
    start_group.add_argument(
        "--host",
        help="Bind to specified host address",
        dest="host",
    )

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
        command_start(host=args.host, ipv4_only=args.ipv4_only)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
