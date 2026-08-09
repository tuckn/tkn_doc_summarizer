# tkn-doc-summarizer

[日本語](README_ja.md)

`tkn-doc-summarizer` creates a source-faithful Markdown summary from a local text
document or an article previously saved as Markdown by a browser clipper. A URL
input is a lookup key for a local clipped note; this application does not fetch
the web page itself.

Source files are never copied, edited, moved, or deleted. The only content
artifact created by `summarize` or `synthesize` is the summary Markdown note.

## Requirements

- Windows 11 is the primary environment; portable code also supports Linux.
- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/)
- An installed and authenticated `codex` CLI for real summary generation
- For URL input, a complete local Markdown clip with a Frontmatter `url`

## Install

For normal use, replace the example path with the actual path to this repository,
then install the CLI from the repository root:

```console
cd "C:\path\to\tkn_doc_summarizer"
uv tool install .
tkn-doc-summarizer --help
```

This normal installation captures the code, package resources, and dependencies
at installation time. After updating the repository with `git pull` or another
method, reinstall the tool to apply those changes:

```console
cd "C:\path\to\tkn_doc_summarizer"
uv tool install . --reinstall
tkn-doc-summarizer --help
```

Use `--force` only when the tool itself must be forcibly installed, such as when
resolving an executable entry-point conflict.

### Editable installation for development

For development, use an editable installation when source changes should be
reflected immediately:

```console
cd "C:\path\to\tkn_doc_summarizer"
uv tool install -e . --reinstall
```

Ordinary source-code changes do not require reinstalling an editable
installation. Re-run the same command after changing dependencies, package
metadata, or the CLI entry point, or after moving or renaming the repository.

## Initial configuration

Copy `.tkn/config.example.yaml` to either:

- `~/.tkn/doc_summarizer/config.yaml` for normal user-wide settings, or
- `./.tkn/config.yaml` for the current working directory only.

Set `source_roots` to one or more folders containing Web Clipper Markdown files.
File-path input works without `source_roots`.

```yaml
source_roots:
  - C:\Users\ExampleUser\Documents\Obsidian\WebClips
output_root: ~/.tkn/doc_summarizer/data/summaries
reports_root: ~/.tkn/doc_summarizer/state/reports
model: null
summary_profile: default-ja
```

The real `./.tkn/config.yaml` is ignored by Git. The application does not create
directories while running `config show`.

## Basic usage

Summarize a clipped Markdown file:

```console
tkn-doc-summarizer summarize "C:\path\to\clipped-article.md"
```

Generate an English note for the same source with a one-run override:

```console
tkn-doc-summarizer summarize "C:\path\to\clipped-article.md" --summary-profile default-en
```

Summarize the same local clip by its original URL:

```console
tkn-doc-summarizer summarize "https://example.com/article"
```

The URL command recursively searches `source_roots`, parses Markdown
Frontmatter, and requires exactly one normalized `url` match. If there is no
match, first save a complete copy with Obsidian Web Clipper or pass the file
path. It intentionally performs no HTTP request.

Preview source resolution and the output path without running Codex or writing
anything:

```console
tkn-doc-summarizer summarize "https://example.com/article" --dry-run
```

Choose one exact output path:

```console
tkn-doc-summarizer summarize "C:\path\to\facts.md" --output "C:\path\to\summary.md"
```

To summarize consecutive pages as one logical article, list them in page order:

```console
tkn-doc-summarizer synthesize "C:\path\to\page-1.md" "C:\path\to\page-2.md" --title "Complete example article" --dry-run
tkn-doc-summarizer synthesize "C:\path\to\page-1.md" "C:\path\to\page-2.md" --title "Complete example article"
```

Each source may be a local path or a clipped article URL resolved locally
through `source_roots`. `--title` is optional and defaults to the first source's
title.

## Commands

### `summarize SOURCE`

Purpose: resolve one UTF-8 local source, invoke Codex with a structured JSON
schema, validate the generated Markdown, and atomically write one summary note.

- `SOURCE`: a local file path, or an HTTP(S) URL present in clipped Frontmatter.
- `--dry-run`: resolves and validates source/target only. It does not invoke
  Codex and writes no output, report, state, or cache.
- `--output FILE`: uses an exact `.md` destination.
- `--output-root DIR`: overrides the configured automatically named destination.
- `--source-root DIR`: overrides URL search roots; repeat for multiple roots.
- `--summary-profile PROFILE`: selects `default-ja` or `default-en` for this run.
- `--summary-prompt FILE`: selects custom Markdown instructions.
- `--model MODEL`: selects a Codex model for this run.
- `--overwrite`: regenerates the matching summary when source, prompt, or model
  changed. It can replace manual and reviewed edits and resets `reviewStatus` to
  `unreviewed`.

