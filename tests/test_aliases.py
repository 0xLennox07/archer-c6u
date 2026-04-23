"""Alias persistence + lookup."""
from c6u import aliases


def test_set_lookup_remove(tmp_path, monkeypatch):
    monkeypatch.setattr(aliases, "ALIASES_PATH", tmp_path / "a.json")
    aliases.set_alias("aa-bb-cc-dd-ee-ff", "Test Phone")
    assert aliases.lookup("AA:BB:CC:DD:EE:FF") == "Test Phone"
    assert aliases.lookup("Aa-Bb-Cc-Dd-Ee-Ff") == "Test Phone"
    assert aliases.remove_alias("AA-BB-CC-DD-EE-FF") is True
    assert aliases.lookup("AA:BB:CC:DD:EE:FF") is None
    assert aliases.remove_alias("AA:BB:CC:DD:EE:FF") is False
