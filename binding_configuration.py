# SPDX-FileCopyrightText: 2025 Alexander Brinkman
# SPDX-License-Identifier: GPL-3.0-or-later
"""Configuration manager for usbipd bound devices."""

import os
import xml.etree.ElementTree as ET
from typing import Optional
from xml.dom import minidom


class BindingConfiguration:
    """Manages the configuration file for bound USB devices."""

    DEFAULT_CONFIG_PATH = os.path.expanduser("~/.config/usbipd/bindings.xml")

    def __init__(self, config_path: Optional[str] = None) -> None:
        """
        Initialize the BindingConfiguration instance.

        Args:
            config_path: Optional path to the configuration file.
                        Defaults to ~/.config/usbipd/bindings.xml
        """
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self._ensure_config_exists()

    def _ensure_config_exists(self) -> None:
        """Ensure the configuration file and its directory exist."""
        config_dir = os.path.dirname(self.config_path)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)

        if not os.path.exists(self.config_path):
            self._create_empty_config()

    def _create_empty_config(self) -> None:
        """Create an empty configuration file with the root element."""
        root = ET.Element("usbipd")
        root.set("version", "1.0")
        ET.SubElement(root, "bindings")
        self._write_config(root)

    def _write_config(self, root: ET.Element) -> None:
        """
        Write the XML configuration to file with pretty formatting.

        Args:
            root: The root XML element to write.
        """
        xml_string = ET.tostring(root, encoding="unicode")
        pretty_xml = minidom.parseString(xml_string).toprettyxml(indent="  ")
        # Remove extra blank lines that minidom adds
        lines = [line for line in pretty_xml.split("\n") if line.strip()]
        formatted_xml = "\n".join(lines) + "\n"

        with open(self.config_path, "w", encoding="utf-8") as config_file:
            config_file.write(formatted_xml)

    def _load_config(self) -> ET.Element:
        """
        Load the configuration file.

        Returns:
            The root XML element.
        """
        tree = ET.parse(self.config_path)
        return tree.getroot()

    def add_binding(self, vendor_id: str, product_id: str, serial_number: str = "") -> bool:
        """
        Add a device binding to the configuration.

        Devices are identified by VID:PID and optionally serial number.

        Args:
            vendor_id: The vendor ID in hex format (e.g., '1234').
            product_id: The product ID in hex format (e.g., '5678').
            serial_number: The device serial number (optional, may be empty).

        Returns:
            True if the binding was added, False if it already exists.
        """
        root = self._load_config()
        bindings = root.find("bindings")

        if bindings is None:
            bindings = ET.SubElement(root, "bindings")

        # Check if binding already exists (same VID:PID:serial)
        for device in bindings.findall("device"):
            if (
                device.get("vendor_id") == vendor_id
                and device.get("product_id") == product_id
                and device.get("serial_number", "") == serial_number
            ):
                return False

        # Add new binding
        device_element = ET.SubElement(bindings, "device")
        device_element.set("vendor_id", vendor_id)
        device_element.set("product_id", product_id)
        if serial_number:
            device_element.set("serial_number", serial_number)

        self._write_config(root)
        return True

    def remove_binding(self, vendor_id: str, product_id: str, serial_number: str = "") -> bool:
        """
        Remove a device binding from the configuration.

        Args:
            vendor_id: The vendor ID in hex format.
            product_id: The product ID in hex format.
            serial_number: The device serial number (optional).

        Returns:
            True if the binding was removed, False if it was not found.
        """
        root = self._load_config()
        bindings = root.find("bindings")

        if bindings is None:
            return False

        for device in bindings.findall("device"):
            if (
                device.get("vendor_id") == vendor_id
                and device.get("product_id") == product_id
                and device.get("serial_number", "") == serial_number
            ):
                bindings.remove(device)
                self._write_config(root)
                return True

        return False

    def get_binding(
        self, vendor_id: str, product_id: str, serial_number: str = ""
    ) -> Optional[dict]:
        """
        Get a specific binding by VID:PID:serial.

        Args:
            vendor_id: The vendor ID in hex format.
            product_id: The product ID in hex format.
            serial_number: The device serial number (optional).

        Returns:
            A dictionary with the binding information, or None if not found.
        """
        root = self._load_config()
        bindings = root.find("bindings")

        if bindings is None:
            return None

        for device in bindings.findall("device"):
            if (
                device.get("vendor_id") == vendor_id
                and device.get("product_id") == product_id
                and device.get("serial_number", "") == serial_number
            ):
                return self._device_element_to_dict(device)

        return None

    def get_all_bindings(self) -> list[dict]:
        """
        Get all device bindings.

        Returns:
            A list of dictionaries containing binding information.
        """
        root = self._load_config()
        bindings = root.find("bindings")

        if bindings is None:
            return []

        return [self._device_element_to_dict(device) for device in bindings.findall("device")]

    def is_bound(self, vendor_id: str, product_id: str, serial_number: str = "") -> bool:
        """
        Check if a device is bound.

        Args:
            vendor_id: The vendor ID in hex format.
            product_id: The product ID in hex format.
            serial_number: The device serial number (optional).

        Returns:
            True if the device is bound, False otherwise.
        """
        return self.get_binding(vendor_id, product_id, serial_number) is not None

    def clear_all_bindings(self) -> int:
        """
        Remove all device bindings from the configuration.

        Returns:
            The number of bindings that were removed.
        """
        root = self._load_config()
        bindings = root.find("bindings")

        if bindings is None:
            return 0

        device_count = len(bindings.findall("device"))
        bindings.clear()
        self._write_config(root)
        return device_count

    def _device_element_to_dict(self, device: ET.Element) -> dict:
        """
        Convert a device XML element to a dictionary.

        Args:
            device: The device XML element.

        Returns:
            A dictionary containing the device information.
        """
        return {
            "vendor_id": device.get("vendor_id", ""),
            "product_id": device.get("product_id", ""),
            "serial_number": device.get("serial_number", ""),
        }
