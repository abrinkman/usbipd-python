# SPDX-FileCopyrightText: 2025 abrinkman
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Libusb backend helper module.

This module provides a cross-platform way to get a libusb backend for pyusb.
It uses the bundled libusb library from the 'libusb' package on all platforms.
"""

import os
import platform
import sys
from typing import Any

import usb.backend.libusb1 as libusb1


def _get_bundled_libusb_path() -> str | None:
    """
    Get the path to the bundled libusb library from the 'libusb' package.

    Returns:
        The path to the libusb library, or None if not found.
    """
    try:
        import libusb

        platform_dir = os.path.dirname(libusb._platform.__file__)

        # Determine OS and architecture
        if sys.platform == "win32":
            os_name = "windows"
            lib_name = "libusb-1.0.dll"
        elif sys.platform == "darwin":
            os_name = "macos"
            lib_name = "libusb-1.0.dylib"
        else:
            os_name = "linux"
            lib_name = "libusb-1.0.so"

        # Determine architecture
        machine = platform.machine().lower()
        if machine in ("x86_64", "amd64"):
            arch = "x86_64"
        elif machine in ("aarch64", "arm64"):
            arch = "arm64" if sys.platform == "darwin" else "aarch64"
        elif machine in ("i386", "i686", "x86"):
            arch = "x86"
        elif machine.startswith("arm"):
            arch = "armhf"
        else:
            arch = "x86_64"  # Default fallback

        lib_path = os.path.join(platform_dir, os_name, arch, lib_name)
        if os.path.exists(lib_path):
            return lib_path
    except ImportError:
        pass

    return None


def get_backend() -> Any:
    """
    Get a libusb backend for pyusb.

    Uses the bundled libusb library from the 'libusb' package if available,
    otherwise falls back to the system libusb installation.

    Returns:
        A libusb backend instance for use with pyusb.

    Raises:
        RuntimeError: If no libusb backend is available.
    """
    backend = None

    # Try to use the bundled libusb library first
    lib_path = _get_bundled_libusb_path()
    if lib_path:
        backend = libusb1.get_backend(find_library=lambda _: lib_path)

    if backend is None:
        # Fall back to system libusb
        backend = libusb1.get_backend()

    if backend is None:
        raise RuntimeError(
            "No libusb backend available. "
            "Install the 'libusb' package: pip install libusb"
        )

    return backend
