"""
Download utilities using curl via plumbum.

Provides Pythonic interface to curl for HTTP/HTTPS operations.
"""

from plumbum import local


def curl(*args):
    """
    Execute curl command with given arguments.

    Returns the output as a string.

    Args:
        *args: Arguments to pass to curl

    Returns:
        str: Standard output from curl
    """
    return local["curl"](*args)
