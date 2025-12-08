# SPDX-FileCopyrightText: 2025 Alexander Brinkman
# SPDX-License-Identifier: GPL-3.0-or-later
"""USB device wrapper and manager module for USB/IP server.

This module provides classes for accessing and managing USB devices:
- USBDevice: Wrapper class for individual USB device access
- USBDeviceManager: Manager class for device enumeration and lookup
"""

import logging
import re
from typing import Optional

import usb.core
import usb.util

from libusb_backend import get_backend


class USBDevice:
    """Wrapper class for USB device access via pyusb.

    Provides convenient access to USB device properties and descriptors.

    Attributes:
        device: The underlying pyusb device object.
        bus_id: The bus identifier string (e.g., "20-4.2.1").
    """

    def __init__(self, device: usb.core.Device) -> None:
        """Initialize USBDevice with a pyusb device.

        Args:
            device: A pyusb Device object.
        """
        self.device = device
        self.bus_id = self.build_bus_id(device)
        self._manufacturer: Optional[str] = None
        self._product: Optional[str] = None
        self._serial_number: Optional[str] = None
        self._strings_loaded = False

    @staticmethod
    def clean_usb_string(value: Optional[str]) -> Optional[str]:
        """Clean a USB string by removing null characters and whitespace.

        USB strings sometimes contain garbage data after null terminators.
        This method extracts only the valid portion of the string.

        Args:
            value: The USB string to clean, or None.

        Returns:
            The cleaned string, or None if input was None or empty.
        """
        if value is None:
            return None
        # Split at null character and take first part, then strip whitespace
        cleaned = value.split("\x00")[0].strip()
        return cleaned if cleaned else None

    @staticmethod
    def build_bus_id(device: usb.core.Device) -> str:
        """Build a bus ID string from a pyusb device.

        The bus ID format is "bus-port.port.port" (e.g., "20-4.2.1").

        Args:
            device: A pyusb Device object.

        Returns:
            The bus ID string.
        """
        port_numbers = device.port_numbers
        if port_numbers:
            port_path = ".".join(str(port) for port in port_numbers)
            return f"{device.bus}-{port_path}"
        return f"{device.bus}-{device.address}"

    @staticmethod
    def parse_bus_id(bus_id: str) -> tuple[int, tuple[int, ...]]:
        """Parse a bus ID string into bus number and port numbers.

        Args:
            bus_id: The bus ID string (e.g., "20-4.2.1").

        Returns:
            A tuple of (bus_number, port_numbers_tuple).

        Raises:
            ValueError: If the bus ID format is invalid.
        """
        match = re.match(r"^(\d+)-(.+)$", bus_id)
        if not match:
            raise ValueError(f"Invalid bus ID format: {bus_id}")

        bus_number = int(match.group(1))
        port_path = match.group(2)
        port_numbers = tuple(int(port) for port in port_path.split("."))
        return bus_number, port_numbers

    def _load_strings(self) -> None:
        """Load USB string descriptors from the device.

        This is done lazily to avoid claiming devices unnecessarily.
        Errors are logged but don't raise exceptions.
        """
        if self._strings_loaded:
            return

        self._strings_loaded = True
        logger = logging.getLogger(__name__)

        try:
            if self.device.iManufacturer:
                raw_manufacturer = usb.util.get_string(self.device, self.device.iManufacturer)
                self._manufacturer = self.clean_usb_string(raw_manufacturer)
        except (usb.core.USBError, ValueError) as error:
            logger.debug("Could not read manufacturer string: %s", error)

        try:
            if self.device.iProduct:
                raw_product = usb.util.get_string(self.device, self.device.iProduct)
                self._product = self.clean_usb_string(raw_product)
        except (usb.core.USBError, ValueError) as error:
            logger.debug("Could not read product string: %s", error)

        try:
            if self.device.iSerialNumber:
                raw_serial = usb.util.get_string(self.device, self.device.iSerialNumber)
                self._serial_number = self.clean_usb_string(raw_serial)
        except (usb.core.USBError, ValueError) as error:
            logger.debug("Could not read serial number string: %s", error)

    @property
    def vendor_id(self) -> int:
        """Get the vendor ID (VID) of the device."""
        return int(self.device.idVendor)

    @property
    def product_id(self) -> int:
        """Get the product ID (PID) of the device."""
        return int(self.device.idProduct)

    @property
    def manufacturer(self) -> Optional[str]:
        """Get the manufacturer string of the device."""
        self._load_strings()
        return self._manufacturer

    @property
    def product(self) -> Optional[str]:
        """Get the product string of the device."""
        self._load_strings()
        return self._product

    @property
    def serial_number(self) -> Optional[str]:
        """Get the serial number string of the device."""
        self._load_strings()
        return self._serial_number

    @property
    def device_id(self) -> str:
        """Get the device identity string (VID:PID:serial or VID:PID)."""
        self._load_strings()
        if self._serial_number:
            return f"{self.vendor_id:04x}:{self.product_id:04x}:{self._serial_number}"
        return f"{self.vendor_id:04x}:{self.product_id:04x}"

    def to_dict(self) -> dict[str, Optional[str]]:
        """Get basic device information as a dictionary.

        Returns:
            Dictionary with bus_id, vid, pid, manufacturer, product, and serial.
        """
        return {
            "bus_id": self.bus_id,
            "vid": f"{self.vendor_id:04x}",
            "pid": f"{self.product_id:04x}",
            "manufacturer": self.manufacturer,
            "product": self.product,
            "serial": self.serial_number,
        }

    def claim(self) -> bool:
        """Claim the device for exclusive access.

        Detaches kernel drivers (on Linux) and claims all interfaces.
        On macOS, kernel driver detachment is not supported by libusb, so HID
        devices (mice, keyboards) may not work correctly.

        Returns:
            True if the device was claimed successfully, False otherwise.
        """
        logger = logging.getLogger(__name__)
        access_denied = False
        kernel_driver_warning_shown = False

        try:
            # Try to set configuration if not already set
            try:
                config = self.device.get_active_configuration()
            except usb.core.USBError:
                try:
                    self.device.set_configuration()
                    config = self.device.get_active_configuration()
                except usb.core.USBError as error:
                    if error.errno == 13:  # Access denied
                        logger.error(
                            "Access denied when setting device configuration. "
                            "Try running with sudo."
                        )
                        return False
                    logger.warning("Could not set configuration: %s", error)
                    return False

            # Detach kernel drivers and claim all interfaces
            for interface in config:
                interface_number = interface.bInterfaceNumber

                # Try to detach kernel driver
                try:
                    if self.device.is_kernel_driver_active(interface_number):
                        try:
                            self.device.detach_kernel_driver(interface_number)
                            logger.info(
                                "Detached kernel driver from interface %d",
                                interface_number,
                            )
                        except usb.core.USBError as error:
                            if not kernel_driver_warning_shown:
                                logger.warning(
                                    "Could not detach kernel driver from interface "
                                    "%d: %s. HID devices may not work correctly.",
                                    interface_number,
                                    error,
                                )
                                kernel_driver_warning_shown = True
                except NotImplementedError:
                    # macOS doesn't support is_kernel_driver_active/detach_kernel_driver
                    if not kernel_driver_warning_shown:
                        if interface.bInterfaceClass == 3:  # HID class
                            logger.warning(
                                "Cannot detach kernel driver on macOS. "
                                "HID devices (mice, keyboards) may not work correctly "
                                "as macOS will still consume input events."
                            )
                            kernel_driver_warning_shown = True

                # Claim the interface
                try:
                    usb.util.claim_interface(self.device, interface_number)
                    logger.debug("Claimed interface %d", interface_number)
                except usb.core.USBError as error:
                    if error.errno == 13:  # Access denied
                        access_denied = True
                        logger.debug("Access denied for interface %d", interface_number)
                    else:
                        logger.warning("Could not claim interface %d: %s", interface_number, error)

        except usb.core.USBError as error:
            if error.errno == 13:
                access_denied = True
            logger.warning("Error claiming device: %s", error)

        if access_denied:
            logger.error("Insufficient permissions to access USB device. Try running with sudo.")
            return False

        return True

    def release(self) -> None:
        """Release all interfaces of the device.

        Should be called when done using the device to allow other
        processes to access it.
        """
        logger = logging.getLogger(__name__)
        try:
            config = self.device.get_active_configuration()
            for interface in config:
                interface_number = interface.bInterfaceNumber
                try:
                    usb.util.release_interface(self.device, interface_number)
                    logger.debug("Released interface %d", interface_number)
                except usb.core.USBError as error:
                    logger.debug("Could not release interface %d: %s", interface_number, error)
        except usb.core.USBError as error:
            logger.debug("Could not get configuration for release: %s", error)

    def get_detailed_info(self) -> str:
        """Get detailed device information as a formatted string.

        Returns:
            Multi-line string with device details including configurations
            and endpoints.
        """
        lines = [
            f"Bus ID: {self.bus_id}",
            f"Vendor ID: 0x{self.vendor_id:04x}",
            f"Product ID: 0x{self.product_id:04x}",
            f"Manufacturer: {self.manufacturer or 'N/A'}",
            f"Product: {self.product or 'N/A'}",
            f"Serial Number: {self.serial_number or 'N/A'}",
            f"Device Class: 0x{self.device.bDeviceClass:02x}",
            f"Device Subclass: 0x{self.device.bDeviceSubClass:02x}",
            f"Device Protocol: 0x{self.device.bDeviceProtocol:02x}",
            f"Max Packet Size: {self.device.bMaxPacketSize0}",
            f"Number of Configurations: {self.device.bNumConfigurations}",
        ]

        # Add configuration details
        for config in self.device:
            lines.append(f"\nConfiguration {config.bConfigurationValue}:")
            lines.append(f"  Total Length: {config.wTotalLength}")
            lines.append(f"  Number of Interfaces: {config.bNumInterfaces}")

            for interface in config:
                lines.append(
                    f"\n  Interface {interface.bInterfaceNumber}, "
                    f"Alt Setting {interface.bAlternateSetting}:"
                )
                lines.append(f"    Class: 0x{interface.bInterfaceClass:02x}")
                lines.append(f"    Subclass: 0x{interface.bInterfaceSubClass:02x}")
                lines.append(f"    Protocol: 0x{interface.bInterfaceProtocol:02x}")
                lines.append(f"    Number of Endpoints: {interface.bNumEndpoints}")

                for endpoint in interface:
                    direction = "IN" if endpoint.bEndpointAddress & 0x80 else "OUT"
                    transfer_type = {
                        0: "Control",
                        1: "Isochronous",
                        2: "Bulk",
                        3: "Interrupt",
                    }.get(endpoint.bmAttributes & 0x03, "Unknown")
                    lines.append(
                        f"\n    Endpoint 0x{endpoint.bEndpointAddress:02x} "
                        f"({direction}, {transfer_type}):"
                    )
                    lines.append(f"      Max Packet Size: {endpoint.wMaxPacketSize}")
                    lines.append(f"      Interval: {endpoint.bInterval}")

        return "\n".join(lines)


