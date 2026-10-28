# 設定と生成プロファイル

`tkn-doc-summarizer config init` は `~/.tkn/doc_summarizer/config.yaml` を作ります。同じ内容なら `unchanged`、異なる既存ファイルがあれば上書きせず停止します。`config list` は有効値とその決定元を1行ごとの `key=value` で表示し、外部 CLI の起動・認証・通信・書き込みは行いません。

## 設定一覧の表示

```shell
tkn-doc-summarizer config list
tkn-doc-summarizer config list --json
```

既定の表示は `git config --list` と同じく1行に1つの `key=value` です。入れ子のキーは `.`、配列の要素は `[0]` などの添字で表します。空の配列・マッピングは `[]`・`{}`、真偽値は `true`・`false`、未設定値は `null` です。文字列は引用符を付けず、Windows パスのバックスラッシュを二重にしません。改行・タブなどの制御文字はエスケープします。

表示形式の例です。

```text
sources[0]=built-in defaults
values.source_roots[0]=C:\path\to\web-clips
values.generation.summary.default_profile=default
value_sources.generation.summary.default_profile=built-in defaults
generationResolved.summary.will_call_provider=false
generationResolved.comparison.will_call_provider=false
```

`values.*` に有効値とリソース情報、`sources[0]` などに読み込んだ設定元、`value_sources.*` に各値の決定元を表示します。`generationResolved.summary.*`／`generationResolved.comparison.*` に各モードで選択した接続先・モデル・出力形式を表示します。`--json` でも同じ構造を返します。どちらの形式も読み取り専用で、表示の案内は標準エラーへ `[INFO] Showing resolved configuration` として出ます。`--quiet` は一覧を保ち、ログだけを省略します。

## 読み込み順とパス

後の層が前の値を上書きします。

| 順位 | 設定元 | 用途 |
| --- | --- | --- |
| 1 | 組み込み既定値 | 設定ファイルがなくても使う値 |
| 2 | `~/.tkn/doc_summarizer/config.yaml` | ユーザーの通常設定 |
| 3 | `./.tkn/config.yaml` | 実行時の作業フォルダ固有の設定 |
| 4 | `--config FILE` | 明示した YAML ファイル |
| 5 | コマンドラインオプション | その実行だけの上書き |

通常の相対パスは設定ファイルの場所ではなく、実行時の作業フォルダを基準に解決します。`summary_prompt` にファイル名だけを指定した場合は、専用の `~/.tkn/doc_summarizer/prompts/` から探します。`./.tkn/config.yaml` は Git 管理対象外です。

組み込み既定値と主な設定項目は次のとおりです。[同梱設定例](../../src/doc_summarizer/resources/config.example.yaml)は `config init` が作る全項目の例です。例中の URL 検索先は置換用のパスなので、実際の保存先に変更してください。

| キー | 既定値 | 役割 |
| --- | --- | --- |
| `schema_version` | `"2.0.0"` | アプリ設定形式の版。Bridge や生成ノートの版とは別 |
| `source_roots` | `[]` | URL から保存済み Markdown を探すフォルダ。空なら URL 検索不可 |
| `output_root` | `~/.tkn/doc_summarizer/data/summaries` | 自動命名するノートの保存先と既存ノートの検索先 |
| `reports_root` | `~/.tkn/doc_summarizer/state/reports` | JSON 実行レポートの保存先 |
| `max_input_bytes` | `2000000` | 1ソースファイル、および結合後 context それぞれの上限バイト数。1以上 |
| `max_total_input_bytes` | `8000000` | 複数文書を渡す1回の `summarize` のソース＋context 合計入力上限バイト数。1以上 |
| `source_path_format` | `native` | 出典参照の形式。`native` または `file-uri` |
| `generation.summary.default_profile` | `default` | 単一・複数入力の要約に使うアプリ内プロファイル |
| `generation.summary.profiles.<name>.bridge_profile` | `null` | Bridge 共有設定の参照先。省略／`null` は Bridge の `default_profile` |
| `generation.summary.profiles.<name>.summary_profile` | `default-ja` | 要約の出力形式。`default-ja` / `default-en` / `conversation-ja` / `meeting-minutes-ja` |
| `generation.comparison.default_profile` | `default` | 比較に使うアプリ内プロファイル |
| `generation.comparison.profiles.<name>.bridge_profile` | `null` | 比較用の Bridge 共有設定の参照先。省略／`null` は Bridge の `default_profile` |
| `generation.comparison.profiles.<name>.comparison_profile` | `compare-ja` | 比較の出力形式。`compare-ja` / `compare-en` / `claims-ja` |
| `generation.<summary または comparison>.profiles.<name>.overrides` | `{}` | このアプリでの接続設定上書き |
| `summary_prompt` | `null` | 組み込み指示を使用。ファイル名または絶対パスで変更 |

