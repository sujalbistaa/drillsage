"""Load basin packs (YAML under `drillsage/config/basin_packs/`) into domain objects."""

from functools import cache
from importlib import resources

import yaml
from pydantic import BaseModel, ConfigDict

from drillsage.domain.formations import BasinPack, StratLevel, StratUnit

_PACKAGE = "drillsage.config.basin_packs"


class _UnitSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    level: StratLevel
    group: str | None = None
    aliases: tuple[str, ...] = ()


class _PackSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    name: str
    units: tuple[_UnitSpec, ...]


def available_basin_packs() -> list[str]:
    return sorted(
        entry.name.removesuffix(".yaml")
        for entry in resources.files(_PACKAGE).iterdir()
        if entry.name.endswith(".yaml")
    )


@cache
def load_basin_pack(key: str) -> BasinPack:
    if key not in available_basin_packs():
        raise KeyError(f"unknown basin pack {key!r}; available: {available_basin_packs()}")
    text = resources.files(_PACKAGE).joinpath(f"{key}.yaml").read_text(encoding="utf-8")
    spec = _PackSpec.model_validate(yaml.safe_load(text))
    if spec.key != key:
        raise ValueError(f"basin pack file {key}.yaml declares key {spec.key!r}")
    groups = {u.name for u in spec.units if u.level is StratLevel.GROUP}
    for unit in spec.units:
        if unit.group is not None and unit.group not in groups:
            raise ValueError(f"basin pack {key!r}: {unit.name} names unknown group {unit.group}")
    return BasinPack(
        key=spec.key,
        name=spec.name,
        units=tuple(
            StratUnit(name=u.name, level=u.level, group=u.group, aliases=u.aliases)
            for u in spec.units
        ),
    )
