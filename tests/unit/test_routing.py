"""Declarative `[[route]]` rules and capability validation [ROUTE-2, ROUTE-6, ROUTE-9]."""

from __future__ import annotations

import pytest

from edgar.config.schema import ModelSection
from edgar.core.errors import ConfigError
from edgar.providers.routing import (
    Route,
    RoutingContext,
    check_capabilities,
    routes_from_config,
    select_model,
)


def test_a_rule_wins_over_the_role_binding() -> None:
    models = ModelSection(default="a/main")
    rules = (Route(name="big-context", model="b/long", prompt_tokens_gt=1000),)
    small = select_model(RoutingContext(prompt_tokens=10), models, rules)
    assert (small.model, small.rule) == ("a/main", "default")
    big = select_model(RoutingContext(prompt_tokens=5000), models, rules)
    assert (big.model, big.rule) == ("b/long", "big-context")


def test_first_match_wins() -> None:
    models = ModelSection(default="a/main")
    rules = (
        Route(name="first", model="b/one", mode="yolo"),
        Route(name="second", model="c/two", mode="yolo"),
    )
    chosen = select_model(RoutingContext(mode="yolo"), models, rules)
    assert chosen.rule == "first"


def test_an_agents_own_model_beats_every_rule() -> None:
    models = ModelSection(default="a/main")
    rules = (Route(name="catch-all", model="b/other", role="subagent"),)
    ctx = RoutingContext(role="subagent", agent="reviewer", agent_model="c/named")
    chosen = select_model(ctx, models, rules)
    assert (chosen.model, chosen.rule) == ("c/named", "agent")


@pytest.mark.parametrize(
    ("rule", "ctx", "matches"),
    [
        (Route(name="r", model="m", role="subagent"), RoutingContext(role="main"), False),
        (Route(name="r", model="m", agent="explorer"), RoutingContext(agent="explorer"), True),
        (
            Route(name="r", model="m", tools_required=True),
            RoutingContext(tools_required=False),
            False,
        ),
        (Route(name="r", model="m", prompt_tokens_lt=100), RoutingContext(prompt_tokens=50), True),
        (
            Route(name="r", model="m", prompt_tokens_lt=100),
            RoutingContext(prompt_tokens=200),
            False,
        ),
        (
            Route(name="r", model="m", budget_remaining_lt=0.2),
            RoutingContext(budget_remaining_fraction=0.1),
            True,
        ),
        (Route(name="r", model="m", tags=frozenset({"cheap"})), RoutingContext(), False),
        (
            Route(name="r", model="m", tags=frozenset({"cheap"})),
            RoutingContext(tags=frozenset({"cheap", "fast"})),
            True,
        ),
        (Route(name="r", model="m", schedule="nightly"), RoutingContext(schedule="hourly"), False),
    ],
)
def test_rule_conditions_must_all_hold(rule: Route, ctx: RoutingContext, matches: bool) -> None:
    models = ModelSection(default="a/main")
    chosen = select_model(ctx, models, (rule,))
    assert (chosen.rule == "r") == matches


def test_capability_check_passes_when_tools_are_not_needed_or_are_present() -> None:
    models = ModelSection(default="a/main")
    selection = select_model(RoutingContext(), models)
    check_capabilities(selection, tools_required=False, has_tools=False)
    check_capabilities(selection, tools_required=True, has_tools=True)


def test_capability_check_fails_loudly_at_selection() -> None:
    models = ModelSection(default="a/main")
    selection = select_model(RoutingContext(), models)
    with pytest.raises(ConfigError, match="needs tools"):
        check_capabilities(selection, tools_required=True, has_tools=False)


def test_routes_from_config_parses_toml_array_of_tables() -> None:
    later = {
        "route": [
            {"name": "cheap", "model": "a/small", "mode": "auto", "tags": ["fast"]},
            {"model": "b/big", "prompt_tokens_gt": 5000},  # unnamed: gets an index name
        ]
    }
    rules = routes_from_config(later)
    assert len(rules) == 2
    assert rules[0] == Route(name="cheap", model="a/small", mode="auto", tags=frozenset({"fast"}))
    assert rules[1].name == "route-1" and rules[1].prompt_tokens_gt == 5000


def test_no_route_key_is_no_rules() -> None:
    assert routes_from_config({}) == ()


@pytest.mark.parametrize(
    "raw",
    [
        {"route": "not a list"},
        {"route": ["not a table"]},
        {"route": [{"name": "no-model"}]},
        {"route": [{"model": ""}]},
        {"route": [{"model": 5}]},
        {"route": [{"model": "a/b", "prompt_tokens_over": 10}]},  # a misspelt condition
    ],
)
def test_a_malformed_route_rule_is_a_config_error(raw: dict[str, object]) -> None:
    with pytest.raises(ConfigError):
        routes_from_config(raw)
