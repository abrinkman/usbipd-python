# SPDX-FileCopyrightText: 2025 Alexander Brinkman
# SPDX-License-Identifier: GPL-3.0-or-later
"""USB/IP server implementation for sharing USB devices over the network."""

import logging
import socket
import struct
import threading
from typing import TYPE_CHECKING, Optional

import usb.core
import usb.util

if TYPE_CHECKING:
    from usb_device import USBDevice

# USB/IP Protocol Constants
USBIP_VERSION = 0x0111

# Operation codes
OP_REQ_DEVLIST = 0x8005
OP_REP_DEVLIST = 0x0005
OP_REQ_IMPORT = 0x8003
OP_REP_IMPORT = 0x0003

# URB commands
USBIP_CMD_SUBMIT = 0x00000001
USBIP_CMD_UNLINK = 0x00000002
USBIP_RET_SUBMIT = 0x00000003
USBIP_RET_UNLINK = 0x00000004

# USB directions
USBIP_DIR_OUT = 0
USBIP_DIR_IN = 1

# Status codes
STATUS_OK = 0
STATUS_ERROR = 1

# USB speeds
USB_SPEED_UNKNOWN = 0
USB_SPEED_LOW = 1
USB_SPEED_FULL = 2
USB_SPEED_HIGH = 3
USB_SPEED_SUPER = 5

# Default server port
DEFAULT_PORT = 3240

logger = logging.getLogger(__name__)