`source_roots: []` は下位層の検索先一覧を空にします。`summary_prompt` や Bridge の `model` に未指定を表す場合は、空文字ではなく YAML の `null` を使います。未知のキー、不正な型・範囲、存在しない `--config`、読み込めないプロンプトはエラーです。

`output_root` を変えると以前の保存先は検索しなくなり、別のノートが生成されることがあります。既存ノートの再利用では、入力・要約リソース・明示したモデルなどを照合します。Bridge の共有設定だけを変更しても既存ノートは自動再生成しません。新しい接続条件で再生成するには `--overwrite` を指定します。

次は保存先と URL 検索先を変える設定の抜粋です。`config init` が作ったファイルの該当項目を置き換え、ほかの項目を残します。ファイルパスを直接指定する場合、`source_roots` は使いません。

```yaml
output_root: 'C:\path\to\summaries'
reports_root: 'C:\path\to\reports'
source_roots:
  - 'C:\path\to\web-clips'
```

## アプリ設定と Bridge 共有設定

| 種類 | ファイル・設定 | 選ぶもの | その実行だけ変更 |
| --- | --- | --- | --- |
| アプリの要約プロファイル | `generation.summary.profiles.<name>.summary_profile` | 言語・生成指示・出力形式 | `--summary-profile`（series のみ） |
| アプリの比較プロファイル | `generation.comparison.profiles.<name>.comparison_profile` | 比較の生成指示・出力形式 | `--comparison-profile`（compare のみ） |
| アプリの既定プロファイル | `generation.<summary または comparison>.default_profile` | 各モードの `profiles` の項目 | `--profile` |
| Bridge の接続名 | 各プロファイルの `bridge_profile` | 共有設定の接続先・モデル・認証 | `--bridge-profile` |
| 接続設定の上書き | 各プロファイルの `overrides` | 選択した Bridge 接続設定の一部 | `--model` など |

Bridge の共有設定は `~/.tkn/genai_bridge/config.yaml` です。共有設定がなくても組み込みの `codex-default` を利用できます。

`bridge_profile` を省略、または `null` にすると、Bridge 側の `default_profile` を使います。Bridge の既定値を変更すると、このアプリも次の実行から追従します。`bridge_profile: copilot-default` のように名前を明示した場合は、その接続先に固定します。空文字や空白だけの指定はエラーです。`--bridge-profile NAME` はその実行だけ接続先を固定します。

Bridge の共有設定を明示する場合の最小例です。既存の設定があれば、利用するプロファイルを選んでください。

```yaml
schema_version: "1.1.0"
default_profile: codex-default
profiles:
  codex-default:
    provider: codex
    model: null
    timeout_seconds: 1800
```

以下は本 CLI 側の設定の抜粋です。ほかの設定を保持して `generation` 以下を編集してください。

```yaml
generation:
  summary:
    default_profile: default
    profiles:
      default:
        bridge_profile: null
        summary_profile: default-ja
      conversation:
        bridge_profile: claude-default
        summary_profile: conversation-ja
        overrides:
          timeout_seconds: 1800
  comparison:
    default_profile: default
    profiles:
      default:
        bridge_profile: null
        comparison_profile: compare-ja
      claims:
        bridge_profile: claude-default
        comparison_profile: claims-ja
```

