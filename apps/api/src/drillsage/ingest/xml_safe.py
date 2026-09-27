"""Hardened XML parsing.

External entities, network access and DTD loading are disabled. Documents carrying a DOCTYPE
are rejected outright: no legitimate WITSML file needs one, and refusing them removes the
entity-expansion attack surface instead of relying on parser limits.
"""

from typing import Final

from lxml import etree

from drillsage.core.errors import InvalidInputError

MAX_XML_BYTES: Final = 32 * 1024 * 1024


class UnsafeXmlError(InvalidInputError):
    slug = "unsafe-xml"


class MalformedXmlError(InvalidInputError):
    slug = "malformed-xml"


def _parser() -> etree.XMLParser:
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
        remove_comments=True,
        remove_pis=True,
    )


def parse_xml(data: bytes) -> etree._Element:
    """Parse untrusted XML bytes and return the root element."""
    if len(data) > MAX_XML_BYTES:
        raise UnsafeXmlError(f"XML document exceeds {MAX_XML_BYTES} bytes")
    head = data[:4096].lstrip()
    if b"<!DOCTYPE" in head.upper() or b"<!ENTITY" in data.upper():
        raise UnsafeXmlError("XML documents with a DOCTYPE or ENTITY declaration are refused")
    try:
        root = etree.fromstring(data, parser=_parser())
    except etree.XMLSyntaxError as exc:
        raise MalformedXmlError(f"malformed XML: {exc}") from exc
    if root.getroottree().docinfo.internalDTD is not None:
        raise UnsafeXmlError("XML documents with a DOCTYPE are refused")
    return root


def local_name(element: etree._Element) -> str:
    return etree.QName(element).localname