class USBIPServer:
    """A USB/IP server that exports USB devices over the network."""

    def __init__(self, host: str = "::", port: int = DEFAULT_PORT) -> None:
        """Initialize the USB/IP server.

        Args:
            host: The host address to bind to. Defaults to '::' which accepts
                  both IPv4 and IPv6 connections (dual-stack).
            port: The port to listen on (default: 3240).
        """
        self.host = host
        self.port = port
        self._server_socket: Optional[socket.socket] = None
        self._running = False
        self._exported_devices: dict[str, USBDevice] = {}
        self._active_connections: list[threading.Thread] = []
        self._lock = threading.Lock()

    def export_device(self, usb_device: "USBDevice") -> None:
        """Export a USB device for remote access.

        Args:
            usb_device: The USBDevice object to export.
        """
        with self._lock:
            self._exported_devices[usb_device.bus_id] = usb_device
            logger.info(f"Exported device: {usb_device.bus_id}")

    def unexport_device(self, bus_id: str) -> bool:
        """
        Remove a device from the export list.

        Args:
            bus_id: The bus ID of the device to unexport.

        Returns:
            True if the device was unexported, False if not found.
        """
        with self._lock:
            if bus_id in self._exported_devices:
                del self._exported_devices[bus_id]
                logger.info(f"Unexported device: {bus_id}")
                return True
            return False

    def get_exported_devices(self) -> dict[str, "USBDevice"]:
        """Get the list of exported devices.

        Returns:
            A dictionary mapping bus IDs to USBDevice objects.
        """
        with self._lock:
            return self._exported_devices.copy()

    def start(self) -> None:
        """Start the USB/IP server."""
        if self._running:
            logger.warning("Server is already running")
            return

        # Determine socket family based on host address
        if ":" in self.host:
            # IPv6 address (includes '::' for dual-stack)
            self._server_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            # Enable dual-stack: accept both IPv4 and IPv6 connections
            # IPV6_V6ONLY=0 means IPv4 clients can connect via IPv4-mapped IPv6 addresses
            self._server_socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        else:
            # IPv4 address
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(5)
        self._running = True

        logger.info(f"USB/IP server started on [{self.host}]:{self.port}")

        while self._running:
            try:
                self._server_socket.settimeout(1.0)
                try:
                    client_socket, client_address = self._server_socket.accept()
                    logger.info(f"Connection from {client_address}")
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, client_address),
                        daemon=True,
                    )
                    client_thread.start()
                    self._active_connections.append(client_thread)
                except socket.timeout:
                    continue
            except OSError:
                break

    def stop(self) -> None:
        """Stop the USB/IP server."""
        self._running = False
        if self._server_socket:
            self._server_socket.close()
            self._server_socket = None
        logger.info("USB/IP server stopped")

    def _handle_client(self, client_socket: socket.socket, client_address: tuple) -> None:
        """
        Handle a client connection.

        Args:
            client_socket: The client socket.
            client_address: The client address tuple.
        """
        try:
            while self._running:
                # Read the operation header (8 bytes minimum)
                header = self._recv_exact(client_socket, 8)
                if not header:
                    break

                version, opcode, status = struct.unpack(">HHI", header)

                if version != USBIP_VERSION:
                    logger.warning(f"Unsupported USB/IP version: 0x{version:04x}")
                    break

                if opcode == OP_REQ_DEVLIST:
                    self._handle_devlist_request(client_socket)
                    # Close connection after devlist as per protocol
                    break
                elif opcode == OP_REQ_IMPORT:
                    # Read the bus ID (32 bytes)
                    bus_id_data = self._recv_exact(client_socket, 32)
                    if not bus_id_data:
                        break
                    bus_id = bus_id_data.rstrip(b"\x00").decode("utf-8")
                    if self._handle_import_request(client_socket, bus_id):
                        # Keep connection open for URB traffic
                        self._handle_urb_traffic(client_socket, bus_id)
                    break
                else:
                    logger.warning(f"Unknown opcode: 0x{opcode:04x}")
                    break
        except (ConnectionResetError, BrokenPipeError) as error:
            logger.debug(f"Client disconnected: {error}")
        except Exception as error:
            logger.error(f"Error handling client {client_address}: {error}")
        finally:
            client_socket.close()
            logger.info(f"Connection closed: {client_address}")

    def _recv_exact(self, sock: socket.socket, length: int) -> Optional[bytes]:
        """
        Receive exactly the specified number of bytes.

        Args:
            sock: The socket to receive from.
            length: The number of bytes to receive.

        Returns:
            The received bytes, or None if connection closed.
        """
        data = b""
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def _handle_devlist_request(self, client_socket: socket.socket) -> None:
        """
        Handle OP_REQ_DEVLIST request.

        Args:
            client_socket: The client socket.
        """
        with self._lock:
            devices = list(self._exported_devices.items())

        # Build the response header
        response = struct.pack(
            ">HHI I",
            USBIP_VERSION,
            OP_REP_DEVLIST,
            STATUS_OK,
            len(devices),
        )

        # Add device information for each exported device
        for bus_id, usb_device in devices:
            response += self._build_device_info(bus_id, usb_device.device)

        client_socket.sendall(response)
        logger.debug(f"Sent device list with {len(devices)} devices")

    def _build_device_info(self, bus_id: str, device: usb.core.Device) -> bytes:
        """
        Build the device information structure for OP_REP_DEVLIST.

        Args:
            bus_id: The bus ID of the device.
            device: The pyusb device object.

        Returns:
            The packed device information bytes.
        """
        # Path (256 bytes, zero-padded)
        path = f"/sys/devices/usb/{bus_id}".encode()
        path = path[:255] + b"\x00" * (256 - len(path))

        # Bus ID (32 bytes, zero-padded)
        bus_id_bytes = bus_id.encode("utf-8")
        bus_id_bytes = bus_id_bytes[:31] + b"\x00" * (32 - len(bus_id_bytes))

        # Parse bus and device numbers from bus_id
        try:
            bus_num, port_num = bus_id.split("-")
            busnum = int(bus_num)
            devnum = int(port_num)
        except ValueError:
            busnum = device.bus or 0
            devnum = device.address or 0

        # Determine USB speed
        speed = self._get_device_speed(device)

        # Get configuration info
        try:
            config = device.get_active_configuration()
            config_value = config.bConfigurationValue
            num_interfaces = config.bNumInterfaces
        except usb.core.USBError:
            config_value = 1
            num_interfaces = 1

        # Build device descriptor portion
        device_info = struct.pack(
            ">II I HH H BBB BB",
            busnum,
            devnum,
            speed,
            device.idVendor,
            device.idProduct,
            device.bcdDevice,
            device.bDeviceClass,
            device.bDeviceSubClass,
            device.bDeviceProtocol,
            config_value,
            device.bNumConfigurations,
        )

        # Add number of interfaces
        device_info += struct.pack(">B", num_interfaces)

        # Add interface descriptors
        interface_info = b""
        try:
            config = device.get_active_configuration()
            for interface in config:
                interface_info += struct.pack(
                    ">BBBB",
                    interface.bInterfaceClass,
                    interface.bInterfaceSubClass,
                    interface.bInterfaceProtocol,
                    0,  # padding
                )
        except usb.core.USBError:
            # Add dummy interface info
            interface_info = struct.pack(">BBBB", 0, 0, 0, 0)

        return path + bus_id_bytes + device_info + interface_info

    def _get_device_speed(self, device: usb.core.Device) -> int:
        """
        Determine the USB speed of a device.

        Args:
            device: The pyusb device object.

        Returns:
            The USB speed constant.
        """
        try:
            speed = device.speed
            if speed is None:
                return USB_SPEED_UNKNOWN
            # pyusb speed values may differ from USB/IP constants
            speed_map = {
                1: USB_SPEED_LOW,
                2: USB_SPEED_FULL,
                3: USB_SPEED_HIGH,
                4: USB_SPEED_SUPER,
            }
            return speed_map.get(speed, USB_SPEED_UNKNOWN)
        except (AttributeError, usb.core.USBError):
            return USB_SPEED_UNKNOWN

    def _handle_import_request(self, client_socket: socket.socket, bus_id: str) -> bool:
        """Handle OP_REQ_IMPORT request.

        Args:
            client_socket: The client socket.
            bus_id: The requested bus ID.

        Returns:
            True if import was successful, False otherwise.
        """
        with self._lock:
            usb_device = self._exported_devices.get(bus_id)

        if usb_device is None:
            # Send error response
            response = struct.pack(
                ">HHI",
                USBIP_VERSION,
                OP_REP_IMPORT,
                STATUS_ERROR,
            )
            client_socket.sendall(response)
            logger.warning(f"Import request for unknown device: {bus_id}")
            return False

        # Build success response with device info
        response = struct.pack(
            ">HHI",
            USBIP_VERSION,
            OP_REP_IMPORT,
            STATUS_OK,
        )

        # Add device information (similar to devlist but without interfaces)
        response += self._build_import_device_info(bus_id, usb_device.device)

        client_socket.sendall(response)
        logger.info(f"Device imported: {bus_id}")
        return True

    def _build_import_device_info(self, bus_id: str, device: usb.core.Device) -> bytes:
        """
        Build the device information structure for OP_REP_IMPORT.

        Args:
            bus_id: The bus ID of the device.
            device: The pyusb device object.

        Returns:
            The packed device information bytes.
        """
        # Path (256 bytes, zero-padded)
        path = f"/sys/devices/usb/{bus_id}".encode()
        path = path[:255] + b"\x00" * (256 - len(path))

        # Bus ID (32 bytes, zero-padded)
        bus_id_bytes = bus_id.encode("utf-8")
        bus_id_bytes = bus_id_bytes[:31] + b"\x00" * (32 - len(bus_id_bytes))

        # Parse bus and device numbers
        try:
            bus_num, port_num = bus_id.split("-")
            busnum = int(bus_num)
            devnum = int(port_num)
        except ValueError:
            busnum = device.bus or 0
            devnum = device.address or 0

        speed = self._get_device_speed(device)

        try:
            config = device.get_active_configuration()
            config_value = config.bConfigurationValue
            num_interfaces = config.bNumInterfaces
        except usb.core.USBError:
            config_value = 1
            num_interfaces = 1

        device_info = struct.pack(
            ">II I HH H BBB BB",
            busnum,
            devnum,
            speed,
            device.idVendor,
            device.idProduct,
            device.bcdDevice,
            device.bDeviceClass,
            device.bDeviceSubClass,
            device.bDeviceProtocol,
            config_value,
            device.bNumConfigurations,
        )

        device_info += struct.pack(">B", num_interfaces)

        return path + bus_id_bytes + device_info

    def _handle_urb_traffic(self, client_socket: socket.socket, bus_id: str) -> None:
        """Handle URB traffic for an imported device.

        Args:
            client_socket: The client socket.
            bus_id: The bus ID of the imported device.
        """
        with self._lock:
            usb_device = self._exported_devices.get(bus_id)

        if usb_device is None:
            return

        # Claim the device for exclusive access
        if not usb_device.claim():
            logger.error(f"Cannot handle URB traffic for {bus_id} - device claim failed")
            return

        logger.info(f"Starting URB traffic handling for {bus_id}")

        try:
            while self._running:
                try:
                    # Read USBIP header (48 bytes)
                    header = self._recv_exact(client_socket, 48)
                    if not header:
                        break

                    command, seqnum, devid, direction, endpoint = struct.unpack(
                        ">IIIII", header[:20]
                    )

                    if command == USBIP_CMD_SUBMIT:
                        self._handle_urb_submit(
                            client_socket,
                            usb_device.device,
                            header,
                            seqnum,
                            direction,
                            endpoint,
                        )
                    elif command == USBIP_CMD_UNLINK:
                        self._handle_urb_unlink(client_socket, header, seqnum)
                    else:
                        logger.warning(f"Unknown URB command: 0x{command:08x}")
                        break

                except socket.timeout:
                    continue
                except (ConnectionResetError, BrokenPipeError):
                    break
                except Exception as error:
                    logger.error(f"Error handling URB: {error}")
                    break
        finally:
            # Release the device
            usb_device.release()
            logger.info(f"URB traffic handling ended for {bus_id}")

    def _handle_urb_submit(
        self,
        client_socket: socket.socket,
        device: usb.core.Device,
        header: bytes,
        seqnum: int,
        direction: int,
        endpoint: int,
    ) -> None:
        """Handle USBIP_CMD_SUBMIT command.

        Args:
            client_socket: The client socket.
            device: The USB device.
            header: The full header bytes.
            seqnum: The sequence number.
            direction: The transfer direction.
            endpoint: The endpoint number.
        """
        # Parse the rest of the submit header
        (
            transfer_flags,
            transfer_buffer_length,
            start_frame,
            number_of_packets,
            interval,
        ) = struct.unpack(">IIIII", header[20:40])

        setup = header[40:48]

        # For control transfers, check the setup packet to determine if we need to read data
        # For bulk/interrupt OUT transfers, read the data buffer
        transfer_buffer = b""
        if transfer_buffer_length > 0:
            if endpoint == 0:
                # Control transfer - check bmRequestType for direction
                bmRequestType = setup[0]
                is_device_to_host = (bmRequestType & 0x80) != 0
                if not is_device_to_host:
                    # Host to Device (OUT) - read the data
                    recv_result = self._recv_exact(client_socket, transfer_buffer_length)
                    if recv_result is None:
                        return
                    transfer_buffer = recv_result
            elif direction == USBIP_DIR_OUT:
                # Bulk/Interrupt OUT - read the data
                recv_result = self._recv_exact(client_socket, transfer_buffer_length)
                if recv_result is None:
                    return
                transfer_buffer = recv_result

        # Execute the USB transfer
        actual_length = 0
        status = 0
        response_data = b""

        try:
            if endpoint == 0:
                # Control transfer
                response_data, actual_length = self._do_control_transfer(
                    device, setup, transfer_buffer, transfer_buffer_length, direction
                )
            else:
                # Bulk/Interrupt transfer
                response_data, actual_length = self._do_bulk_interrupt_transfer(
                    device, endpoint, transfer_buffer, transfer_buffer_length, direction
                )
        except usb.core.USBTimeoutError:
            # Timeout - return ETIMEDOUT (-110 on Linux)
            logger.debug(f"USB timeout on endpoint {endpoint}")
            status = -110
        except usb.core.USBError as error:
            logger.debug(f"USB error on endpoint {endpoint}: {error}")
            # Map common USB errors to Linux errno values
            if error.errno is not None:
                status = -error.errno
            else:
                # Generic I/O error
                status = -5  # EIO

        # Build response
        response = struct.pack(
            ">IIIII",
            USBIP_RET_SUBMIT,
            seqnum,
            0,  # devid
            0,  # direction
            0,  # endpoint
        )

        response += struct.pack(
            ">iI I I i",
            status,
            actual_length,
            start_frame,
            number_of_packets,
            0,  # error_count
        )

        # Padding (8 bytes)
        response += b"\x00" * 8

        # Add response data for IN transfers (including control IN transfers)
        if actual_length > 0 and len(response_data) > 0:
            response += response_data[:actual_length]

        client_socket.sendall(response)
        logger.debug(
            f"Sent URB response: seqnum={seqnum}, status={status}, actual_length={actual_length}"
        )

    def _do_control_transfer(
        self,
        device: usb.core.Device,
        setup: bytes,
        data: bytes,
        length: int,
        direction: int,
    ) -> tuple[bytes, int]:
        """
        Execute a control transfer.

        Args:
            device: The USB device.
            setup: The setup packet (8 bytes).
            data: The data buffer for OUT transfers.
            length: The expected transfer length.
            direction: The transfer direction from header.

        Returns:
            A tuple of (response_data, actual_length).
        """
        bmRequestType, bRequest, wValue, wIndex, wLength = struct.unpack("<BBHHH", setup)

        # Direction is encoded in bmRequestType bit 7:
        # 0 = Host to Device (OUT), 1 = Device to Host (IN)
        is_device_to_host = (bmRequestType & 0x80) != 0

        logger.debug(
            f"Control transfer: bmRequestType=0x{bmRequestType:02x}, "
            f"bRequest=0x{bRequest:02x}, wValue=0x{wValue:04x}, "
            f"wIndex=0x{wIndex:04x}, wLength={wLength}, "
            f"direction={'IN' if is_device_to_host else 'OUT'}"
        )

        try:
            if is_device_to_host:
                # Device to Host (IN) - read data from device
                result = device.ctrl_transfer(
                    bmRequestType, bRequest, wValue, wIndex, wLength, timeout=5000
                )
                return bytes(result), len(result)
            else:
                # Host to Device (OUT) - write data to device
                if wLength > 0 and data:
                    result = device.ctrl_transfer(
                        bmRequestType,
                        bRequest,
                        wValue,
                        wIndex,
                        data[:wLength],
                        timeout=5000,
                    )
                else:
                    result = device.ctrl_transfer(
                        bmRequestType, bRequest, wValue, wIndex, None, timeout=5000
                    )
                return b"", result if result is not None else 0
        except usb.core.USBError as error:
            logger.debug(f"Control transfer error: {error}")
            raise

    def _do_bulk_interrupt_transfer(
        self,
        device: usb.core.Device,
        endpoint: int,
        data: bytes,
        length: int,
        direction: int,
    ) -> tuple[bytes, int]:
        """
        Execute a bulk or interrupt transfer.

        Args:
            device: The USB device.
            endpoint: The endpoint number (without direction bit).
            data: The data buffer for OUT transfers.
            length: The expected transfer length.
            direction: The transfer direction (USBIP_DIR_IN or USBIP_DIR_OUT).

        Returns:
            A tuple of (response_data, actual_length).
        """
        # Construct the full endpoint address with direction bit
        if direction == USBIP_DIR_IN:
            endpoint_addr = (endpoint & 0x0F) | 0x80  # Set IN bit (bit 7)
            logger.debug(
                f"Bulk/Interrupt IN transfer: endpoint=0x{endpoint_addr:02x}, length={length}"
            )
            try:
                # Use a shorter timeout for interrupt endpoints to avoid blocking
                result = device.read(endpoint_addr, length, timeout=1000)
                return bytes(result), len(result)
            except usb.core.USBTimeoutError:
                # Timeout is normal for interrupt endpoints with no data
                logger.debug(f"Read timeout on endpoint 0x{endpoint_addr:02x}")
                raise
        else:
            endpoint_addr = endpoint & 0x0F  # Clear direction bit for OUT
            logger.debug(
                f"Bulk/Interrupt OUT transfer: endpoint=0x{endpoint_addr:02x}, length={len(data)}"
            )
            result = device.write(endpoint_addr, data, timeout=5000)
            return b"", result

    def _handle_urb_unlink(self, client_socket: socket.socket, header: bytes, seqnum: int) -> None:
        """
        Handle USBIP_CMD_UNLINK command.

        Args:
            client_socket: The client socket.
            header: The full header bytes.
            seqnum: The sequence number.
        """
        unlink_seqnum = struct.unpack(">I", header[20:24])[0]

        # Build response (we don't actually track pending URBs in this simple implementation)
        response = struct.pack(
            ">IIIII",
            USBIP_RET_UNLINK,
            seqnum,
            0,  # devid
            0,  # direction
            0,  # endpoint
        )

        # Status: -ECONNRESET (-104) for successful unlink
        response += struct.pack(">i", -104)

        # Padding (24 bytes)
        response += b"\x00" * 24

        client_socket.sendall(response)
        logger.debug(f"Unlinked URB seqnum={unlink_seqnum}")
