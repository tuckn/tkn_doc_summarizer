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
values.generation.active_profile=codex
value_sources.generation.active_profile=built-in defaults
generationResolved.will_call_provider=false
```

`values.*` に有効値とリソース情報、`sources[0]` などに読み込んだ設定元、`value_sources.*` に各値の決定元、`generationResolved.*` に選択した接続先・モデルなどを表示します。`--json` では従来と同じ `sources`、`value_sources`、`values`、`generationResolved` の構造を返します。どちらの形式も読み取り専用で、表示の案内は標準エラーへ `[INFO] Showing resolved configuration` として出ます。`--quiet` は一覧を保ち、ログだけを省略します。

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
| `schema_version` | `"1.0.0"` | アプリ設定形式の版 |
| `source_roots` | `[]` | URL から保存済み Markdown を探すフォルダ。空なら URL 検索不可 |
| `output_root` | `~/.tkn/doc_summarizer/data/summaries` | 自動命名するノートの保存先と既存ノートの検索先 |
| `reports_root` | `~/.tkn/doc_summarizer/state/reports` | JSON 実行レポートの保存先 |
| `max_input_bytes` | `2000000` | 1ファイルの上限バイト数。Frontmatter を含む。1以上 |
| `max_total_input_bytes` | `8000000` | 1回の `synthesize` の合計入力上限バイト数。1以上 |
| `source_path_format` | `native` | 出典参照の形式。`native` または `file-uri` |
| `generation.summary_profile` | `default-ja` | 言語・出力形式。`default-ja` / `default-en` |
| `generation.active_profile` | `codex` | アプリ内の生成プロファイル |
| `generation.profiles.codex.bridge_profile` | `codex-default` | Bridge 共有設定の参照先 |
| `generation.profiles.<name>.overrides` | `{}` | このアプリでの接続設定上書き |
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
| アプリの要約プロファイル | `generation.summary_profile` | 言語・生成指示・出力形式 | `--summary-profile` |
| アプリの接続名 | `generation.active_profile` | アプリ内の `generation.profiles` の項目 | `--profile` |
| Bridge の接続名 | `generation.profiles.<name>.bridge_profile` | 共有設定の接続先・モデル・認証 | `--bridge-profile` |
| 接続設定の上書き | `generation.profiles.<name>.overrides` | 選択した Bridge 接続設定の一部 | `--model` など |

Bridge の共有設定は `~/.tkn/genai_bridge/config.yaml` です。共有設定がなくても組み込みの `codex-default` を利用できます。

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
  summary_profile: default-ja
  active_profile: codex
  profiles:
    codex:
      bridge_profile: codex-default
    claude:
      bridge_profile: claude-default
    codex-long:
      bridge_profile: codex-default
      overrides:
        timeout_seconds: 1800
```

`claude-default` は Bridge 側に定義してから使います。モデル・認証・実行ファイル・`local_only` は [Bridge の設定仕様](https://github.com/tuckn/tkn_genai_bridge/blob/9cf534e47159901c3bb05bb802695fad746cc338/docs/reference/configuration.md)に従います。Bridge は作業フォルダの `./.tkn/config.yaml` を読みません。

```shell
tkn-doc-summarizer config list --profile claude
tkn-doc-summarizer summarize "<source-file>" --profile claude --dry-run
```

`--model` と `--provider-timeout-seconds` はその実行の接続設定を上書きします。待機上限は共有設定を継承します。Bridge の組み込み値は300秒、指定できる範囲は0より大きく86400以下です。存在しないプロファイルや不正な値で、別の接続先へ自動で切り替えることはありません。
`summarize`、`synthesize`、`config list` のオプションはコマンド名の後ろに指定します。`--source-root` は複数回指定でき、設定ファイルの検索先一覧を置き換えます。`--model`、`--config`、`--reports-root`、入力サイズやタイムアウトの指定もその実行だけに適用されます。

旧形式のトップレベル `summary_profile`、`model`、`provider: codex`、`codex_executable`、`codex_timeout_seconds` は読み込み時に変換します。同じファイルで旧形式と `generation` を混在させるとエラーです。旧 `provider` / `codex_executable` は Codex 接続に限定されます。旧 `--codex-executable` / `--codex-timeout-seconds` も互換入力として受け付けます。設定ファイルを自動で書き換えません。

## 出典のパス形式

既定の出典参照は Windows では `source: 'C:\path\to\article.md'` の形式です。URI に変えるには設定の `source_path_format: file-uri` を指定します。この場合は `source: "file:///C:/path/to/article.md"` となります。複数文書では `sources` の各出典へ適用します。両形式とも検証できます。既存ノートの形式を変えるには、手動編集を含む置換に同意したうえで `--overwrite` により再生成します。

## カスタム生成指示

```shell
tkn-doc-summarizer prompt init my-summary.md
```

`NAME` を省略すると `summary.md` です。`~/.tkn/doc_summarizer/prompts/` に UUID 付きの編集用コピーを作り、既存ファイルと設定は変更しません。英語版を基にするには `--summary-profile default-en` を指定します。

作成した UTF-8 Markdown の Frontmatter は `type: prompt`、UUID の `id`、文字列の `version` を保持し、本文の指示を編集します。設定ファイルの一部として `summary_prompt: my-summary.md` を指定するか、その実行だけ `--summary-prompt my-summary.md` を使います。別のフォルダなら絶対パスを指定し、相対フォルダを含むパスは指定しません。

カスタム指示は `summarize` と `series` で使用できます。選択したプロファイルの生成指示のみを置換し、JSON スキーマと Markdown テンプレートは維持します。比較モードはカスタム指示を受け付けません。入力本文を命令として扱わないための区切りはアプリが付けます。
