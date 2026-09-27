"""Declarative XML → Pydantic mapping.

Each model field declares the XML child it comes from with `Xml(tag, kind)` metadata:

    md_m: Annotated[float | None, Xml("md", Kind.LENGTH)] = None

The same declarations drive parsing, unit conversion to canonical units, null-sentinel
handling and the parser-fidelity check (which XML paths are mapped). A field cannot be parsed
without also being accounted for in the fidelity report.
"""

import types
import typing
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime
from functools import cache
from typing import Final, get_args, get_origin

from lxml import etree
from pydantic import BaseModel

from drillsage.core.errors import InvalidInputError
from drillsage.core.units import Kind, is_null_sentinel, to_canonical
from drillsage.ingest.xml_safe import local_name

_TRUE: Final = frozenset({"true", "1", "yes"})
_FALSE: Final = frozenset({"false", "0", "no"})
_KNOWN_DEPTH_DATUMS: Final = frozenset({"RKB", "KB"})
"""Kelly bushing and rotary kelly bushing are the same reference on these rigs."""


class XmlValueError(InvalidInputError):
    slug = "xml-value"


@dataclass(frozen=True, slots=True)
class Xml:
    tag: str
    kind: Kind | None = None


@dataclass(frozen=True, slots=True)
class _Leaf:
    field: str
    tag: str
    scalar: type
    kind: Kind | None


@dataclass(frozen=True, slots=True)
class _Child:
    field: str
    tag: str
    model: type[BaseModel]
    many: bool


@dataclass(frozen=True, slots=True)
class _Spec:
    leaves: dict[str, _Leaf]
    children: dict[str, _Child]


_SCALARS: Final = (str, int, float, bool, datetime, date)


def _unwrap_optional(annotation: object) -> object:
    origin = get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


@cache
def spec_for(model: type[BaseModel]) -> _Spec:
    leaves: dict[str, _Leaf] = {}
    children: dict[str, _Child] = {}
    for name, info in model.model_fields.items():
        marks = [m for m in info.metadata if isinstance(m, Xml)]
        if len(marks) != 1:
            raise TypeError(f"{model.__name__}.{name} needs exactly one Xml(...) annotation")
        mark = marks[0]
        if mark.tag in leaves or mark.tag in children:
            raise TypeError(f"{model.__name__}: tag {mark.tag!r} mapped twice")
        target = _unwrap_optional(info.annotation)
        if get_origin(target) is list:
            (item,) = get_args(target)
            if not (isinstance(item, type) and issubclass(item, BaseModel)):
                raise TypeError(f"{model.__name__}.{name}: lists must hold models")
            children[mark.tag] = _Child(name, mark.tag, item, many=True)
        elif isinstance(target, type) and issubclass(target, BaseModel):
            children[mark.tag] = _Child(name, mark.tag, target, many=False)
        elif target in _SCALARS:
            assert isinstance(target, type)  # noqa: S101 - narrowed by the membership test
            if target is float and mark.kind is None and name.endswith("_m"):
                raise TypeError(f"{model.__name__}.{name}: depth fields must declare a unit kind")
            leaves[mark.tag] = _Leaf(name, mark.tag, target, mark.kind)
        else:
            raise TypeError(f"{model.__name__}.{name}: unsupported annotation {target!r}")
    return _Spec(leaves, children)


def _parse_bool(text: str) -> bool:
    lowered = text.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    raise ValueError(text)


def _parse_datetime(text: str) -> datetime:
    value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        raise ValueError("timestamp has no UTC offset")
    return value


def _parse_date(text: str) -> date:
    return date.fromisoformat(text[:10])


_TEXT_PARSERS: Final[dict[type, Callable[[str], object]]] = {
    str: str,
    bool: _parse_bool,
    datetime: _parse_datetime,
    date: _parse_date,
}


def _quantity(leaf: _Leaf, element: etree._Element, number: float, path: str) -> object:
    if is_null_sentinel(number):
        return None
    if leaf.scalar is int:
        if not number.is_integer():
            raise XmlValueError(f"{path}: expected an integer, got {number!r}")
        return int(number)
    datum = element.get("datum")
    if datum is not None and datum not in _KNOWN_DEPTH_DATUMS:
        raise XmlValueError(f"{path}: unsupported depth datum {datum!r}")
    if leaf.kind is None:
        return number
    return to_canonical(number, element.get("uom"), leaf.kind)


