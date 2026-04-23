"""Router client factory + context manager."""
from __future__ import annotations

import contextlib
import logging

from .config import load_config


@contextlib.contextmanager
def router(debug: bool = False):
    """Authenticated router client. Guarantees logout even on error.

    Honors C6U_FAKE=1 (or `c6u --fake`) to swap in a recorded-fixture client,
    so the entire stack can run offline.
    """
    from . import fakerouter
    if fakerouter.is_enabled():
        fr = fakerouter.FakeRouter()
        fr.authorize()
        try:
            yield fr
        finally:
            fr.logout()
        return

    from tplinkrouterc6u import TplinkRouterProvider
    cfg = load_config()
    logger = logging.getLogger("c6u")
    if debug and not logger.handlers:
        logging.basicConfig(level=logging.DEBUG)
    client = TplinkRouterProvider.get_client(
        host=cfg["host"],
        password=cfg["password"],
        username=cfg.get("username", "admin"),
        logger=logger,
        verify_ssl=cfg.get("verify_ssl", False),
        timeout=cfg.get("timeout", 30),
    )
    client.authorize()
    try:
        yield client
    finally:
        try:
            client.logout()
        except Exception:
            pass
