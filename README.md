# tkn-doc-summarizer

[日本語](README_ja.md)

`doc-summarizer` creates a source-faithful Markdown summary from a local text
document or an article previously saved as Markdown by a browser clipper. A URL
input is a lookup key for a local clipped note; this application does not fetch
the web page itself.

The source file is never copied, edited, moved, or deleted. The only content
artifact created by `summarize` is the summary Markdown note.

## Requirements

- Windows 11 is the primary environment; portable code also supports Linux.
- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/)
- An installed and authenticated `codex` CLI for real summary generation
- For URL input, a complete local Markdown clip with a Frontmatter `url`

## Install

From the repository root:

```console
uv tool install -e .
doc-summarizer --help
doc-summarizer config show
```

Reinstall with `--force` after changing dependencies, package metadata, the CLI
entry point, or the repository location:

```console
uv tool install -e . --force
```

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
```

The real `./.tkn/config.yaml` is ignored by Git. The application does not create
directories while running `config show`.

## Basic usage

Summarize a clipped Markdown file:

```console
doc-summarizer summarize "C:\path\to\clipped-article.md"
```

Summarize the same local clip by its original URL:

```console
doc-summarizer summarize "https://example.com/article"
```

The URL command recursively searches `source_roots`, parses Markdown
Frontmatter, and requires exactly one normalized `url` match. If there is no
match, first save a complete copy with Obsidian Web Clipper or pass the file
path. It intentionally performs no HTTP request.

Preview source resolution and the output path without running Codex or writing
anything:

```console
doc-summarizer summarize "https://example.com/article" --dry-run
```

Choose one exact output path:

```console
doc-summarizer summarize "C:\path\to\facts.md" --output "C:\path\to\summary.md"
```

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
- `--summary-prompt FILE`: selects custom Markdown instructions.
- `--model MODEL`: selects a Codex model for this run.
- `--overwrite`: regenerates the matching summary when source, prompt, or model
  changed. It can replace manual and reviewed edits and resets `reviewStatus` to
  `unreviewed`.

Without `--overwrite`, a current, valid summary returns `unchanged` without
calling Codex. A stale, invalid, or different existing output is not replaced.
Even with `--overwrite`, the application refuses to replace a file belonging to
another source or prompt.

Success is confirmed by final JSON with `created`, `updated`, or `unchanged`,
the summary path, source path, validation details, and run-report path.

### `validate PATH`

Validates the output schema, Frontmatter order and provenance, section
structure, review status, source file reference, and source SHA-256.

```console
doc-summarizer validate "C:\path\to\summary.md"
```

It is read-only. JSON reports `valid: true` on success; the process exits nonzero
when validation fails.

### `config show`

Displays all resolved non-secret values, the configuration files read, the
source of each setting, and built-in/custom prompt provenance.

```console
doc-summarizer config show
```

It does not create application directories or invoke Codex.

### `prompt init [NAME]`

Creates an editable copy of the built-in prompt under
`~/.tkn/doc_summarizer/prompts/`. Each copy receives a new UUID. Existing files
are never replaced, and the command does not change configuration.

```console
doc-summarizer prompt init my-summary.md
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

Application-managed prompt-injection protection, source metadata/content
delimiters, and the JSON output schema remain outside editable instructions.

## Output and storage

Default locations:

```text
~/.tkn/doc_summarizer/
├── config.yaml
├── data/
│   └── summaries/<year>/<date>_<title>_<prompt-id-prefix>.md
├── prompts/
└── state/
    └── reports/<run-id>.json
```

Temporary Codex schema/output files use the platform temporary directory and
are removed after execution. The repository root is not used for runtime data.

Generated notes follow the reference layout. When the source has a `cover`, it
is shown directly below the title. Summary is normally one Japanese paragraph
of about 250–400 characters. Structuring normally uses H3 major sections, H4
subsections, and concise bullets. Key points are narrowed to roughly 5–8 major
items, and Technical terms to roughly 3–7 neutral, reusable definitions.

1. Summary
2. Structuring (from abstract to concrete)
3. Key points
4. Technical terms
5. Conclusion

Frontmatter records `type: summary`, the local source URI, source SHA-256,
generator/effective model, prompt ID/version/SHA-256, prompt envelope version,
review state, dates, and stable note UUID. Classification metadata such as
`nouns` is intentionally left to a separate CLI. The source body is not copied
into the summary.

`schemaVersion` and `promptVersion` are quoted YAML strings, for example
`schemaVersion: "3.0"` and `promptVersion: "2.0"`. They are version identifiers,
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
| `summary_prompt` | `null` | Built-in prompt, user prompt filename, or absolute path |

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

```console
uv sync --locked
uv run pytest
uv run ruff check .
uv run mypy src
uv build
```

Build/test artifacts should use the normal cache or platform temporary
directories; do not create repository-root runtime data.
