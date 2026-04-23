"""Wake-on-LAN magic packet shape + MAC resolution."""
from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from c6u import wol


def test_send_wol_packet_shape():
    captured = {}

    class FakeSock:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def setsockopt(self, *a, **k): pass
        def sendto(self, data, addr):
            captured["data"] = data
            captured["addr"] = addr

    with patch.object(socket, "socket", return_value=FakeSock()):
        wol.send_wol("AA:BB:CC:DD:EE:FF")
    assert captured["addr"] == ("255.255.255.255", 9)
    assert captured["data"][:6] == b"\xff" * 6
    assert captured["data"][6:12] == bytes.fromhex("AABBCCDDEEFF")
    assert len(captured["data"]) == 6 + 16 * 6


def test_send_wol_bad_mac():
    with pytest.raises(ValueError):
        wol.send_wol("not-a-mac")
