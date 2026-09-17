"""Sideways fallback on a `ProviderError` [ROUTE-7, ROUTE-10, PRV-13]."""

from __future__ import annotations

import pytest

from edgar.core.errors import ConfigError
from edgar.providers.base import Capabilities
from edgar.providers.fallback import Candidate, NoFallback, chain_from_config, choose

CAPS = Capabilities(
    tools=True,
    parallel_tool_calls=True,
    streaming=True,
    reasoning=True,
    prompt_caching=True,
    images=False,
    max_context=100_000,
    max_output=8_000,
)
NO_TOOLS = Capabilities(
    tools=False,
    parallel_tool_calls=False,
    streaming=True,
    reasoning=False,
    prompt_caching=False,
    images=False,
    max_context=100_000,
    max_output=8_000,
)


def _c(
    model: str, family: str = "openai-compatible", capabilities: Capabilities = CAPS
) -> Candidate:
    return Candidate(model, family, capabilities)


def test_picks_the_next_candidate_in_order() -> None:
    failed = _c("a/one")
    chain = (_c("a/one"), _c("b/two"), _c("c/three"))
    result = choose(failed, chain, tried=frozenset(), tools_required=False)
    assert result.model == "b/two"


def test_skips_candidates_already_tried() -> None:
    failed = _c("a/one")
    chain = (_c("a/one"), _c("b/two"), _c("c/three"))
    result = choose(failed, chain, tried=frozenset({"b/two"}), tools_required=False)
    assert result.model == "c/three"


def test_reasoning_survives_a_same_family_switch() -> None:
    failed = _c("a/one", family="anthropic")
    chain = (_c("a/one", family="anthropic"), _c("b/two", family="anthropic"))
    result = choose(failed, chain, tried=frozenset(), tools_required=False)
    assert result.reasoning is True


def test_reasoning_drops_on_a_family_switch() -> None:
    failed = _c("a/one", family="anthropic")
    chain = (_c("a/one", family="anthropic"), _c("b/two", family="openai-compatible"))
    result = choose(failed, chain, tried=frozenset(), tools_required=False)
    assert result.reasoning is False


def test_never_falls_back_to_a_candidate_missing_required_tools() -> None:
    failed = _c("a/one")
    chain = (_c("a/one"), _c("b/no-tools", capabilities=NO_TOOLS), _c("c/three"))
    result = choose(failed, chain, tried=frozenset(), tools_required=True)
    assert result.model == "c/three"


def test_no_fallback_left_raises() -> None:
    failed = _c("a/one")
    chain = (_c("a/one"),)
    with pytest.raises(NoFallback, match="a/one"):
        choose(failed, chain, tried=frozenset(), tools_required=False)


def test_no_fallback_when_every_candidate_was_tried() -> None:
    failed = _c("a/one")
    chain = (_c("a/one"), _c("b/two"))
    with pytest.raises(NoFallback):
        choose(failed, chain, tried=frozenset({"b/two"}), tools_required=False)


def test_chain_from_config_parses_the_list() -> None:
    assert chain_from_config({"model.fallback": ["a/one", "b/two"]}) == ("a/one", "b/two")


def test_no_fallback_key_is_an_empty_chain() -> None:
    assert chain_from_config({}) == ()


@pytest.mark.parametrize(
    "later",
    [
        {"model.fallback": "not a list"},
        {"model.fallback": [1, 2]},
        {"model.fallback": [""]},
    ],
)
def test_a_malformed_fallback_chain_is_a_config_error(later: dict[str, object]) -> None:
    with pytest.raises(ConfigError):
        chain_from_config(later)