`claude-default` は Bridge 側に定義してから使います。モデル・認証・実行ファイル・`local_only` は [Bridge の設定仕様](https://github.com/tuckn/tkn_genai_bridge/blob/9cf534e47159901c3bb05bb802695fad746cc338/docs/reference/configuration.md)に従います。Bridge は作業フォルダの `./.tkn/config.yaml` を読みません。

```shell
tkn-doc-summarizer config list --profile conversation
tkn-doc-summarizer summarize "<source-file>" --profile conversation --dry-run
tkn-doc-summarizer config list --mode compare --profile claims
tkn-doc-summarizer summarize "<source-1>" "<source-2>" --mode compare --profile claims --dry-run
```

`--mode series`（既定）は `generation.summary`、`--mode compare` は `generation.comparison` を使います。`--profile NAME` はそのグループのプロファイルを選び、接続先と出力形式をまとめて切り替えます。その後に `--bridge-profile`、`--model`、`--provider-timeout-seconds`、`--summary-profile`／`--comparison-profile` の上書きを適用します。別モードの設定には影響しません。存在しないプロファイル名はエラーです。

`config list` は常に両モードを表示します。`--profile` 等の上書き対象は既定で要約側です。比較側を確認・上書きするには `--mode compare` を指定します。

`--model` と `--provider-timeout-seconds` はその実行の接続設定を上書きします。待機上限は共有設定を継承します。Bridge の組み込み値は300秒、指定できる範囲は0より大きく86400以下です。存在しないプロファイルや不正な値で、別の接続先へ自動で切り替えることはありません。
`summarize`、`config list` のオプションはコマンド名の後ろに指定します。`--source-root` は複数回指定でき、設定ファイルの検索先一覧を置き換えます。`--model`、`--config`、`--reports-root`、入力サイズやタイムアウトの指定もその実行だけに適用されます。

## 旧形式からの移行

旧設定形式の読み込み互換はありません。`schema_version: "1.0.0"`、`generation.active_profile`／`generation.profiles`／`generation.summary_profile`、トップレベルの `summary_profile`／`bridge_profile`／`model`／`provider`／`provider_timeout_seconds`／`codex_executable`／`codex_timeout_seconds` はエラーです。旧 CLI オプション `--codex-executable`／`--codex-timeout-seconds` も廃止しました。

既存の保存先などは維持したまま、`schema_version` を `"2.0.0"` に変更し、`generation` を上の例のように置き換えてください。旧 `active_profile` の選択名は要約側の `default_profile` に、各接続設定は要約側の `profiles` に移し、各プロファイル内に `summary_profile` を指定します。比較側は別に定義します。以前の英語比較を維持する場合は、比較側に `comparison_profile: compare-en` を明示します。

トップレベルのモデル指定は選択するプロファイルの `overrides.model` に移します。CLI のパスは Bridge 共有設定の対象プロファイルの `cli.executable`（またはアプリ側の `overrides.cli.executable`）へ、タイムアウトは `timeout_seconds`（または `overrides.timeout_seconds`）へ移します。接続先の種類は Bridge 側の `provider` で指定します。

設定ファイルは自動で書き換えません。`config init --force` はバックアップを作って同梱例へ置換するだけであり、設定内容を移行するコマンドではありません。

## 出典のパス形式

既定の出典参照は Windows では `source: 'C:\path\to\article.md'` の形式です。URI に変えるには設定の `source_path_format: file-uri` を指定します。この場合は `source: "file:///C:/path/to/article.md"` となります。複数文書では `sources` の各出典へ適用します。両形式とも検証できます。既存ノートの形式を変えるには、手動編集を含む置換に同意したうえで `--overwrite` により再生成します。

## カスタム生成指示

`conversation-ja` は会話の文字起こし用です。`summarize` の既定の `series` モードで単一・複数入力に使い、会話日は実行時の `--conversation-date YYYY-MM-DD` で指定します。設定ファイルに会話日のキーは追加しません。出典時刻・話者の不確かさ・記録の形式は [会話記録のガイド](../guides/conversations.md) を参照してください。比較に切り替える場合は `--mode compare` を指定します。比較側の設定は要約側から独立しています。

`meeting-minutes-ja` は会議後の議事メモ用で、概要・事実・認識差／未決事項・RAID・次回確認事項の5節を出力します。同じく `summarize` の `series` モードで単一・複数入力に対応し、`--conversation-date` を使えます。独立した JSON スキーマとテンプレートを持ち、結論・専門用語は要求しません。比較モードでは使いません。

比較用の組み込みprofileは、`summarize --mode compare --comparison-profile NAME` で選べます。`compare-ja`・`compare-en` は記事比較、`claims-ja` は同一話者の主張整理です。省略時は選択した `generation.comparison.profiles.<name>.comparison_profile` を使います。要約側が英語でも、比較側の既定は独立して `compare-ja` です。

```shell
tkn-doc-summarizer prompt init my-summary.md
```

`NAME` を省略すると `summary.md` です。`~/.tkn/doc_summarizer/prompts/` に UUID 付きの編集用コピーを作り、既存ファイルと設定は変更しません。英語版を基にするには `--summary-profile default-en` を指定します。

作成した UTF-8 Markdown の Frontmatter は `type: prompt`、UUID の `id`、文字列の `version` を保持し、本文の指示を編集します。設定ファイルの一部として `summary_prompt: my-summary.md` を指定するか、その実行だけ `--summary-prompt my-summary.md` を使います。別のフォルダなら絶対パスを指定し、相対フォルダを含むパスは指定しません。

カスタム指示は `summarize` の `series` モードで単一・複数入力に使用できます。選択したプロファイルの生成指示のみを置換し、JSON スキーマと Markdown テンプレートは維持します。設定ファイルの `summary_prompt` は要約側だけに適用し、比較側には影響しません。比較モードで CLI の `--summary-prompt` を指定するとエラーです。入力本文を命令として扱わないための区切りはアプリが付けます。

## 実行ごとの補足 context

`summarize`（`series`／`compare`）で、全 profile に補足を渡せます。接続先を選ぶ `--profile` や、固定の生成指示を置き換える `--summary-prompt` とは独立しています。

```shell
tkn-doc-summarizer summarize "<source-file>" --context "略称ABCは今回の製品名。費用と期限に注目。"
tkn-doc-summarizer summarize --sources-file sources.txt --summary-profile meeting-minutes-ja --context "会議の背景。" --context "C:\path\to\context.md" --context "期限は未確定。"
tkn-doc-summarizer summarize "<article-a>" "<article-b>" --mode compare --context "両記事の前提条件の違いを重視。"
```

- `--context TEXT_OR_FILE` は、補足テキストまたは UTF-8 ファイルのパスです。複数回指定でき、テキストとファイルを自由に混在させられます。長い補足・テキスト化した参照資料・別のツールの要約はファイルにまとめられます。Frontmatter や所定の見出しは不要です。
- 既存のファイルは拡張子なしでも読み込みます。絶対パス、`.\`・`..\`・`~\` で始まるパス、空白のない `context.md` のような拡張子付きの名前や `notes\context` のような相対パスもファイル指定と判定し、存在しなければエラーです。空白を含む相対パスを明確に指定するには `.\meeting context.md` のように書いてください。通常の文章、複数行のテキスト、`https://...` 等の URL は文字列として扱います。
- 各 `--context` を指定順に読み込み、空行で結合します。改行を LF に統一し、各入力の前後の空白を除きます。ファイルは UTF-8（BOM 可）。相対パスは実行時の作業フォルダを基準とし、ファイル自体は変更しません。同じ指定を繰り返した場合も順序を保ち、重複除去はしません。
- 明示した補足が空、ファイルが読めない、UTF-8 でない、サイズ上限を超える場合は生成前に停止します。ファイルの読込サイズと結合後テキストはそれぞれ `max_input_bytes` 以内、複数文書の要約・比較はソースと context の合計も `max_total_input_bytes` 以内である必要があります。
- 背景・用語・名前の表記・注目点の有力な手掛かりとして使います。ただし、会議での発言や独立確認された事実に格上げせず、原文との矛盾は留保として残すよう指示します。比較でも context だけの主張を S番号の根拠にしません。
- 読み込んだ context 本文中のパス・URL を再帰的に開くことはありません。URL の取得や PPTX／DOCX／PDF 等の抽出も行わず、必要な本文をテキスト化して含めます。補足の中でも「ユーザーの手掛かり」「参照資料の抜粋」「別ツールの要約」等を区別して記述してください。

context は設定ファイルや profile に固定保存せず、今回の入力とともに選択した Bridge 接続先へ渡します。渡してよい情報だけを指定してください。正規化・結合後のテキストの SHA-256 をノートの `contextSha256` と実行結果の `details.context_sha256` に記録し、元の補足全文は Frontmatter・実行レポートに保存しません（生成本文には反映されます）。同じ補足なら再利用でき、補足の追加・変更・削除・並べ替えで結合結果が変わる場合は `--overwrite` が必要です。再実行に必要な補足は利用者が保持してください。`--dry-run` でも補足を読み込み、生成計画の入力ハッシュ・token 概算へ反映しますが、外部生成・書き込みはしません。
