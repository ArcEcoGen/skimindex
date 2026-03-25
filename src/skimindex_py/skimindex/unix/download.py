"""
Download utilities using curl via plumbum.

Provides Pythonic interface to curl for HTTP/HTTPS operations.
"""

from skimindex.unix.base import LoggedBoundCommand, local


def curl(*args: str) -> LoggedBoundCommand:
    """
    Execute curl command with given arguments.

    Returns a Command object that can be executed with ().

    Args:
        *args: Arguments to pass to curl

    Returns:
        Command: plumbum Command object to be executed with ()
    """
    return local["curl"][*args]


def curl_download(url: str, *extra_args: str) -> LoggedBoundCommand:
    """
    Download from URL with sensible defaults for robustness.

    Includes:
      - HTTP/2 support (faster like modern browsers)
      - User-Agent header (avoid throttling)
      - Max time: 300 seconds (5 minutes)
      - Automatic retries: up to 3 times on failure
      - Silent mode (-s) and follow redirects (-L)

    Args:
        url: URL to download
        *extra_args: Additional curl arguments (e.g., "-o", "filename")

    Returns:
        Command: plumbum Command object to be executed with ()
    """
    return curl(
        "-s",
        "-L",
        "--http2",
        "--user-agent",
        "Mozilla/5.0",
        "--retry",
        "3",
        url,
        *extra_args,
    )