def _scalar(leaf: _Leaf, element: etree._Element, path: str) -> object:
    text = (element.text or "").strip()
    if not text:
        return None
    parser = _TEXT_PARSERS.get(leaf.scalar)
    try:
        if parser is not None:
            return parser(text)
        number = float(text)
    except ValueError as exc:
        raise XmlValueError(f"{path}: cannot read {text!r} as {leaf.scalar.__name__}") from exc
    return _quantity(leaf, element, number, path)


def _is_null_text(element: etree._Element) -> bool:
    text = (element.text or "").strip()
    try:
        return is_null_sentinel(float(text))
    except ValueError:
        return False


@dataclass
class ParseReport:
    """What the parser saw: mapped and unmapped leaf paths, and null sentinels read."""

    mapped: Counter[str]
    unmapped: Counter[str]
    nulls: Counter[str]

    @classmethod
    def empty(cls) -> "ParseReport":
        return cls(Counter(), Counter(), Counter())


def parse_model[M: BaseModel](
    element: etree._Element, model: type[M], path: str, report: ParseReport
) -> M:
    """Build `model` from `element`'s children, recording every leaf path in `report`."""
    spec = spec_for(model)
    values: dict[str, object] = {}
    lists: dict[str, list[BaseModel]] = {c.field: [] for c in spec.children.values() if c.many}
    # The hardened parser strips comments and processing instructions and refuses entity
    # declarations, so every child here is an element.
    for child in element:
        tag = local_name(child)
        child_path = f"{path}/{tag}"
        if (leaf := spec.leaves.get(tag)) is not None:
            if leaf.field in values:
                raise XmlValueError(f"{child_path}: repeated element for a single-valued field")
            values[leaf.field] = _scalar(leaf, child, child_path)
            if (child.text or "").strip():
                report.mapped[child_path] += 1
            if _is_null_text(child):
                report.nulls[child_path] += 1
        elif (sub := spec.children.get(tag)) is not None:
            parsed = parse_model(child, sub.model, child_path, report)
            if sub.many:
                lists[sub.field].append(parsed)
            elif sub.field in values:
                raise XmlValueError(f"{child_path}: repeated element for a single-valued field")
            else:
                values[sub.field] = parsed
        else:
            for leaf_path in _leaf_paths(child, child_path):
                report.unmapped[leaf_path] += 1
    values.update(lists)
    return model.model_validate(values)


def _leaf_paths(element: etree._Element, path: str) -> Iterator[str]:
    children = [c for c in element if isinstance(c.tag, str)]
    if not children:
        yield path
        return
    for child in children:
        yield from _leaf_paths(child, f"{path}/{local_name(child)}")


def source_leaf_counts(root: etree._Element) -> tuple[Counter[str], Counter[str]]:
    """Independent count of non-empty leaf values and null sentinels, straight from the XML.

    Used by the fidelity check to compare against what the parser reports it mapped.
    """
    values: Counter[str] = Counter()
    nulls: Counter[str] = Counter()

    def walk(element: etree._Element, path: str) -> None:
        children = [c for c in element if isinstance(c.tag, str)]
        if not children:
            if (element.text or "").strip():
                values[path] += 1
                if _is_null_text(element):
                    nulls[path] += 1
            return
        for child in children:
            walk(child, f"{path}/{local_name(child)}")

    walk(root, "/" + local_name(root))
    return values, nulls


def model_value_counts(model: BaseModel, path: str) -> Counter[str]:
    """Non-null leaf values held by a parsed model tree, keyed by their XML path."""
    counts: Counter[str] = Counter()
    spec = spec_for(type(model))
    for leaf in spec.leaves.values():
        if getattr(model, leaf.field) is not None:
            counts[f"{path}/{leaf.tag}"] += 1
    for sub in spec.children.values():
        value = getattr(model, sub.field)
        items: list[BaseModel] = value if sub.many else ([] if value is None else [value])
        for item in items:
            counts.update(model_value_counts(item, f"{path}/{sub.tag}"))
    return counts


__all__ = [
    "ParseReport",
    "Xml",
    "XmlValueError",
    "model_value_counts",
    "parse_model",
    "source_leaf_counts",
    "spec_for",
]
