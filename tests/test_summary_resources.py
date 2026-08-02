from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from doc_summarizer.models import SummaryDocument
from doc_summarizer.prompting import load_summary_prompt
from doc_summarizer.summary_resources import (
    REQUIRED_TEMPLATE_FIELDS,
    load_summary_profile,
    render_summary_template,
)


def _without_descriptions(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _without_descriptions(item) for key, item in value.items() if key != "description"
        }
    if isinstance(value, list):
        return [_without_descriptions(item) for item in value]
    return deepcopy(value)


def test_default_japanese_summary_profile_is_packaged_and_coherent() -> None:
    profile = load_summary_profile()

    assert profile.name == "default-ja"
    assert profile.source.endswith("summary_profiles/default-ja")
    assert profile.prompt.source.endswith("summary_profiles/default-ja/prompt.md")
    assert profile.schema.source.endswith("summary_profiles/default-ja/output.schema.json")
    assert profile.template.source.endswith("summary_profiles/default-ja/template.md")
    assert "Japanese paragraph" in profile.schema.value["properties"]["summary"]["description"]
    assert "## 1. 要約" in profile.template.body
    assert _without_descriptions(profile.schema.value) == _without_descriptions(
        SummaryDocument.model_json_schema()
    )
    assert len(profile.sha256) == 64
    assert len(profile.schema.sha256) == 64
    assert len(profile.template.sha256) == 64


def test_english_summary_profile_is_packaged_and_language_specific() -> None:
    profile = load_summary_profile("default-en")

    assert profile.name == "default-en"
    assert "English summary" in profile.prompt.instructions
    assert "English paragraph" in profile.schema.value["properties"]["summary"]["description"]
    assert "## 1. Summary" in profile.template.body
    assert _without_descriptions(profile.schema.value) == _without_descriptions(
        SummaryDocument.model_json_schema()
    )
    assert profile.prompt.prompt_id != load_summary_profile("default-ja").prompt.prompt_id


def test_custom_prompt_participates_in_profile_identity(tmp_path: Path) -> None:
    default = load_summary_profile()
    custom_path = tmp_path / "custom.md"
    custom_path.write_text(
        "---\n"
        "type: prompt\n"
        "id: f5dfc679-13d3-4fcc-9736-b7d4e6bb5c11\n"
        'version: "1.0"\n'
        "---\n\n"
        "Custom instructions.\n",
        encoding="utf-8",
    )

    custom = load_summary_profile("default-ja", prompt=load_summary_prompt(custom_path))

    assert custom.prompt.mode == "custom"
    assert custom.schema == default.schema
    assert custom.template == default.template
    assert custom.sha256 != default.sha256


def test_custom_prompt_uses_selected_profile_schema_and_template(tmp_path: Path) -> None:
    custom_path = tmp_path / "custom.md"
    custom_path.write_text(
        "---\n"
        "type: prompt\n"
        "id: e46b50fb-cdc8-43fd-947a-c98b7d41d080\n"
        'version: "1.0"\n'
        "---\n\n"
        "Custom English instructions.\n",
        encoding="utf-8",
    )

    profile = load_summary_profile("default-en", prompt=load_summary_prompt(custom_path))

    assert profile.prompt.mode == "custom"
    assert "English paragraph" in profile.schema.value["properties"]["summary"]["description"]
    assert "## 1. Summary" in profile.template.body


def test_summary_template_requires_exact_values() -> None:
    template = load_summary_profile().template
    values = {field: field for field in REQUIRED_TEMPLATE_FIELDS}

    rendered = render_summary_template(template, values)

    assert "{{" not in rendered
    assert rendered.endswith("\n")
