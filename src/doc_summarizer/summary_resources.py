"""Load and validate bundled document-summary profile resources."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

import yaml

from doc_summarizer.config import DEFAULT_SUMMARY_PROFILE
from doc_summarizer.prompting import SummaryPrompt, parse_summary_prompt

SUMMARY_PROFILES_ROOT = "summary_profiles"
PROMPT_FILENAME = "prompt.md"
SCHEMA_FILENAME = "output.schema.json"
TEMPLATE_FILENAME = "template.md"
REQUIRED_TEMPLATE_FIELDS = frozenset(
    {
        "frontmatter",
        "title",
        "cover",
        "summary",
        "structuring",
        "key_points",
        "technical_terms",
        "conclusion",
    }
)
_PROFILE_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_PLACEHOLDER = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")


@dataclass(frozen=True)
class SummarySchema:
    value: dict[str, Any]
    source: str
    sha256: str


@dataclass(frozen=True)
class SummaryTemplate:
    template_id: str
    version: str
    body: str
    source: str
    sha256: str


@dataclass(frozen=True)
class SummaryProfile:
    name: str
    source: str
    sha256: str
    prompt: SummaryPrompt
    schema: SummarySchema
    template: SummaryTemplate


def _profile_resource_name(profile_name: str, filename: str) -> str:
    if _PROFILE_NAME.fullmatch(profile_name) is None:
        raise RuntimeError(f"invalid built-in summary profile name: {profile_name}")
    return f"{SUMMARY_PROFILES_ROOT}/{profile_name}/{filename}"


def _resource_bytes(resource_name: str, label: str) -> bytes:
    resource = files("doc_summarizer").joinpath(resource_name)
    try:
        return resource.read_bytes()
    except (OSError, FileNotFoundError) as exc:
        raise RuntimeError(f"built-in {label} is unavailable: {resource_name}: {exc}") from exc


def _load_profile_prompt(profile_name: str) -> SummaryPrompt:
    resource_name = _profile_resource_name(profile_name, PROMPT_FILENAME)
    payload = _resource_bytes(resource_name, "summary profile prompt")
    source = f"package:doc_summarizer/{resource_name}"
    return parse_summary_prompt(payload, source, "built-in")


def _validate_strict_schema_object(value: Any, source: str, path: str) -> None:
    if not isinstance(value, dict):
        raise RuntimeError(f"built-in summary schema object must be a mapping: {source}: {path}")
    properties = value.get("properties")
    required = value.get("required")
    if (
        value.get("type") != "object"
        or value.get("additionalProperties") is not False
        or not isinstance(properties, dict)
        or not isinstance(required, list)
        or set(required) != set(properties)
    ):
        raise RuntimeError(
            "built-in summary schema objects must be strict with every property required: "
            f"{source}: {path}"
        )


def load_summary_schema(
    profile_name: str = DEFAULT_SUMMARY_PROFILE,
) -> SummarySchema:
    resource_name = _profile_resource_name(profile_name, SCHEMA_FILENAME)
    payload = _resource_bytes(resource_name, "summary profile schema")
    source = f"package:doc_summarizer/{resource_name}"
    try:
        value = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid built-in summary schema {source}: {exc}") from exc
    _validate_strict_schema_object(value, source, "$")
    definitions = value.get("$defs", {})
    if not isinstance(definitions, dict):
        raise RuntimeError(f"built-in summary schema $defs must be an object: {source}")
    for name, definition in definitions.items():
        if not isinstance(definition, dict):
            raise RuntimeError(
                f"built-in summary schema definition must be an object: {source}: $defs.{name}"
            )
        if definition.get("type") == "object":
            _validate_strict_schema_object(definition, source, f"$defs.{name}")
    return SummarySchema(
        value=value,
        source=source,
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def load_summary_template(
    profile_name: str = DEFAULT_SUMMARY_PROFILE,
) -> SummaryTemplate:
    resource_name = _profile_resource_name(profile_name, TEMPLATE_FILENAME)
    payload = _resource_bytes(resource_name, "summary profile template")
    source = f"package:doc_summarizer/{resource_name}"
    try:
        text = payload.decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"summary template must be UTF-8: {source}: {exc}") from exc
    if not text.startswith("---\n"):
        raise RuntimeError(f"summary template must start with YAML frontmatter: {source}")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise RuntimeError(f"summary template frontmatter closing delimiter is missing: {source}")
    try:
        metadata = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        raise RuntimeError(f"invalid summary template frontmatter {source}: {exc}") from exc
    if not isinstance(metadata, dict) or metadata.get("type") != "template":
        raise RuntimeError(f"summary template type must be 'template': {source}")
    try:
        template_id = str(uuid.UUID(str(metadata.get("id"))))
    except (ValueError, AttributeError) as exc:
        raise RuntimeError(f"summary template id must be a UUID: {source}") from exc
    version = metadata.get("version")
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError(f"summary template version must be a non-empty quoted string: {source}")
    body = text[end + 5 :].strip()
    placeholders = _PLACEHOLDER.findall(body)
    if set(placeholders) != REQUIRED_TEMPLATE_FIELDS or any(
        placeholders.count(field) != 1 for field in REQUIRED_TEMPLATE_FIELDS
    ):
        expected = ", ".join(sorted(REQUIRED_TEMPLATE_FIELDS))
        raise RuntimeError(
            "summary template must contain each required placeholder exactly once "
            f"({expected}): {source}"
        )
    return SummaryTemplate(
        template_id=template_id,
        version=version.strip(),
        body=body,
        source=source,
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def load_summary_profile(
    profile_name: str = DEFAULT_SUMMARY_PROFILE,
    *,
    prompt: SummaryPrompt | None = None,
) -> SummaryProfile:
    active_prompt = prompt or _load_profile_prompt(profile_name)
    schema = load_summary_schema(profile_name)
    template = load_summary_template(profile_name)
    source = f"package:doc_summarizer/{SUMMARY_PROFILES_ROOT}/{profile_name}"
    identity = json.dumps(
        {
            "name": profile_name,
            "promptSha256": active_prompt.sha256,
            "schemaSha256": schema.sha256,
            "templateSha256": template.sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return SummaryProfile(
        name=profile_name,
        source=source,
        sha256=hashlib.sha256(identity).hexdigest(),
        prompt=active_prompt,
        schema=schema,
        template=template,
    )


def render_summary_template(template: SummaryTemplate, values: dict[str, str]) -> str:
    if set(values) != REQUIRED_TEMPLATE_FIELDS:
        missing = sorted(REQUIRED_TEMPLATE_FIELDS - set(values))
        extra = sorted(set(values) - REQUIRED_TEMPLATE_FIELDS)
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if extra:
            details.append("extra=" + ",".join(extra))
        raise ValueError("invalid summary template values: " + "; ".join(details))
    rendered = template.body
    for field in REQUIRED_TEMPLATE_FIELDS:
        rendered = rendered.replace(f"{{{{{field}}}}}", values[field])
    if _PLACEHOLDER.search(rendered):
        raise ValueError("summary template contains unresolved placeholders")
    return rendered.rstrip() + "\n"
