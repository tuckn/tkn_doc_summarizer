"""Load and validate bundled comparison profile resources."""

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

COMPARISON_PROFILES_ROOT = "comparison_profiles"
COMPARISON_TEMPLATE_FIELDS = frozenset(
    {
        "frontmatter",
        "title",
        "cover",
        "summary",
        "common_concepts",
        "perspectives",
        "disagreements",
        "source_specific_insights",
        "technical_terms",
        "conclusion",
    }
)
_PROFILE_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_PLACEHOLDER = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")


@dataclass(frozen=True)
class ComparisonSchema:
    value: dict[str, Any]
    source: str
    sha256: str


@dataclass(frozen=True)
class ComparisonTemplate:
    template_id: str
    version: str
    body: str
    source: str
    sha256: str


@dataclass(frozen=True)
class ComparisonProfile:
    name: str
    language_profile: str
    source: str
    sha256: str
    prompt: SummaryPrompt
    schema: ComparisonSchema
    template: ComparisonTemplate


def _resource_name(profile_name: str, filename: str) -> str:
    if _PROFILE_NAME.fullmatch(profile_name) is None:
        raise RuntimeError(f"invalid built-in comparison profile name: {profile_name}")
    return f"{COMPARISON_PROFILES_ROOT}/{profile_name}/{filename}"


def _resource_bytes(profile_name: str, filename: str, label: str) -> tuple[bytes, str]:
    resource_name = _resource_name(profile_name, filename)
    resource = files("doc_summarizer").joinpath(resource_name)
    try:
        payload = resource.read_bytes()
    except (OSError, FileNotFoundError) as exc:
        raise RuntimeError(f"built-in {label} is unavailable: {resource_name}: {exc}") from exc
    return payload, f"package:doc_summarizer/{resource_name}"


def _validate_strict_object(value: Any, source: str, path: str) -> None:
    if not isinstance(value, dict):
        raise RuntimeError(f"comparison schema object must be a mapping: {source}: {path}")
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
            "comparison schema objects must be strict with every property required: "
            f"{source}: {path}"
        )


def _load_schema(profile_name: str) -> ComparisonSchema:
    payload, source = _resource_bytes(profile_name, "output.schema.json", "comparison schema")
    try:
        value = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid built-in comparison schema {source}: {exc}") from exc
    _validate_strict_object(value, source, "$")
    definitions = value.get("$defs", {})
    if not isinstance(definitions, dict):
        raise RuntimeError(f"comparison schema $defs must be an object: {source}")
    for name, definition in definitions.items():
        if isinstance(definition, dict) and definition.get("type") == "object":
            _validate_strict_object(definition, source, f"$defs.{name}")
    return ComparisonSchema(value=value, source=source, sha256=hashlib.sha256(payload).hexdigest())


def _load_template(profile_name: str) -> ComparisonTemplate:
    payload, source = _resource_bytes(profile_name, "template.md", "comparison template")
    try:
        text = payload.decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"comparison template must be UTF-8: {source}: {exc}") from exc
    if not text.startswith("---\n"):
        raise RuntimeError(f"comparison template must start with YAML frontmatter: {source}")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise RuntimeError(f"comparison template frontmatter is incomplete: {source}")
    try:
        metadata = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        raise RuntimeError(f"invalid comparison template frontmatter {source}: {exc}") from exc
    if not isinstance(metadata, dict) or metadata.get("type") != "template":
        raise RuntimeError(f"comparison template type must be 'template': {source}")
    try:
        template_id = str(uuid.UUID(str(metadata.get("id"))))
    except (ValueError, AttributeError) as exc:
        raise RuntimeError(f"comparison template id must be a UUID: {source}") from exc
    version = metadata.get("version")
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError(f"comparison template version must be a quoted string: {source}")
    body = text[end + 5 :].strip()
    placeholders = _PLACEHOLDER.findall(body)
    if set(placeholders) != COMPARISON_TEMPLATE_FIELDS or any(
        placeholders.count(field) != 1 for field in COMPARISON_TEMPLATE_FIELDS
    ):
        expected = ", ".join(sorted(COMPARISON_TEMPLATE_FIELDS))
        raise RuntimeError(
            "comparison template must contain each required placeholder exactly once "
            f"({expected}): {source}"
        )
    return ComparisonTemplate(
        template_id=template_id,
        version=version.strip(),
        body=body,
        source=source,
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def load_comparison_profile(
    language_profile: str = DEFAULT_SUMMARY_PROFILE,
) -> ComparisonProfile:
    prompt_payload, prompt_source = _resource_bytes(
        language_profile, "prompt.md", "comparison prompt"
    )
    prompt = parse_summary_prompt(prompt_payload, prompt_source, "built-in")
    schema = _load_schema(language_profile)
    template = _load_template(language_profile)
    name = "compare-ja" if language_profile == "default-ja" else "compare-en"
    source = f"package:doc_summarizer/{COMPARISON_PROFILES_ROOT}/{language_profile}"
    identity = json.dumps(
        {
            "name": name,
            "promptSha256": prompt.sha256,
            "schemaSha256": schema.sha256,
            "templateSha256": template.sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return ComparisonProfile(
        name=name,
        language_profile=language_profile,
        source=source,
        sha256=hashlib.sha256(identity).hexdigest(),
        prompt=prompt,
        schema=schema,
        template=template,
    )


def render_comparison_template(template: ComparisonTemplate, values: dict[str, str]) -> str:
    if set(values) != COMPARISON_TEMPLATE_FIELDS:
        missing = sorted(COMPARISON_TEMPLATE_FIELDS - set(values))
        extra = sorted(set(values) - COMPARISON_TEMPLATE_FIELDS)
        raise ValueError(f"invalid comparison template values: missing={missing}; extra={extra}")
    rendered = template.body
    for field in COMPARISON_TEMPLATE_FIELDS:
        rendered = rendered.replace(f"{{{{{field}}}}}", values[field])
    if _PLACEHOLDER.search(rendered):
        raise ValueError("comparison template contains unresolved placeholders")
    return rendered.rstrip() + "\n"
