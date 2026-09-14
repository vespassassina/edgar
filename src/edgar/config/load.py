"""Config layering with provenance [CFG-1, CFG-2, CFG-3, CFG-8].

    defaults < ~/.edgar/config.toml < ./.edgar/config.toml < EDGAR_* env < flags

Read once, at session start: a change to a config file takes effect in the next
session. Environment variables are named `EDGAR_<SECTION>_<KEY>`, for example
`EDGAR_TOOLS_MAX_OUTPUT_TOKENS=4000`; variables whose section edgar does not have
(`EDGAR_IDENTITY`, say) belong to someone else and are left alone.
"""

from __future__ import annotations

import dataclasses
import difflib
import os
import tomllib
import types
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from edgar.config.schema import LATER, SECTIONS, TABLES, Config
from edgar.core.errors import ConfigError

_BOOLS = {"true": True, "1": True, "yes": True, "on": True}
_BOOLS |= {"false": False, "0": False, "no": False, "off": False}


def _fields(sections: Mapping[str, type]) -> dict[str, tuple[Any, Any]]:
    out: dict[str, tuple[Any, Any]] = {}
    for section, cls in sections.items():
        hints = get_type_hints(cls)
        for f in dataclasses.fields(cls):
            default = f.default
            if f.default_factory is not dataclasses.MISSING:
                default = f.default_factory()
            out[f"{section}.{f.name}"] = (hints[f.name], default)
    return out


FIELDS = _fields(SECTIONS)
BLOCK_FIELDS = _fields(TABLES)  # "providers.base_url" → the hint for every [providers.X]


def user_config(home: Path) -> Path:
    return home / ".edgar" / "config.toml"


def project_config(cwd: Path) -> Path:
    return cwd / ".edgar" / "config.toml"


def load(
    cwd: Path,
    *,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
    flags: Mapping[str, tuple[Any, str]] | None = None,
) -> Config:
    """`flags` maps a dotted key to (value, how it was given), e.g.
    `{"model.default": ("fake/test", "flag --model")}`."""
    values = {key: default for key, (_, default) in FIELDS.items()}
    origins = dict.fromkeys(FIELDS, "default")
    later: dict[str, Any] = {}
    blocks: dict[str, dict[str, dict[str, Any]]] = {section: {} for section in TABLES}

    for path in (user_config(home or Path.home()), project_config(cwd)):
        if path.is_file():
            for key, value in _read_file(path, later).items():
                # A credential is personal: a cloned repository never names the command
                # that mints yours, so api_key_command is read from user config only.
                if key.endswith(".api_key_command") and path == project_config(cwd):
                    raise ConfigError(f"{path}: api_key_command is read from user config only")
                origins[key] = str(path)
                section, _, rest = key.partition(".")
                if section in TABLES:  # blocks merge key by key across files, like the rest
                    block, _, name = rest.rpartition(".")
                    blocks[section].setdefault(block, {})[name] = value
                else:
                    values[key] = value

    for name, raw in (os.environ if env is None else env).items():
        env_key = _env_key(name)
        if env_key is not None:
            values[env_key] = _parse_env(name, env_key, raw)
            origins[env_key] = f"env {name}"

    for key, (value, how) in (flags or {}).items():
        _check(how, key, value)
        values[key], origins[key] = value, how

    sections = {
        name: cls(**{k.split(".", 1)[1]: v for k, v in values.items() if k.startswith(name + ".")})
        for name, cls in SECTIONS.items()
    }
    tables = {
        section: {name: _block(section, name, fields, origins) for name, fields in named.items()}
        for section, named in blocks.items()
    }
    return Config(**sections, **tables, origins=origins, later=later)  # type: ignore[arg-type]  # both dicts are keyed by field name, built from the schema


def _block(section: str, name: str, fields: dict[str, Any], origins: dict[str, str]) -> Any:
    cls = TABLES[section]
    missing = [
        f.name
        for f in dataclasses.fields(cls)
        if f.default is f.default_factory is dataclasses.MISSING and f.name not in fields
    ]
    if missing:
        where = origins[f"{section}.{name}.{next(iter(fields))}"]
        example = _example(BLOCK_FIELDS[f"{section}.{missing[0]}"][0])
        raise ConfigError(
            f"{where}: {_title(section, name)} needs {', '.join(missing)}",
            hint=f"for example: {missing[0]} = {example}",
        )
    return cls(**fields)


def _title(section: str, name: str) -> str:
    bare = name.replace("-", "").replace("_", "").isalnum()
    return f"[{section}.{name}]" if bare else f'[{section}."{name}"]'


def _read_file(path: Path, later: dict[str, Any]) -> dict[str, Any]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: not valid TOML: {exc}", hint="fix the syntax") from None
    found: dict[str, Any] = {}
    for section, table in data.items():
        if section in LATER:
            later[section] = table
            continue
        if section not in SECTIONS and section not in TABLES:
            raise ConfigError(
                f"{path}: unknown section [{section}]",
                hint=_did_you_mean(section, [*SECTIONS, *TABLES, *LATER]),
            )
        if not isinstance(table, dict):
            raise ConfigError(f"{path}: {section} must be a table, written [{section}]")
        if section in TABLES:
            for block, fields in table.items():
                if not isinstance(fields, dict):
                    raise ConfigError(
                        f"{path}: {section}.{block} must be a table, "
                        f"written {_title(section, block)}"
                    )
                for name, value in fields.items():
                    key = f"{section}.{block}.{name}"
                    _check(str(path), key, value)
                    found[key] = value
            continue
        for name, value in table.items():
            key = f"{section}.{name}"
            if key in LATER:
                later[key] = value
                continue
            _check(str(path), key, value)
            found[key] = value
    return found


