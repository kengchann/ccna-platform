"""Importer exception hierarchy.

Exceptions are reserved for conditions that make the *import run itself*
impossible (unreadable file, unwritable output directory, corrupt bundle).
Problems with individual questions are never raised — they are recorded as
``Issue`` entries on the question and in the import report, per the
"flag, don't fix" rule.
"""


class ImporterError(Exception):
    """Base class for all importer errors."""


class SourceError(ImporterError):
    """The source document cannot be opened or read at all."""


class UnsupportedFormatError(ImporterError):
    """No registered ImportSource can handle the given file."""


class BundleError(ImporterError):
    """An import bundle cannot be written or is structurally invalid."""
