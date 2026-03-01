"""Backward-compat shim — real server lives in twincat_validator.server."""

from twincat_validator.server import *  # noqa: F401,F403
from twincat_validator.server import main  # noqa: F401

if __name__ == "__main__":
    main()
