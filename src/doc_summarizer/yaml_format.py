"""Lossless timestamp loading and scalar formatting for YAML metadata."""

from __future__ import annotations

import json
import re
from typing import Any

import yaml


class MetadataLoader(yaml.SafeLoader):
    """Keep timestamp spelling, offsets and fractional precision intact."""


def _timestamp_string(loader: MetadataLoader, node: yaml.ScalarNode) -> str:
    return loader.construct_scalar(node)


MetadataLoader.add_constructor("tag:yaml.org,2002:timestamp", _timestamp_string)


def is_windows_path(value: str) -> bool:
    if "\n" in value or "\r" in value:
        return False
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", value):
        return False
    if re.match(r"^[A-Za-z]:[\\/]", value):
        return True
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value):
        return False
    return "\\" in value or value.startswith("//")


def quote_scalar(value: str) -> str:
    if is_windows_path(value):
        return "'" + value.replace("'", "''") + "'"
    return json.dumps(value, ensure_ascii=False)


def load_metadata(text: str) -> Any:
    return yaml.load(text, Loader=MetadataLoader)


DATE_VALUE = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?"
    r"(?:[Zz]|[+-]\d{2}:\d{2})?)?\Z"
)


def normalize_yaml(text: str, *, rename_date: bool = False) -> str:
    """Edit only scalar tokens, preserving comments, layout and timestamp spelling.

    Refuse ambiguous mappings or conflicting creation fields. Callers handle file
    selection, backups and concurrent-edit checks before persisting the result.
    """
    root = yaml.compose(text, Loader=MetadataLoader)
    if not isinstance(root, yaml.MappingNode):
        raise ValueError("YAML metadata must be a mapping")
    tokens = list(yaml.scan(text))
    edits: dict[tuple[int, int], str] = {}
    seen: set[int] = set()

    def replace_scalar(node: yaml.ScalarNode, replacement: str) -> None:
        scalar_tokens = [
            token
            for token in tokens
            if isinstance(token, yaml.tokens.ScalarToken)
            and node.start_mark.index <= token.start_mark.index
            and token.end_mark.index <= node.end_mark.index
        ]
        if len(scalar_tokens) != 1:
            raise ValueError("cannot safely locate YAML scalar")
        token = scalar_tokens[0]
        edits[token.start_mark.index, token.end_mark.index] = replacement
        for tag in tokens:
            if (
                isinstance(tag, yaml.tokens.TagToken)
                and node.start_mark.index <= tag.start_mark.index
                and tag.end_mark.index <= node.end_mark.index
                and node.tag == "tag:yaml.org,2002:timestamp"
            ):
                edits[tag.start_mark.index, tag.end_mark.index] = ""

    def visit(node: yaml.Node) -> None:
        if id(node) in seen:
            return
        seen.add(id(node))
        if isinstance(node, yaml.MappingNode):
            keys: set[str] = set()
            for key, value in node.value:
                if not isinstance(key, yaml.ScalarNode) or key.value in keys:
                    raise ValueError("duplicate or complex YAML key")
                keys.add(key.value)
                visit(value)
        elif isinstance(node, yaml.SequenceNode):
            for child in node.value:
                visit(child)
        elif isinstance(node, yaml.ScalarNode):
            if node.tag not in ("tag:yaml.org,2002:str", "tag:yaml.org,2002:timestamp"):
                return
            if DATE_VALUE.fullmatch(node.value) or node.tag == "tag:yaml.org,2002:timestamp":
                if node.style != '"' or node.tag == "tag:yaml.org,2002:timestamp":
                    replace_scalar(node, json.dumps(node.value, ensure_ascii=False))
            elif is_windows_path(node.value) and node.style != "'":
                replace_scalar(node, quote_scalar(node.value))

    visit(root)
    keys = {key.value: key for key, _ in root.value}
    if rename_date and "date" in keys:
        if "created" in keys:
            raise ValueError("both date and created exist; manual resolution required")
        replace_scalar(keys["date"], "created")
    result = text
    for (start, end), replacement in sorted(edits.items(), reverse=True):
        result = result[:start] + replacement + result[end:]
    expected = load_metadata(text)
    if rename_date and "date" in expected:
        expected["created"] = expected.pop("date")
    if load_metadata(result) != expected:
        raise ValueError("YAML normalization changed metadata values")
    return result
