"""Backend services (extension bridge, click client)."""

from .click_client import ClickClient
from .extension_bridge import extension_bridge

__all__ = ["ClickClient", "extension_bridge"]