def _env_key(name: str) -> str | None:
    if not name.startswith("EDGAR_"):
        return None
    section, _, rest = name[len("EDGAR_") :].lower().partition("_")
    if section in TABLES:
        raise ConfigError(
            f"environment variable {name}: [{section}] blocks are set in config.toml only",
            hint=f"write it as [{section}.NAME] in .edgar/config.toml",
        )
    if section not in SECTIONS:
        return None
    key = f"{section}.{rest}"
    if key not in FIELDS:
        raise ConfigError(
            f"environment variable {name}: unknown key [{section}] {rest}",
            hint=_did_you_mean(rest, _keys_of(section), prefix=f"EDGAR_{section.upper()}_"),
        )
    return key


def _parse_env(name: str, key: str, raw: str) -> Any:
    hint = _unwrap_optional(FIELDS[key][0])
    value: Any = raw
    try:
        if raw == "" and hint is not FIELDS[key][0]:
            value = None
        elif hint is bool:
            value = _BOOLS[raw.strip().lower()]
        elif hint is int:
            value = int(raw)
        elif hint is float:
            value = float(raw)
        elif get_origin(hint) is list:
            value = [part.strip() for part in raw.split(",") if part.strip()]
    except (KeyError, ValueError):
        pass  # left as the raw string, so _check reports it with the expected type
    _check(f"environment variable {name}", key, value)
    return value


def _check(where: str, key: str, value: Any) -> None:
    section, _, name = key.partition(".")
    fields, title = FIELDS, f"[{section}]"
    if section in TABLES:  # "providers.lmstudio.base_url"; a block name may hold dots
        block, _, name = name.rpartition(".")
        fields, key, title = BLOCK_FIELDS, f"{section}.{name}", _title(section, block)
    if key not in fields:
        raise ConfigError(
            f"{where}: unknown key {title} {name}",
            hint=_did_you_mean(name, _keys_of(section, fields)),
        )
    hint = fields[key][0]
    if not _accepts(hint, value):
        raise ConfigError(
            f"{where}: {title} {name} must be {_describe(hint)}, got {_type_name(value)} {value!r}",
            hint=f"for example: {name} = {_example(hint)}",
        )


def _accepts(hint: Any, value: Any) -> bool:
    origin = get_origin(hint)
    if origin is Literal:
        return value in get_args(hint)
    if origin in (Union, types.UnionType):
        return any(_accepts(arg, value) for arg in get_args(hint))
    if origin is list:
        (item,) = get_args(hint)
        return isinstance(value, list) and all(_accepts(item, v) for v in value)
    if origin is dict:
        _, item = get_args(hint)
        return isinstance(value, dict) and all(_accepts(item, v) for v in value.values())
    if hint is type(None):
        return value is None
    if hint is bool:
        return isinstance(value, bool)
    if hint is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if hint is float:
        return isinstance(value, int | float) and not isinstance(value, bool)
    return bool(hint is str and isinstance(value, str))


def _describe(hint: Any) -> str:
    origin = get_origin(hint)
    if origin is Literal:
        return "one of " + ", ".join(f'"{a}"' for a in get_args(hint))
    if origin in (Union, types.UnionType):
        return " or ".join(_describe(a) for a in get_args(hint) if a is not type(None))
    if origin is list:
        return "a list of strings"
    if origin is dict:
        return f"a table of {_describe(get_args(hint)[1])}"
    names = {bool: "true or false", int: "an integer", float: "a number", str: "a string"}
    return names.get(hint, str(hint))


def _example(hint: Any) -> str:
    hint = _unwrap_optional(hint)
    if get_origin(hint) is Literal:
        return f'"{get_args(hint)[0]}"'
    if get_origin(hint) is list:
        return '["…"]'
    if get_origin(hint) is dict:
        return '{ shell = "ask" }'
    return {bool: "true", int: "8000", float: "0.5"}.get(hint, '"…"')


def _unwrap_optional(hint: Any) -> Any:
    if get_origin(hint) in (Union, types.UnionType):
        args = [a for a in get_args(hint) if a is not type(None)]
        return args[0] if len(args) == 1 else hint
    return hint


def _type_name(value: Any) -> str:
    kinds = {bool: "boolean", int: "integer", float: "number", str: "string"}
    kinds |= {list: "array", dict: "table"}
    return kinds.get(type(value), type(value).__name__)


def _keys_of(section: str, fields: Mapping[str, Any] = FIELDS) -> list[str]:
    return [k.split(".", 1)[1] for k in fields if k.startswith(section + ".")]


def _did_you_mean(name: str, options: list[str], prefix: str = "") -> str:
    close = difflib.get_close_matches(name, options, n=1)
    if close:
        return f"did you mean {prefix}{close[0].upper() if prefix else close[0]}?"
    return "known: " + ", ".join(sorted(options))
