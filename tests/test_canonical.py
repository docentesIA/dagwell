"""Canonicalization scheme c1 (ADR-0003). Zero-cost."""

import re

from dagwell import canonical

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def test_digest_representation():
    assert DIGEST_RE.match(canonical.content_digest("x\n"))


def test_line_endings_normalized():
    assert canonical.content_digest("a\r\nb\r\n") == canonical.content_digest("a\nb\n")
    assert canonical.content_digest("a\rb\r") == canonical.content_digest("a\nb\n")


def test_bom_stripped():
    assert canonical.content_digest("\ufeff" + "x\n") == canonical.content_digest("x\n")


def test_unicode_nfc():
    composed = "caf\u00e9\n"
    decomposed = "cafe\u0301\n"
    assert composed != decomposed
    assert canonical.content_digest(composed) == canonical.content_digest(decomposed)


def test_terminal_newlines_normalized_to_one():
    assert (canonical.content_digest("x")
            == canonical.content_digest("x\n")
            == canonical.content_digest("x\n\n\n"))


def test_per_line_trailing_whitespace_preserved():
    # Markdown hard break: two trailing spaces are semantic
    assert canonical.content_digest("x  \ny\n") != canonical.content_digest("x\ny\n")


def test_bytes_and_str_agree():
    assert canonical.content_digest("café\n".encode()) == canonical.content_digest("café\n")


def test_invalid_utf8_fails_closed():
    try:
        canonical.content_digest(b"\xff\xfe\xfa")
    except UnicodeDecodeError:
        pass
    else:
        raise AssertionError("invalid UTF-8 must fail closed, never raw-hash fallback")


def test_graph_version_and_input_hash_are_content_functions():
    text = "same content\n"
    assert canonical.graph_version(text) == canonical.input_hash(text) \
        == canonical.content_digest(text)


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(vars(sys.modules["__main__"]).items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"test_canonical: {len(fns)} tests PASS")
