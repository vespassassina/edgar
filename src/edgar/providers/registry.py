"""Model string → provider, loaded lazily [PRV-4].

Nothing here imports an adapter at module level: `import_module` runs only when a
model string names that provider, so startup never pays for an SDK or HTTP client
it does not use. Real providers and user-defined ones arrive in M2 [PRV-12].
"""

from __future__ import annotations

from importlib import import_module
from typing import cast

from edgar.core.errors import ConfigError
from edgar.providers.base import Provider

_BUILTIN = {
    "fake": "edgar.providers.fake",
}


def resolve(model_string: str) -> tuple[Provider, str]:
    """`"fake/test"` → (the fake provider, `"test"`)."""
    name, slash, model = model_string.partition("/")
    if not slash or not name or not model:
        raise ConfigError(
            f"model {model_string!r} is not in the form provider/model",
            hint='for example --model fake/test, or [model] default = "fake/test"',
        )
    module = _BUILTIN.get(name)
    if module is None:
        known = ", ".join(sorted(_BUILTIN))
        raise ConfigError(
            f"unknown provider {name!r} in model {model_string!r}",
            hint=f"known providers: {known}. Real providers arrive in milestone M2",
        )
    return cast(Provider, import_module(module).make()), model
