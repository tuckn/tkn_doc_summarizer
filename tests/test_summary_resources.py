from __future__ import annotations

from pathlib import Path

from doc_summarizer.models import SummaryDocument
from doc_summarizer.prompting import load_summary_prompt
from doc_summarizer.summary_resources import (
    REQUIRED_TEMPLATE_FIELDS,
    load_summary_profile,
    render_summary_template,
)


def test_default_summary_profile_is_packaged_and_coherent() -> None:
    profile = load_summary_profile()

    assert profile.name == "default"
    assert profile.source.endswith("summary_profiles/default")
    assert profile.prompt.source.endswith("summary_profiles/default/prompt.md")
    assert profile.schema.source.endswith("summary_profiles/default/output.schema.json")
    assert profile.template.source.endswith("summary_profiles/default/template.md")
    assert profile.schema.value == SummaryDocument.model_json_schema()
    assert len(profile.sha256) == 64
    assert len(profile.schema.sha256) == 64
    assert len(profile.template.sha256) == 64


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

    custom = load_summary_profile(prompt=load_summary_prompt(custom_path))

    assert custom.prompt.mode == "custom"
    assert custom.schema == default.schema
    assert custom.template == default.template
    assert custom.sha256 != default.sha256


def test_summary_template_requires_exact_values() -> None:
    template = load_summary_profile().template
    values = {field: field for field in REQUIRED_TEMPLATE_FIELDS}

    rendered = render_summary_template(template, values)

    assert "{{" not in rendered
    assert rendered.endswith("\n")