Without `--overwrite`, a current, valid summary returns `unchanged` without
calling Codex. A stale, invalid, or different existing output is not replaced.
Even with `--overwrite`, the application refuses to replace a file belonging to
another source, summary profile, or prompt. Different profiles create separate
notes and can coexist for the same source.

Success is confirmed by final JSON with `created`, `updated`, or `unchanged`,
the summary path, source path, validation details, and run-report path.

### `synthesize SOURCE SOURCE [...]`

Purpose: create one integrated series summary from at least two sources listed
in page order. The order is exactly the CLI argument order; it is never inferred
from filenames or URLs. Repeated page furniture is omitted while cross-page
reasoning and later qualifications are preserved. Source identifiers `S1`,
`S2`, and so on are assigned automatically.

`--dry-run`, `--output`, `--output-root`, `--source-root`,
`--summary-profile`, `--summary-prompt`, `--model`, and `--overwrite` follow the
same write-safety rules as `summarize`. The total raw input is also limited by
`max_total_input_bytes`. Duplicate entries resolving to the same local file are
rejected. `--title TITLE` sets the combined article title; when omitted, the
first source title is used.

Generated schema 6.0 Frontmatter records an automatically generated stable
source-set UUID, mode, ordered local source URIs, every source SHA-256, and a
canonical `sourceSetSha256`. The UUID is derived from the ordered resolved local
URIs, while content changes are detected by `sourceSetSha256`. Changed source
content requires explicit `--overwrite`, and reviewed output is never silently
replaced.

### `validate PATH`

Validates the output schema, Frontmatter order and provenance, section
structure, review status, and either the single source or every ordered series
source and its SHA-256. Series validation also recalculates `sourceSetSha256`.

```console
tkn-doc-summarizer validate "C:\path\to\summary.md"
```

It is read-only. JSON reports `valid: true` on success; the process exits nonzero
when validation fails.

### `config show`

Displays all resolved non-secret values, the configuration files read, the
source of each setting, and built-in/custom prompt provenance.

```console
tkn-doc-summarizer config show
```

It does not create application directories or invoke Codex.

### `prompt init [NAME]`

Creates an editable copy of the built-in prompt under
`~/.tkn/doc_summarizer/prompts/`. Each copy receives a new UUID. Existing files
are never replaced, and the command does not change configuration.

```console
tkn-doc-summarizer prompt init my-summary.md
tkn-doc-summarizer prompt init my-english-summary.md --summary-profile default-en
```

Set `summary_prompt: my-summary.md` in configuration or pass
`--summary-prompt` to use it. Custom prompt files must be UTF-8 Markdown with:

```markdown
---
type: prompt
id: 00000000-0000-4000-8000-000000000000
version: "1.0"
---

Your instructions...
```

Application-managed prompt-injection protection and source metadata/content
delimiters remain outside editable instructions. A custom prompt replaces only
the prompt in the selected profile; its language-specific schema and template
remain active.

## Output and storage

Default locations:

```text
~/.tkn/doc_summarizer/
├── config.yaml
├── data/
│   └── summaries/<year>/<date>_<title>_<profile>_<prompt-id-prefix>.md
├── prompts/
└── state/
    └── reports/<run-id>.json
```

Temporary Codex schema/output files use the platform temporary directory and
are removed after execution. The repository root is not used for runtime data.

`default-ja` is the default and generates Japanese content with Japanese H2
section headings; its Summary is normally one paragraph of about 250–400
characters. `default-en` generates English content with English H2 section
headings; its Summary is normally about 120–200 words. Both profiles use H3
major sections, H4 subsections, concise bullets, roughly 5–8 Key points, and
roughly 3–7 neutral, reusable Technical-term definitions. When the source has a
`cover`, it is shown directly below the title.

The Japanese headings are `要約`, `構造化（抽象から具体へ）`, `重要ポイント`,
`専門用語`, and `結論`; the English equivalents are `Summary`, `Structuring
(from abstract to concrete)`, `Key points`, `Technical terms`, and `Conclusion`.

Frontmatter records `type: summary`, the local source URI, source SHA-256,
generator/effective model, prompt ID/version/SHA-256, summary-profile and output
schema hashes, template ID/version/hash, prompt envelope version, review state,
dates, and stable note UUID. Classification metadata such as `nouns` is
intentionally left to a separate CLI. The source body is not copied into the
summary.