class USBDeviceManager:
    """Manager class for USB device enumeration and lookup.

    Provides methods to list devices, find devices by various criteria,
    and resolve bindings to current devices.
    """

    def __init__(self) -> None:
        """Initialize the USBDeviceManager."""
        self._logger = logging.getLogger(__name__)

    def list_devices(self) -> list[USBDevice]:
        """List all available USB devices.

        Returns:
            List of USBDevice objects for all connected devices.
        """
        backend = get_backend(fresh=True)
        devices = usb.core.find(find_all=True, backend=backend)
        return [USBDevice(device) for device in devices]

    def find_by_bus_id(self, bus_id: str) -> Optional[USBDevice]:
        """Find a device by its bus ID.

        Args:
            bus_id: The bus ID string (e.g., "20-4.2.1" or "0-1").

        Returns:
            The USBDevice if found, None otherwise.
        """
        try:
            target_bus, target_ports = USBDevice.parse_bus_id(bus_id)
        except ValueError as error:
            self._logger.error("Invalid bus ID: %s", error)
            return None

        backend = get_backend(fresh=True)
        devices = usb.core.find(find_all=True, backend=backend)

        for device in devices:
            if device.bus == target_bus:
                port_numbers = device.port_numbers
                if port_numbers:
                    # Device has port numbers - match against port path
                    if tuple(port_numbers) == target_ports:
                        return USBDevice(device)
                else:
                    # Device has no port numbers - match against address
                    # This handles the fallback case in build_bus_id
                    if len(target_ports) == 1 and device.address == target_ports[0]:
                        return USBDevice(device)

        return None

    def find_by_identity(
        self,
        vendor_id: int,
        product_id: int,
        serial_number: Optional[str] = None,
    ) -> Optional[USBDevice]:
        """Find a device by VID, PID, and optionally serial number.

        Args:
            vendor_id: The vendor ID to match.
            product_id: The product ID to match.
            serial_number: The serial number to match (optional).

        Returns:
            The USBDevice if found, None otherwise.
        """
        backend = get_backend(fresh=True)
        devices = usb.core.find(
            find_all=True,
            idVendor=vendor_id,
            idProduct=product_id,
            backend=backend,
        )

        for device in devices:
            usb_device = USBDevice(device)

            # Normalize both to empty string for comparison
            # (binding stores "" for no serial, USBDevice returns None)
            search_serial = serial_number or ""
            device_serial = usb_device.serial_number or ""

            if search_serial == device_serial:
                return usb_device

        return None

    def find_by_binding(self, binding: dict[str, str]) -> Optional[USBDevice]:
        """Find a device that matches a binding configuration.

        The binding dictionary should contain 'vendor_id', 'product_id',
        and optionally 'serial_number'.

        Args:
            binding: Dictionary with device identity information.

        Returns:
            The USBDevice if found, None otherwise.
        """
        try:
            vendor_id = int(binding["vendor_id"], 16)
            product_id = int(binding["product_id"], 16)
            serial_number = binding.get("serial_number")
        except (KeyError, ValueError) as error:
            self._logger.error("Invalid binding format: %s", error)
            return None

        return self.find_by_identity(vendor_id, product_id, serial_number)
