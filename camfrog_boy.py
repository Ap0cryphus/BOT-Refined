"""Compatibility entry point for the requested Camfrog bot main script."""

from camfrog_bot import CamfrogBot, main

__all__ = ["CamfrogBot", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
