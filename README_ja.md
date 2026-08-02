# tkn-doc-summarizer

[English](README.md)

`doc-summarizer` は、ローカルのテキスト文書、またはブラウザ拡張で事前に
Markdown保存したWeb記事から、ソースに忠実な要約Markdownノートを作るCLIです。
URLはローカルにあるクリップ済みノートを特定する検索キーとして使い、このCLI自身は
Webページを取得しません。

入力ファイルの複製、編集、移動、削除は行いません。`summarize` が作る内容成果物は、
要約Markdownノート1つだけです。

## 必要環境

- 主対象はWindows 11。OS固有でない処理はLinuxでも動作します。
- Python 3.11以上
- [uv](https://docs.astral.sh/uv/)
- 実際の要約生成には、インストール・認証済みの `codex` CLI
- URL入力には、Frontmatterに `url` がある完全なローカルMarkdownクリップ

## インストール

リポジトリルートで実行します。

```console
uv tool install -e .
doc-summarizer --help
doc-summarizer config show
```

依存関係、package metadata、CLI entry point、リポジトリの場所を変更した場合は、
再インストールします。

```console
uv tool install -e . --force
```

## 初期設定

`.tkn/config.example.yaml` を次のどちらかへコピーします。

- 通常のユーザー設定: `~/.tkn/doc_summarizer/config.yaml`
- 現在のworking directory専用設定: `./.tkn/config.yaml`

`source_roots` に、Obsidian Web ClipperのMarkdown保存先を1つ以上設定します。
ファイルパスを直接入力する場合、`source_roots` は不要です。

```yaml
source_roots:
  - C:\Users\ExampleUser\Documents\Obsidian\WebClips
output_root: ~/.tkn/doc_summarizer/data/summaries
reports_root: ~/.tkn/doc_summarizer/state/reports
model: null
```

実設定の `./.tkn/config.yaml` はGit管理対象外です。`config show` ではdirectoryを
作成しません。

## 基本的な使い方

クリップ済みMarkdownをファイルパスで要約します。

```console
doc-summarizer summarize "C:\path\to\clipped-article.md"
```

同じローカルクリップを元記事URLで要約します。

```console
doc-summarizer summarize "https://example.com/article"
```

URL入力では、`source_roots` 内を再帰検索し、Markdown Frontmatterの正規化済み
`url` が1件だけ一致することを要求します。一致しない場合は、先にObsidian Web
Clipperで完全なMarkdownを保存するか、ファイルパスを指定してください。HTTP通信は
意図的に行いません。

Codexを実行せず、ファイルも一切書かずに、入力と出力先だけ確認できます。

```console
doc-summarizer summarize "https://example.com/article" --dry-run
```

出力ファイルを明示することもできます。

```console
doc-summarizer summarize "C:\path\to\facts.md" --output "C:\path\to\summary.md"
```

## コマンド

### `summarize SOURCE`

UTF-8のローカルソースを1件解決し、Codexへstructured JSON schema付きで渡し、
生成Markdownを検証してから原子的に1ノートを保存します。

- `SOURCE`: ローカルファイルパス、またはクリップ済みFrontmatter内のHTTP(S) URL
- `--dry-run`: 入力と出力先だけを解決・検証します。Codex実行、出力、report、
  state、cacheの書き込みはありません。
- `--output FILE`: 出力する `.md` の正確なパスを指定します。
- `--output-root DIR`: 自動命名時の出力先設定を、この実行だけ上書きします。
- `--source-root DIR`: URL検索先を上書きします。複数回指定できます。
- `--summary-prompt FILE`: カスタムMarkdownプロンプトを指定します。
- `--model MODEL`: この実行で使うCodex modelを指定します。
- `--overwrite`: source、prompt、modelの変更後に一致する要約を再生成します。
  手動編集・レビュー済み編集も置換し、`reviewStatus` を `unreviewed` に戻します。

`--overwrite` がなければ、現在の有効な要約はCodexを呼ばず `unchanged` になります。
古い要約、不正な要約、内容が異なる既存出力は置換しません。`--overwrite` があっても、
別のsourceまたはpromptに属するファイルは置換しません。

成功時、`created`、`updated`、`unchanged` の状態、要約パス、sourceパス、
検証情報、実行reportパスを含むJSONを返します。

### `validate PATH`

出力schema、Frontmatterの順序とprovenance、本文section、review状態、
source参照、source SHA-256をread-onlyで検証します。

```console
doc-summarizer validate "C:\path\to\summary.md"
```

成功時はJSONの `valid` が `true` になります。失敗時は非0で終了します。

### `config show`

解決後の非secret設定、読み込んだ設定ファイル、各値の決定元、
built-in/custom promptのprovenanceを表示します。Codex実行やdirectory作成は
行いません。

```console
doc-summarizer config show
```

### `prompt init [NAME]`

built-in promptの編集用コピーを `~/.tkn/doc_summarizer/prompts/` に作ります。
コピーには新しいUUIDが付きます。既存ファイルは置換せず、設定も変更しません。

```console
doc-summarizer prompt init my-summary.md
```

使用するには、設定へ `summary_prompt: my-summary.md` を追加するか、
`--summary-prompt` で指定します。カスタムpromptは次のFrontmatterを持つUTF-8
Markdownです。

```markdown
---
type: prompt
id: 00000000-0000-4000-8000-000000000000
version: "1.0"
---

Your instructions...
```

prompt injection対策、source metadata/contentの境界、JSON出力schemaは、
編集可能な指示文の外側でapplicationが管理します。

## 出力と保存先

既定の配置は次のとおりです。

```text
~/.tkn/doc_summarizer/
├── config.yaml
├── data/
│   └── summaries/<year>/<date>_<title>_<prompt-id-prefix>.md
├── prompts/
└── state/
    └── reports/<run-id>.json
```

Codexへ渡す一時schema/outputはOS標準の一時directoryに置き、実行後に削除します。
リポジトリルートへruntime dataを作りません。

生成ノートは参考ノートと同じsection構成です。`cover` がある文書は、タイトル直下に
画像を表示します。Summaryは1段落・約250〜400字を目安とし、Structuringは通常、
H3の大分類、H4の中分類、簡潔な箇条書きという階層で構成します。Key pointsは主要な
5〜8件、Technical termsは中立的で再利用可能な定義3〜7件を目安に絞ります。

1. Summary
2. Structuring (from abstract to concrete)
3. Key points
4. Technical terms
5. Conclusion

Frontmatterには `type: summary`、ローカルsource URI、source SHA-256、
generator・実効model、prompt ID/version/SHA-256、summary profileとoutput schemaの
SHA-256、template ID/version/SHA-256、prompt envelope version、review状態、日時、
安定したnote UUIDを記録します。`nouns` などの分類metadataは別CLIへ委ねるため
登録しません。source本文は要約ノートへ複製しません。

`schemaVersion` と `promptVersion` は、`schemaVersion: "4.0"`、
`promptVersion: "2.0"` のようなYAML文字列として出力します。これらは小数値ではなく
version識別子です。文字列にすることで、`2.0`、`2.10`、将来のsemantic versionを
YAMLの浮動小数点数へ変換させず、そのまま保持できます。

## 設定

低いものから高いものへの優先順位です。

1. built-in defaults
2. `~/.tkn/doc_summarizer/config.yaml`
3. `./.tkn/config.yaml`
4. `--config FILE`
5. 個別CLI option

相対パスはcurrent working directory基準です。unknown key、不正な型、存在しない
明示config、不正prompt、読めないsource、未対応providerはerrorにします。

| Key | 既定値 | 意味 |
| --- | --- | --- |
| `source_roots` | `[]` | URL入力で検索するMarkdown root |
| `output_root` | user data内summaries | 自動命名した要約の保存先 |
| `reports_root` | user state内reports | JSON実行report |
| `provider` | `codex` | 生成adapter。v1はCodexのみ |
| `model` | `null` | 未指定時はCodexの既定model |
| `codex_executable` | `codex` | 実行ファイルまたはshim名 |
| `codex_timeout_seconds` | `1800` | 生成timeout秒 |
| `max_input_bytes` | `2000000` | UTF-8 sourceの最大size |
| `summary_prompt` | `null` | built-in、user prompt名、または絶対path |

## ログとautomation

進捗と診断はstderrです。

```text
[DEBUG] 詳細診断
[INFO] 通常の進捗
[SUCCESS] 利用者が確認すべき最終成功
[WARNING] 継続できるが確認が必要な状態
[ERROR] command失敗
```

`--quiet` はerrorだけ、`--verbose` はdebugも表示し、同時指定はできません。
interactive terminalでは、ANSI color対応時に成功を緑、errorを赤で表示します。
redirect、`NO_COLOR`、`TERM=dumb`、Windows terminal非対応時は無色です。

最終結果はstdoutのJSON 1件だけです。正常終了は `0`、設定、source、生成、
collision、validationの失敗は非0です。

## 安全性と制約

- Web本文は取得しません。要約前にclipが完全か確認してください。
- sourceはuntrusted contentとして扱い、埋め込まれたprompt風の指示には従いません。
- 入力ファイルはread-onlyで、本文を要約出力へそのまま複製しません。
- 出力全体を組み立て、決定的検証に合格してから原子的に確定します。
- 生成内容には意味上の誤りが残る可能性があります。確認後、Vaultのworkflowに
  合わせて `reviewStatus` を変更してください。
- `--overwrite` は生成ノートの手動編集を置換します。明示的にだけ使用してください。
- UTF-8 text fileを対象とし、binaryおよび `max_input_bytes` 超過を拒否します。

## 開発と検証

### Summary profile

要約生成を一体として定義するresourceは、application-owned profileとしてまとめています。

```text
src/doc_summarizer/summary_profiles/
└── default/
    ├── prompt.md
    ├── output.schema.json
    └── template.md
```

`prompt.md` は編集方針とfieldの意味、`output.schema.json` はCodexへ渡す構造化JSON契約、
`template.md` は決定的なMarkdown配置を定義します。loaderは3つすべてを検証し、各SHA-256
からprofile SHA-256を計算します。このprofile hashを冪等性判定にも使うため、schemaや
templateを変更したのに旧ノートを最新と誤判定することはありません。
`config show` ではactive profileと各resourceのprovenanceを確認できます。

カスタムpromptは引き続き利用できます。その場合は `default/prompt.md` だけを置換し、
default schema/templateと組み合わせた別のprofileとしてfingerprintを計算します。
将来application管理の別形式を増やす場合は、同階層へprofile directoryを追加できます。
field変更時はprompt、schema、Pydantic model、renderer、validation、testを、配置変更時は
template、renderer、validation、testを協調して更新してください。

既存schema 2.0/3.0 noteは引き続き `validate` できます。ただしprofile fingerprint導入前の
出力なので、再生成時はresource変更として扱い、明示的な `--overwrite` を必要とします。

```console
uv sync --locked
uv run pytest
uv run ruff check .
uv run mypy src
uv build
```

build/testの一時artifactは通常のcacheまたはOSの一時directoryを使い、
リポジトリルートへruntime dataを作らないでください。
