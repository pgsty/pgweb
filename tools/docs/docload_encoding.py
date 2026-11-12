"""Encoding decisions used by the PostgreSQL manual loader."""


def document_encoding(version):
    """Return the source encoding for a PostgreSQL manual version.

    PostgreSQL 10 switched the documentation toolchain to UTF-8.  The
    development tree is represented by version ``0`` and uses the same
    encoding.  Older manuals were built with the Latin-1 toolchain.
    """
    version_number = float(version)
    if 0 < version_number < 10:
        return "latin1"
    return "utf-8"


def has_utf8_xml_declaration(rawcontents):
    """Whether *rawcontents* starts with the XML declaration used by newer builds."""
    rawfirst = rawcontents[:50].decode("ascii", errors="ignore")
    return rawfirst.startswith('<?xml version="1.0" encoding="UTF-8"')