`schemaVersion` and `promptVersion` are quoted YAML strings, for example
`schemaVersion: "5.0"` and `promptVersion: "2.0"`. They are version identifiers,
not decimal quantities. Keeping them as strings preserves values such as
`2.0`, `2.10`, or a future semantic version without YAML converting them to
floating-point numbers.

## Configuration

Precedence, from lowest to highest:

1. built-in defaults
2. `~/.tkn/doc_summarizer/config.yaml`
3. `./.tkn/config.yaml`
4. `--config FILE`
5. individual CLI options

Relative paths resolve from the current working directory. Unknown keys,
invalid types, missing explicit config files, invalid prompts, unreadable
sources, and unsupported providers fail closed.

| Key | Default | Meaning |
| --- | --- | --- |
| `source_roots` | `[]` | Markdown roots searched for URL input |
| `output_root` | user data summaries | Automatic summary destination |
| `reports_root` | user state reports | JSON run reports |
| `provider` | `codex` | Generation adapter; v1 supports Codex |
| `model` | `null` | Codex default model, unless explicitly set |
| `codex_executable` | `codex` | Executable or shim name |
| `codex_timeout_seconds` | `1800` | Generation timeout |
| `max_input_bytes` | `2000000` | Maximum UTF-8 source file size |
| `max_total_input_bytes` | `8000000` | Maximum total source bytes for one source set |
| `summary_profile` | `default-ja` | Built-in language/profile: `default-ja` or `default-en` |
| `summary_prompt` | `null` | Selected profile's prompt, user prompt filename, or absolute path |

## Logs and automation

Progress and diagnostics go to stderr:

```text
[DEBUG] detailed diagnostics
[INFO] normal progress
[SUCCESS] final successful outcome
[WARNING] completed/continuing state needing attention
[ERROR] command failure
```

`--quiet` shows errors only. `--verbose` adds debug diagnostics; the two options
are mutually exclusive. Interactive terminals color success green and errors
red when ANSI color is supported. Redirected output, `NO_COLOR`, `TERM=dumb`,
or unsupported Windows terminals automatically use plain text.

The final result is one JSON object on stdout. Normal success exits `0`;
configuration, source, generation, collision, or validation failures exit
nonzero.

## Safety and limitations

- The application does not acquire web content. Clipper completeness must be
  checked before summarization.
- Input is treated as untrusted content. Embedded prompt-like instructions are
  not followed.
- The source file is read-only and is never included verbatim in the output.
- Output is fully rendered and deterministically validated before atomic commit.
- A real generation can still contain semantic mistakes. Review the note and
  change `reviewStatus` according to your Vault workflow.
- `--overwrite` replaces manual edits in the generated note. Keep it explicit.
- UTF-8 text files are supported. Binary files and files over
  `max_input_bytes` are rejected.

## Development and verification

### Summary profiles

The resources that jointly define summary generation are bundled as one
application-owned profile:

```text
src/doc_summarizer/summary_profiles/
├── default-ja/
│   ├── prompt.md
│   ├── output.schema.json
│   └── template.md
└── default-en/
    ├── prompt.md
    ├── output.schema.json
    └── template.md
```

`prompt.md` defines the editorial policy and field meanings,
`output.schema.json` is the structured JSON contract passed to Codex, and
`template.md` defines the deterministic Markdown layout. The loader validates
all three and computes a profile SHA-256 from their individual hashes. This
profile hash participates in idempotency, so changing the schema or template
cannot leave an older note incorrectly classified as current.
`config show` reports the active profile and each resource's provenance.

Select a profile with `summary_profile` in YAML or `--summary-profile` on the
CLI; CLI selection has normal highest precedence. Custom prompts remain
supported. They replace only the selected profile's `prompt.md` and are combined
with that profile's schema and template into a separately fingerprinted profile.
Coordinate field changes across the prompt,
schema, Pydantic models, renderer, validation, and tests; coordinate layout
changes across the template, renderer, validation, and tests.

Existing schema 2.0 through 4.0 notes remain accepted by `validate`. New
profile-aware filenames and identity allow Japanese and English schema 5.0 notes
for one source to coexist without overwriting an older note.

```console
uv sync --locked
uv run pytest
uv run ruff check .
uv run mypy src
uv build
```

Build/test artifacts should use the normal cache or platform temporary
directories; do not create repository-root runtime data.
