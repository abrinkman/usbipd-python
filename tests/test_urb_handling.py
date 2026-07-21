# SPDX-FileCopyrightText: 2026 usbipd-python contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression tests for concurrent URB handling in ``usbip_server``.

These exercise the URB traffic loop with a mocked USB device and a scripted
in-memory socket (no libusb / no hardware, per CONTRIBUTING):

* a pending IN read must not head-of-line block OUT / other endpoints;
* an unlinked pending IN read must not emit a spurious ``RET_SUBMIT``;
* every URB is completed exactly once, so an ``UNLINK`` racing with the
  transfer never produces a ``RET_UNLINK`` before ``RET_SUBMIT`` for the same
  seqnum (which makes the Linux ``vhci_hcd`` abort the whole connection).
"""

import struct
import threading
import time

import usb.core

import usbip_server as srv

CMD_SUBMIT = 1
CMD_UNLINK = 2
RET_SUBMIT = 3
RET_UNLINK = 4
DIR_OUT = 0
DIR_IN = 1


class FakeDevice:
    """Minimal stand-in for a ``usb.core.Device``.

    Bulk OUT writes are echoed back on the matching IN endpoint so a simple
    loopback can be asserted. IN reads with no buffered data raise
    ``USBTimeoutError`` like libusb would.
    """

    def __init__(self, write_delay: float = 0.0) -> None:
        self._echo: dict[int, bytearray] = {}
        self._lock = threading.Lock()
        self._write_delay = write_delay

    def write(self, endpoint: int, data: bytes, timeout: int = 0) -> int:
        if self._write_delay:
            time.sleep(self._write_delay)
        in_addr = (endpoint & 0x0F) | 0x80
        with self._lock:
            self._echo.setdefault(in_addr, bytearray()).extend(bytes(data))
        return len(data)

    def read(self, endpoint: int, length: int, timeout: int = 0) -> bytes:
        with self._lock:
            buf = self._echo.get(endpoint)
            if buf:
                out = bytes(buf[:length])
                del buf[:length]
                return out
        time.sleep(min(timeout, 20) / 1000.0)
        raise usb.core.USBTimeoutError("timeout")

    def ctrl_transfer(self, *args: object, **kwargs: object) -> bytes:
        return b""


class FakeExportedDevice:
    """Stand-in for the exported-device wrapper used by the server."""

    def __init__(self, device: FakeDevice) -> None:
        self.device = device

    def claim(self) -> bool:
        return True

    def release(self) -> None:
        pass


class FakeSocket:
    """Feeds a scripted client byte stream and captures server responses."""

    def __init__(self, stream: bytes) -> None:
        self._stream = stream
        self._pos = 0
        self.sent: list[bytes] = []
        self._lock = threading.Lock()

    def recv(self, length: int) -> bytes:
        if self._pos >= len(self._stream):
            # Give worker threads a moment to finish, then signal EOF.
            time.sleep(0.4)
            return b""
        chunk = self._stream[self._pos : self._pos + length]
        self._pos += len(chunk)
        return chunk

    def sendall(self, data: bytes) -> None:
        with self._lock:
            self.sent.append(bytes(data))

    def close(self) -> None:
        pass


def _submit(
    seqnum: int,
    direction: int,
    endpoint: int,
    buflen: int = 0,
    payload: bytes = b"",
    setup: bytes = b"\x00" * 8,
) -> bytes:
    header = struct.pack(">IIIII", CMD_SUBMIT, seqnum, 0, direction, endpoint)
    header += struct.pack(">IIIII", 0, buflen, 0, 0, 0)
    header += setup
    return header + (payload if direction == DIR_OUT else b"")


def _unlink(seqnum: int, target: int) -> bytes:
    header = struct.pack(">IIIII", CMD_UNLINK, seqnum, 0, 0, 0)
    header += struct.pack(">I", target) + b"\x00" * 24
    return header[:48]


def _run(stream: bytes, device: FakeDevice) -> list[tuple[str, int, int, bytes]]:
    server = srv.USBIPServer()
    server._running = True
    server._exported_devices = {"1-1": FakeExportedDevice(device)}  # type: ignore[dict-item]
    sock = FakeSocket(stream)
    thread = threading.Thread(target=server._handle_urb_traffic, args=(sock, "1-1"), daemon=True)
    thread.start()
    thread.join(timeout=10)
    assert not thread.is_alive(), "URB traffic handler did not terminate"

    parsed: list[tuple[str, int, int, bytes]] = []
    for msg in sock.sent:
        command, seqnum = struct.unpack(">II", msg[:8])
        if command == RET_SUBMIT:
            status, actual = struct.unpack(">iI", msg[20:28])
            parsed.append(("submit", seqnum, status, msg[48 : 48 + actual]))
        elif command == RET_UNLINK:
            parsed.append(("unlink", seqnum, 0, b""))
    return parsed


def test_pending_in_does_not_block_out_or_echo() -> None:
    """A pending interrupt IN read must not stall bulk OUT / bulk IN."""
    device = FakeDevice()
    stream = b"".join(
        [
            _submit(101, DIR_IN, 1, buflen=8),  # interrupt IN -> stays pending
            _submit(102, DIR_OUT, 2, buflen=5, payload=b"HELLO"),  # bulk OUT
            _submit(103, DIR_IN, 2, buflen=64),  # bulk IN -> echoes HELLO
            _unlink(104, 101),  # release the pending interrupt IN
        ]
    )
    resp = _run(stream, device)
    submits = {seqnum: (status, data) for kind, seqnum, status, data in resp if kind == "submit"}
    unlinks = {seqnum for kind, seqnum, _, _ in resp if kind == "unlink"}

    assert submits.get(102, (None, b""))[0] == 0  # OUT completed (not HOL blocked)
    assert submits.get(103, (None, b""))[1] == b"HELLO"  # IN echoed loopback data
    assert 104 in unlinks  # unlink acknowledged
    assert 101 not in submits  # pending IN that was unlinked never RET_SUBMITs


def test_exactly_once_completion_under_unlink_race() -> None:
    """UNLINK racing with completion must never yield RET_UNLINK before
    RET_SUBMIT for the same URB, and never a duplicate completion."""
    device = FakeDevice(write_delay=0.002)  # keep workers busy to force the race
    count = 200
    parts: list[bytes] = []
    unlink_to_orig: dict[int, int] = {}
    for i in range(count):
        orig = 1000 + i
        unlink_cmd = 500000 + i
        unlink_to_orig[unlink_cmd] = orig
        parts.append(_submit(orig, DIR_OUT, 2, buflen=4, payload=b"XXXX"))
        parts.append(_unlink(unlink_cmd, orig))

    resp = _run(b"".join(parts), device)

    submit_pos: dict[int, int] = {}
    unlink_pos: dict[int, int] = {}
    submit_count: dict[int, int] = {}
    for pos, (kind, seqnum, _status, _data) in enumerate(resp):
        if kind == "submit":
            submit_pos.setdefault(seqnum, pos)
            submit_count[seqnum] = submit_count.get(seqnum, 0) + 1
        else:
            unlink_pos.setdefault(seqnum, pos)

    for unlink_cmd, orig in unlink_to_orig.items():
        sp = submit_pos.get(orig)
        up = unlink_pos.get(unlink_cmd)
        # The fatal ordering is RET_UNLINK(orig) before RET_SUBMIT(orig).
        assert not (sp is not None and up is not None and up < sp), (
            f"fatal RET_UNLINK-before-RET_SUBMIT for seqnum {orig}"
        )
        assert submit_count.get(orig, 0) <= 1, f"duplicate RET_SUBMIT for seqnum {orig}"
        assert sp is not None or up is not None, f"seqnum {orig} got no terminal response"


def test_client_socket_has_nagle_disabled() -> None:
    """Accepted client sockets must have TCP_NODELAY set.

    USB/IP is a small-PDU request/response protocol; Nagle plus the peer's
    delayed-ACK timer adds tens to hundreds of ms per URB, which breaks the
    DTR/RTS auto-reset timing serial bootloaders depend on.
    """
    import socket as _socket

    listener = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    client = _socket.create_connection(listener.getsockname())
    accepted, _ = listener.accept()
    try:
        assert accepted.getsockopt(_socket.IPPROTO_TCP, _socket.TCP_NODELAY) == 0
        srv.USBIPServer._configure_client_socket(accepted)
        assert accepted.getsockopt(_socket.IPPROTO_TCP, _socket.TCP_NODELAY) != 0
    finally:
        accepted.close()
        client.close()
        listener.close()
