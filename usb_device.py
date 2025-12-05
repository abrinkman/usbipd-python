# SPDX-FileCopyrightText: 2024 abrinkman
# SPDX-License-Identifier: GPL-3.0-or-later
"""USB device wrapper module for usbipd."""

import usb.core
import usb.util


class USBDevice:
    """Represents a USB device identified by its bus ID."""

    def __init__(self, bus_id: str) -> None:
        """
        Initialize a USBDevice instance.

        Args:
            bus_id: The bus ID in format 'bus-port' (e.g., '1-3').

        Raises:
            ValueError: If the bus ID format is invalid.
            DeviceNotFoundError: If no device is found at the specified bus ID.
        """
        self.bus_id = bus_id
        self._device = self._find_device_by_bus_id(bus_id)

    def _find_device_by_bus_id(self, bus_id: str) -> usb.core.Device:
        """
        Find a USB device by its bus ID.

        Args:
            bus_id: The bus ID in format 'bus-port' (e.g., '1-3').

        Returns:
            The USB device if found.

        Raises:
            ValueError: If the bus ID format is invalid.
            LookupError: If no device is found at the specified bus ID.
        """
        try:
            bus, port = bus_id.split("-")
            target_bus = int(bus)
            target_port = int(port)
        except ValueError as error:
            raise ValueError(f"Invalid bus ID format '{bus_id}'. Expected format: bus-port (e.g., 1-3)") from error

        devices = usb.core.find(find_all=True)
        for device in devices:
            device_port = device.port_number if device.port_number else 0
            if device.bus == target_bus and device_port == target_port:
                return device

        raise LookupError(f"No device found with bus ID '{bus_id}'")

    @property
    def device(self) -> usb.core.Device:
        """
        Get the underlying pyusb device object.

        Returns:
            The usb.core.Device instance.
        """
        return self._device

    def get_basic_info(self) -> dict:
        """
        Get basic information about the USB device.

        Returns:
            A dictionary containing vendor_id, product_id, manufacturer, product, and serial_number.
        """
        device = self._device
        result = {
            "bus_id": self.bus_id,
            "vendor_id": f"{device.idVendor:04x}",
            "product_id": f"{device.idProduct:04x}",
            "manufacturer": "",
            "product": "",
            "serial_number": "",
        }

        try:
            if device.iManufacturer:
                result["manufacturer"] = usb.util.get_string(device, device.iManufacturer)
        except (usb.core.USBError, ValueError):
            pass

        try:
            if device.iProduct:
                result["product"] = usb.util.get_string(device, device.iProduct)
        except (usb.core.USBError, ValueError):
            pass

        try:
            if device.iSerialNumber:
                result["serial_number"] = usb.util.get_string(device, device.iSerialNumber)
        except (usb.core.USBError, ValueError):
            pass

        return result

    def get_device_information(self) -> str:
        """
        Get comprehensive information about the USB device.

        Returns:
            A formatted string containing all device information.
        """
        lines = []
        device = self._device

        lines.append(f"Device found at bus ID: {self.bus_id}")
        lines.append("=" * 60)

        # Basic device information
        lines.append(f"Vendor ID:      0x{device.idVendor:04x}")
        lines.append(f"Product ID:     0x{device.idProduct:04x}")
        lines.append(f"USB Version:    {device.bcdUSB >> 8}.{(device.bcdUSB >> 4) & 0xf}{device.bcdUSB & 0xf}")
        lines.append(f"Device Class:   {device.bDeviceClass}")
        lines.append(f"Device Subclass:{device.bDeviceSubClass}")
        lines.append(f"Device Protocol:{device.bDeviceProtocol}")
        lines.append(f"Max Packet Size:{device.bMaxPacketSize0}")
        lines.append(f"Num Configs:    {device.bNumConfigurations}")

        # Try to get string descriptors
        try:
            if device.iManufacturer:
                manufacturer = usb.util.get_string(device, device.iManufacturer)
                lines.append(f"Manufacturer:   {manufacturer}")
        except (usb.core.USBError, ValueError) as error:
            lines.append(f"Manufacturer:   (unable to read: {error})")

        try:
            if device.iProduct:
                product = usb.util.get_string(device, device.iProduct)
                lines.append(f"Product:        {product}")
        except (usb.core.USBError, ValueError) as error:
            lines.append(f"Product:        (unable to read: {error})")

        try:
            if device.iSerialNumber:
                serial = usb.util.get_string(device, device.iSerialNumber)
                lines.append(f"Serial Number:  {serial}")
        except (usb.core.USBError, ValueError) as error:
            lines.append(f"Serial Number:  (unable to read: {error})")

        # Configuration information
        lines.append("\n" + "-" * 60)
        lines.append("Configurations:")

        for config in device:
            lines.append(f"\n  Configuration {config.bConfigurationValue}:")
            lines.append(f"    Total Length:     {config.wTotalLength}")
            lines.append(f"    Num Interfaces:   {config.bNumInterfaces}")
            lines.append(f"    Config Value:     {config.bConfigurationValue}")
            lines.append(f"    Max Power:        {config.bMaxPower * 2} mA")

            try:
                if config.iConfiguration:
                    config_string = usb.util.get_string(device, config.iConfiguration)
                    lines.append(f"    Description:      {config_string}")
            except (usb.core.USBError, ValueError):
                pass

            # Interface information
            for interface in config:
                lines.append(f"\n    Interface {interface.bInterfaceNumber}, Alt Setting {interface.bAlternateSetting}:")
                lines.append(f"      Interface Class:    {interface.bInterfaceClass}")
                lines.append(f"      Interface Subclass: {interface.bInterfaceSubClass}")
                lines.append(f"      Interface Protocol: {interface.bInterfaceProtocol}")
                lines.append(f"      Num Endpoints:      {interface.bNumEndpoints}")

                try:
                    if interface.iInterface:
                        interface_string = usb.util.get_string(device, interface.iInterface)
                        lines.append(f"      Description:        {interface_string}")
                except (usb.core.USBError, ValueError):
                    pass

                # Endpoint information
                for endpoint in interface:
                    endpoint_direction = "IN" if usb.util.endpoint_direction(endpoint.bEndpointAddress) == usb.util.ENDPOINT_IN else "OUT"
                    endpoint_type_map = {
                        usb.util.ENDPOINT_TYPE_CTRL: "Control",
                        usb.util.ENDPOINT_TYPE_ISO: "Isochronous",
                        usb.util.ENDPOINT_TYPE_BULK: "Bulk",
                        usb.util.ENDPOINT_TYPE_INTR: "Interrupt",
                    }
                    endpoint_type = endpoint_type_map.get(usb.util.endpoint_type(endpoint.bmAttributes), "Unknown")

                    lines.append(f"\n        Endpoint 0x{endpoint.bEndpointAddress:02x}:")
                    lines.append(f"          Direction:      {endpoint_direction}")
                    lines.append(f"          Type:           {endpoint_type}")
                    lines.append(f"          Max Packet:     {endpoint.wMaxPacketSize}")
                    lines.append(f"          Interval:       {endpoint.bInterval}")

        lines.append("\n" + "=" * 60)
        lines.append(f"Device at bus ID '{self.bus_id}' successfully queried.")

        return "\n".join(lines)
