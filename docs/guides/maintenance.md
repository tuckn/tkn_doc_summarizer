# 更新と開発

## インストール済み CLI を更新する

リポジトリを更新したら、ソース・同梱リソース・依存関係を反映します。

```shell
cd "C:\path\to\tkn_doc_summarizer"
uv tool install . --reinstall
tkn-doc-summarizer --help
tkn-doc-summarizer --version
```

`uv tool install . --force` は実行ファイルの競合など、ツール環境の強制的な再作成が必要な場合に使います。プロンプトやテンプレートが変わった後、既存ノートの再生成には `--overwrite` が必要になることがあります。

## 保存済みノートを検証する

```shell
tkn-doc-summarizer validate "<summary-note>"
```

`validate` は `schemaVersion` 2.0〜9.0 を読み取り専用で検証します。旧版の見出し順もその版の規則で判定します。Frontmatter の必須項目・順序・生成情報・確認状態、本文の見出し、出典ファイルとハッシュを検査し、複数文書はすべての出典と `sourceSetSha256` も照合します。現在の新規出力の形式は [要約ノートの形式](../reference/note-format.md)を参照してください。

元文書を移動・変更すると検証が失敗することがあります。形式の検証と、現在の生成条件で再利用できるかの判定は別です。新形式への再生成や、生成条件が変わったノートの更新には明示的な `--overwrite` が必要です。

## 設定を初期状態へ戻す

```shell
tkn-doc-summarizer config init --force
```

異なる内容の設定があれば、同じフォルダへ日時付きの `.bak` を保存してから同梱例で置き換えます。結果の `backup_path` でバックアップ先を確認してください。保存先などの設定も初期化されます。要約ノートとカスタムプロンプトは変更しません。

## 開発環境を用意する

```shell
cd "C:\path\to\tkn_doc_summarizer"
uv sync --locked
uv run pytest
uv run ruff check .
uv run mypy src
uv build
```

テストは人工データと置き換えた生成処理を使うため、実際の接続先の認証・通信・生成品質は確認できません。実データはリポジトリに保存しないでください。

本 CLI は Bridge 0.10.0 を使用し、単一文書・連続ページ・比較ではテキストのみを渡します。画像添付や VLM による解析はしません。Bridge は `pyproject.toml` の固定コミット ZIP URL から取得します。参照コミットを更新する際は `uv.lock` も変更し、テストと再インストールを行ってください。

### editable インストール

ソース変更をインストール済み CLI へすぐ反映したい開発時に使います。

```shell
cd "C:\path\to\tkn_doc_summarizer"
uv tool install -e . --reinstall
```

通常のソース変更は再インストールせずに反映されます。依存関係・パッケージ定義・実行コマンドを変えた場合、またはリポジトリを移動・改名した場合は再インストールしてください。

## 同梱の要約プロファイルを変更する

生成指示、JSON 出力形式、Markdown テンプレートは1組のリソースです。単一文書・連続ページは `src/doc_summarizer/summary_profiles/`、比較は `src/doc_summarizer/comparison_profiles/` にあり、それぞれ `default-ja/` と `default-en/` を持ちます。

| ファイル | 担当 |
| --- | --- |
| `prompt.md` | 生成指示と出典に沿う規則 |
| `output.schema.json` | AI が返す JSON の項目・型・階層 |
| `template.md` | Markdown の見出し・順序・配置 |

読み込み時に各リソースを検証し、SHA-256 からプロファイル全体のハッシュを計算します。ハッシュは既存ノートの再利用判定に使うため、出力形式やテンプレートの変更も検出できます。`config list` でリソースの場所、ID、版、ハッシュを確認できます。

項目を変更するときは、プロンプト、出力スキーマ、Pydantic モデル、描画、検証、テストを合わせて更新します。配置だけを変える場合も、テンプレート、描画、検証、テストの整合を確認してください。
