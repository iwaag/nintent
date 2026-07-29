"""Django-free YAML decoding shared by the desired-state batch API parsers."""

from __future__ import annotations

from typing import Any

import yaml


YAML_MEDIA_TYPES = ("application/yaml", "text/yaml", "application/x-yaml")


class YAMLDocumentError(ValueError):
    """The request body is not a valid YAML object document."""


def load_yaml_document(payload: str | bytes) -> dict[str, Any]:
    """Safely decode one YAML mapping without assigning HTTP semantics."""
    try:
        document = yaml.safe_load(payload)
    except yaml.YAMLError as exc:
        raise YAMLDocumentError(f"Malformed YAML: {exc}") from exc
    if not isinstance(document, dict):
        raise YAMLDocumentError("YAML document must be an object")
    return document
