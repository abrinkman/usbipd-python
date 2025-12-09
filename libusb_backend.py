# SPDX-FileCopyrightText: 2025 Alexander Brinkman
# SPDX-License-Identifier: GPL-3.0-or-later
"""Libusb backend helper module.

This module provides a cross-platform way to get a libusb backend for pyusb.
It uses the bundled libusb library from the 'libusb' pip package.
"""

import os
import platform
import sys
from typing import Any

# Import libusb to ensure it's installed (it's a required dependency)
import libusb
import usb.backend.libusb1 as libusb1


def _get_bundled_libusb_path() -> str:
    """Get the path to the bundled libusb library from the 'libusb' package.

    Returns:
        The path to the libusb library.

    Raises:
        RuntimeError: If the bundled library cannot be found.
    """
    platform_dir = os.path.dirname(libusb._platform.__file__)

    # Determine OS and library name
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
    if not os.path.exists(lib_path):
        raise RuntimeError(
            f"Bundled libusb library not found at {lib_path}. "
            f"Try reinstalling: pip install --force-reinstall libusb"
        )

    return lib_path


def get_backend(fresh: bool = False) -> Any:
    """Get a libusb backend for pyusb.

    Uses the bundled libusb library from the 'libusb' pip package.

    Args:
        fresh: Unused, kept for API compatibility. Each call creates a new
               backend instance which forces re-enumeration of USB devices.

    Returns:
        A libusb backend instance for use with pyusb.

    Raises:
        RuntimeError: If the libusb backend cannot be initialized.
    """
    _ = fresh  # Unused, but kept for API compatibility

    lib_path = _get_bundled_libusb_path()
    backend = libusb1.get_backend(find_library=lambda _: lib_path)

    if backend is None:
        raise RuntimeError(
            f"Failed to initialize libusb backend from {lib_path}. "
            f"Try reinstalling: pip install --force-reinstall libusb"
        )

    return backend

    return backend
