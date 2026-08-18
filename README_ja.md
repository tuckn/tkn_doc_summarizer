# tkn-doc-summarizer

[English](README.md)

`tkn-doc-summarizer` は、ローカルのテキスト文書、またはブラウザ拡張で事前に
Markdown保存したWeb記事から、ソースに忠実な要約Markdownノートを作るCLIです。
URLはローカルにあるクリップ済みノートを特定する検索キーとして使い、このCLI自身は
Webページを取得しません。

入力ファイルの複製、編集、移動、削除は行いません。`summarize` または `synthesize` が
作る内容成果物は、要約Markdownノート1つだけです。

## 必要環境

- 主対象はWindows 11。OS固有でない処理はLinuxでも動作します。
- Python 3.11以上
- [uv](https://docs.astral.sh/uv/)
- 実際の要約生成には、インストール・認証済みの `codex` CLI
- URL入力には、Frontmatterに `url` がある完全なローカルMarkdownクリップ

## インストール

通常利用では、例示しているpathをこのリポジトリの実際のfolder pathへ置き換え、
リポジトリルートへ移動してからインストールします。

```console
cd "C:\path\to\tkn_doc_summarizer"
uv tool install .
tkn-doc-summarizer --help
```

通常のインストールでは、インストール時点のcode、package resource、dependencyが
tool環境へ反映されます。`git pull` などでリポジトリを更新した後は、更新内容を
反映するため再インストールします。

```console
cd "C:\path\to\tkn_doc_summarizer"
uv tool install . --reinstall
tkn-doc-summarizer --help
```

`--force` は、実行ファイルのentry point競合を解消する場合など、tool自体の
強制インストールが必要な場合に限って使用します。

### 開発用のeditable installation

開発時にsource codeの変更をすぐCLIへ反映したい場合は、editable installationを
使用します。

```console
cd "C:\path\to\tkn_doc_summarizer"
uv tool install -e . --reinstall
```

editable installationでは、通常のsource code変更に再インストールは不要です。
dependency、package metadata、CLI entry pointを変更した場合、またはリポジトリを
移動・renameした場合は、同じcommandを再実行します。

## 初期設定

通常のユーザー設定を作成します。

```console
tkn-doc-summarizer config init
tkn-doc-summarizer config show
```

`config init` はpackageに含まれるexampleを
`~/.tkn/doc_summarizer/config.yaml` へ作成し、その絶対pathを表示します。同じ内容の
fileがある場合は `unchanged` とし、編集済み設定は置換しません。意図的に初期状態へ
戻す場合は `config init --force` を使います。既存fileは置換前にbackupされます。

current working directoryだけで設定を上書きする場合は、`./.tkn/config.yaml` を使用します。
このfileはGit管理対象外です。

`source_roots` に、Obsidian Web ClipperのMarkdown保存先を1つ以上設定します。
ファイルパスを直接入力する場合、`source_roots` は不要です。

```yaml
source_roots:
  - C:\Users\ExampleUser\Documents\Obsidian\WebClips
output_root: ~/.tkn/doc_summarizer/data/summaries
reports_root: ~/.tkn/doc_summarizer/state/reports
model: null
source_path_format: native
summary_profile: default-ja
```

`config show` は有効な値と決定元を表示し、directory作成やCodex実行は行いません。

## 基本的な使い方

### `summarize`

クリップ済みMarkdownをファイルパスで要約します。

```console
tkn-doc-summarizer summarize "C:\path\to\clipped-article.md"
```

同じsourceの英語版を、この実行だけprofileを上書きして生成できます。

```console
tkn-doc-summarizer summarize "C:\path\to\clipped-article.md" --summary-profile default-en
```

同じローカルクリップを元記事URLで要約します。

```console
tkn-doc-summarizer summarize "https://example.com/article"
```

URL入力では、`source_roots` 内を再帰検索し、Markdown Frontmatterの正規化済み
`url` が1件だけ一致することを要求します。一致しない場合は、先にObsidian Web
Clipperで完全なMarkdownを保存するか、ファイルパスを指定してください。HTTP通信は
意図的に行いません。

Codexを実行せず、ファイルも一切書かずに、入力と出力先だけ確認できます。

```console
tkn-doc-summarizer summarize "https://example.com/article" --dry-run
```

出力ファイルを明示することもできます。

```console
tkn-doc-summarizer summarize "C:\path\to\facts.md" --output "C:\path\to\summary.md"
```

### `synthesize`

複数ページを1つの論理的な記事として要約するには、ページ順にsourceを列挙します。

```console
tkn-doc-summarizer synthesize "C:\path\to\page-1.md" "C:\path\to\page-2.md" --dry-run
tkn-doc-summarizer synthesize "C:\path\to\page-1.md" "C:\path\to\page-2.md"
```

各sourceにはローカルpath、または `source_roots` からローカル解決できるクリップ済み
記事URLを指定できます。`--title` を省略すると、全sourceから統合内容を生成した後、
その内容を表すタイトルも生成AIが決めます。

複数の記事を比較し、共通概念、異なる観点、相反する意見をまとめる場合は
`--mode compare` を指定します。

```console
tkn-doc-summarizer synthesize "C:\path\to\article-a.md" "C:\path\to\article-b.md" --mode compare
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
- `--summary-profile PROFILE`: この実行で `default-ja` または `default-en` を選択します。
- `--summary-prompt FILE`: カスタムMarkdownプロンプトを指定します。
- `--model MODEL`: この実行で使うCodex modelを指定します。
- `--overwrite`: source、prompt、modelの変更後に一致する要約を再生成します。
  手動編集・レビュー済み編集も置換し、`reviewStatus` を `unreviewed` に戻します。

`--overwrite` がなければ、現在の有効な要約はCodexを呼ばず `unchanged` になります。
古い要約、不正な要約、内容が異なる既存出力は置換しません。`--overwrite` があっても、
別のsource、summary profile、promptに属するファイルは置換しません。異なるprofileは
同じsourceに対して別ノートとして共存できます。

成功時、`created`、`updated`、`unchanged` の状態、要約パス、sourceパス、
検証情報、実行reportパスを含むJSONを返します。

### `synthesize SOURCE SOURCE [...]`

2件以上のsourceから1つの統合ノートを作ります。`--mode series` が既定値で、
ページ順に列挙した1つの記事を統合します。ページ順はCLI引数の順序そのものであり、
ファイル名やURLから推測しません。重複するページ共通部分を除外しながら、ページを
またぐ論旨や後半の留保条件を保持します。

`--mode compare` は、別々の記事を比較し、比較要約、共通概念、観点別の捉え方、
相違・対立、各source固有の知見、専門用語、結論を生成します。各主張には
`[S1, S2]` のようなsource IDを付け、根拠を追跡できます。CLI引数の順序はsource IDを
決めるだけで、権威、優先順位、時系列を意味しません。実際の対立がない場合は無理に
対立を作りません。source IDは両modeとも `S1`、`S2`…として自動付与します。

`--dry-run`、`--output`、`--output-root`、`--source-root`、
`--summary-profile`、`--model`、`--overwrite` は `summarize` と同じwrite safety契約です。
`--summary-prompt` はseriesでのみ使用でき、compareでは比較prompt、schema、templateの
整合性を保つため拒否します。raw input合計には
`max_total_input_bytes` が適用され、同じローカルファイルへ解決される重複entryは
拒否します。`--title TITLE` は生成タイトルを使わず、明示したタイトルをそのまま
Frontmatter、H1、自動ファイル名へ使用するoverrideです。省略時は、seriesでは全ページの
統合内容、compareでは比較結果全体を踏まえ、生成AIがタイトルを生成します。

タイトル未指定の `--dry-run` は生成AIを呼ばないため、返されるpathは先頭sourceタイトルを
使った暫定値です。JSONの `generated_title_pending` が `true` になり、実生成時のpathは
生成タイトルに応じて確定します。

seriesはschema 6.0、compareはschema 7.0を生成します。Frontmatterには、自動生成した
安定source-set UUID、mode、順序付きローカルsource参照、各source SHA-256、正規化した
`sourceSetSha256` を記録します。`source_path_format` の既定値は `native` です。
Windowsでは、pathをコピーしてExplorerやOSの「ファイル名を指定して実行」へ
貼り付けやすいよう、次のようにYAMLのシングルクォートで囲みます。

```yaml
sources:
  - id: "S1"
    source: 'C:\path\to\page-1.md'
```

`config.yaml` で次のように指定すると、従来のfile URI形式で出力できます。

```yaml
source_path_format: file-uri
```

```yaml
source: "file:///C:/path/to/page-1.md"
```

設定値にかかわらず、既存noteのOS pathと `file:///C:/...` はどちらも読み取り・検証
できます。既存noteを別形式へ変換する場合は、レビュー済み内容を暗黙に書き換えない
ため `--overwrite` が必要です。UUIDは順序付きの
解決後ローカルpathから安定生成し、内容変更は
`sourceSetSha256` で検出します。source変更後は明示的な `--overwrite` が必要で、
レビュー済み出力を暗黙には置換しません。

### `validate PATH`

出力schema、Frontmatterの順序とprovenance、本文section、review状態、単一source、
またはseries/compareの全順序付きsourceと各SHA-256をread-onlyで検証します。
複数sourceでは `sourceSetSha256` も再計算します。

```console
tkn-doc-summarizer validate "C:\path\to\summary.md"
```

成功時はJSONの `valid` が `true` になります。失敗時は非0で終了します。

### `config init [--force]`

packageに含まれるexampleから `~/.tkn/doc_summarizer/config.yaml` を作り、結果と絶対pathを
JSONで表示します。同じ内容なら `unchanged`、異なる内容なら保護します。`--force` を
指定して置換する場合も、先にtimestamp付きbackupを作成します。

```console
tkn-doc-summarizer config init
```

### `config show`

解決後の非secret設定、読み込んだ設定ファイル、各値の決定元、
built-in/custom promptとcomparison profileのprovenanceを表示します。Codex実行やdirectory作成は
行いません。

```console
tkn-doc-summarizer config show
```

### `prompt init [NAME]`

built-in promptの編集用コピーを `~/.tkn/doc_summarizer/prompts/` に作ります。
コピーには新しいUUIDが付きます。既存ファイルは置換せず、設定も変更しません。

```console
tkn-doc-summarizer prompt init my-summary.md
tkn-doc-summarizer prompt init my-english-summary.md --summary-profile default-en
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

prompt injection対策とsource metadata/contentの境界は、編集可能な指示文の外側で
applicationが管理します。カスタムpromptは選択profileのpromptだけを置換し、
言語別のschemaとtemplateはそのまま使用します。

## 出力と保存先

既定の配置は次のとおりです。

```text
~/.tkn/doc_summarizer/
├── config.yaml
├── data/
│   └── summaries/<year>/<date>_<title>_<profile>_<prompt-id-prefix>.md
├── prompts/
└── state/
    └── reports/<run-id>.json
```

Codexへ渡す一時schema/outputはOS標準の一時directoryに置き、実行後に削除します。
リポジトリルートへruntime dataを作りません。

既定の `default-ja` は、日本語本文、日本語H2見出し、1段落・約250〜400字の要約を
生成します。`default-en` は、英語本文、英語H2見出し、約120〜200語の要約を生成します。
どちらも通常、H3の大分類、H4の中分類、簡潔な箇条書きという階層で構成し、重要ポイントは
5〜8件、専門用語は中立的で再利用可能な定義3〜7件を目安に絞ります。`cover` がある文書は、
タイトル直下に画像を表示します。

日本語見出しは「要約」「構造化（抽象から具体へ）」「重要ポイント」「専門用語」「結論」、
英語見出しは `Summary`、`Structuring (from abstract to concrete)`、`Key points`、
`Technical terms`、`Conclusion` です。

Frontmatterには `type: summary`、ローカルsource URI、source SHA-256、
generator・実効model、prompt ID/version/SHA-256、summary profileとoutput schemaの
SHA-256、template ID/version/SHA-256、prompt envelope version、review状態、日時、
安定したnote UUIDを記録します。`nouns` などの分類metadataは別CLIへ委ねるため
登録しません。source本文は要約ノートへ複製しません。

`schemaVersion` と `promptVersion` は、`schemaVersion: "5.0"`、
`promptVersion: "3.0"` のようなYAML文字列として出力します。これらは小数値ではなく
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
| `max_total_input_bytes` | `8000000` | 1 source setのsource合計最大byte数 |
| `source_path_format` | `native` | Frontmatterのローカルsource参照。`native` または `file-uri` |
| `summary_profile` | `default-ja` | built-in言語/profile。`default-ja` または `default-en` |
| `summary_prompt` | `null` | 選択profileのprompt、user prompt名、または絶対path |

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

### Summary / comparison profile

要約生成を一体として定義するresourceは、application-owned profileとしてまとめています。

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

src/doc_summarizer/comparison_profiles/
├── default-ja/
│   ├── prompt.md
│   ├── output.schema.json
│   └── template.md
└── default-en/
    ├── prompt.md
    ├── output.schema.json
    └── template.md
```

`prompt.md` は編集方針とfieldの意味、`output.schema.json` はCodexへ渡す構造化JSON契約、
`template.md` は決定的なMarkdown配置を定義します。loaderは3つすべてを検証し、各SHA-256
からprofile SHA-256を計算します。このprofile hashを冪等性判定にも使うため、schemaや
templateを変更したのに旧ノートを最新と誤判定することはありません。
`config show` ではactive profileと各resourceのprovenanceを確認できます。

YAMLの `summary_profile` またはCLIの `--summary-profile` でprofileを選び、CLI指定が通常どおり
最優先になります。この言語選択はcompare profileにも適用されます。カスタムpromptは
summarize/seriesでは選択profileの `prompt.md` だけを置換し、そのprofileのschema/templateと
組み合わせた別のprofileとしてfingerprintを計算します。compare profileはapplication-ownedの
一体的な比較契約として扱い、カスタムpromptは受け付けません。
field変更時はprompt、schema、Pydantic model、renderer、validation、testを、配置変更時は
template、renderer、validation、testを協調して更新してください。

`validate` はschema 2.0〜7.0を扱います。schema 5.0は単一source、6.0はseries、7.0は
compareです。profile付きファイル名とidentityにより、同じsourceの日本語版・英語版noteを
上書きせず共存できます。

```console
uv sync --locked
uv run pytest
uv run ruff check .
uv run mypy src
uv build
```

build/testの一時artifactは通常のcacheまたはOSの一時directoryを使い、
リポジトリルートへruntime dataを作らないでください。
