"""The GitHub Copilot provider: a removable v4 file [NFR-12, PRV-19, ADR-0043].

Not exercised through cassettes yet (no test-mode key to record with), so this
checks the row's own data and the one branch that needs no network: a missing
client id.
"""

from __future__ import annotations

import pytest

from edgar.core.errors import ConfigError
from edgar.providers.github_copilot import ROW, sign_in
from edgar.providers.quirks import _optional_row


def test_the_row_names_its_own_host_and_device_flow() -> None:
    # A provider's own host is chosen by naming the provider, never guessed [PRV-15].
    assert ROW.base_url == "https://api.githubcopilot.com"
    assert ROW.device is not None
    assert ROW.device.client_id_env == "GITHUB_COPILOT_CLIENT_ID"


def test_quirks_finds_the_row_by_name() -> None:
    assert _optional_row("github-copilot") is ROW
    assert _optional_row("openai") is None


def test_sign_in_without_a_client_id_names_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_COPILOT_CLIENT_ID", raising=False)
    with pytest.raises(ConfigError, match="GITHUB_COPILOT_CLIENT_ID is not set"):
        sign_in("github-copilot", ROW.device, print)  # type: ignore[arg-type]
