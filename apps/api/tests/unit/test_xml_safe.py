import pytest

from drillsage.ingest import xml_safe
from drillsage.ingest.xml_safe import MalformedXmlError, UnsafeXmlError, parse_xml

XXE = b"""<?xml version="1.0"?>
<!DOCTYPE r [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<r>&xxe;</r>"""

BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
]>
<lolz>&lol2;</lolz>"""

ENTITY_ONLY = b"<r><!ENTITY x 'y'></r>"
LOWERCASE_DOCTYPE = b"<?xml version='1.0'?><!doctype r><r/>"


@pytest.mark.parametrize("payload", [XXE, BILLION_LAUGHS, ENTITY_ONLY, LOWERCASE_DOCTYPE])
def test_documents_with_dtds_or_entities_are_refused(payload: bytes) -> None:
    with pytest.raises(UnsafeXmlError):
        parse_xml(payload)


def test_malformed_xml() -> None:
    with pytest.raises(MalformedXmlError):
        parse_xml(b"<r><unclosed></r>")


def test_oversized_document(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(xml_safe, "MAX_XML_BYTES", 10)
    with pytest.raises(UnsafeXmlError, match="exceeds"):
        parse_xml(b"<r>0123456789</r>")


def test_comments_and_processing_instructions_are_stripped() -> None:
    root = parse_xml(b"<r><!-- note --><?pi x?><a>1</a></r>")
    assert [xml_safe.local_name(c) for c in root] == ["a"]
