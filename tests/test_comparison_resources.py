from __future__ import annotations

from doc_summarizer.comparison_resources import (
    COMPARISON_TEMPLATE_FIELDS,
    load_comparison_profile,
    render_comparison_template,
)


def test_japanese_comparison_profile_is_packaged_and_strict() -> None:
    profile = load_comparison_profile("default-ja")

    assert profile.name == "compare-ja"
    assert profile.source == "package:profiles/compare-ja"
    assert "source-faithful Japanese comparison" in profile.prompt.instructions
    assert "## 2. 共通概念" in profile.template.body
    assert set(profile.schema.value["required"]) == set(profile.schema.value["properties"])
    for definition in profile.schema.value["$defs"].values():
        assert definition["additionalProperties"] is False
        assert set(definition["required"]) == set(definition["properties"])
    assert len(profile.sha256) == 64


def test_english_comparison_profile_and_template_are_packaged() -> None:
    profile = load_comparison_profile("default-en")

    assert profile.name == "compare-en"
    assert "source-faithful English comparison" in profile.prompt.instructions
    assert "## 4. Differences and disagreements" in profile.template.body
    values = {field: field for field in COMPARISON_TEMPLATE_FIELDS}
    rendered = render_comparison_template(profile.template, values)
    assert "{{" not in rendered
    assert rendered.endswith("\n")


def test_claims_profile_has_attribution_instructions_and_source_list() -> None:
    profile = load_comparison_profile(profile_name="claims-ja")
    assert profile.name == "claims-ja"
    assert profile.language_profile == "default-ja"
    assert "Clinical anecdotes remain anecdotes" in profile.prompt.instructions
    assert "{{sources}}" in profile.template.body
    values = {field: field for field in COMPARISON_TEMPLATE_FIELDS} | {"sources": "[S1](a.md)"}
    rendered = render_comparison_template(profile.template, values)
    assert "## 8. 参照した要約ノート" in rendered
    assert "[S1](a.md)" in rendered
