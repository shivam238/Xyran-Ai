"""Shared connectivity helpers for hybrid online/offline routing."""

import socket

DEFAULT_INTERNET_TIMEOUT = 3.0


def has_internet(timeout: float = DEFAULT_INTERNET_TIMEOUT) -> bool:
    """True when a general outbound connection is likely available."""
    try:
        with socket.create_connection(("8.8.8.8", 53), timeout=timeout):
            return True
    except OSError:
        return False
