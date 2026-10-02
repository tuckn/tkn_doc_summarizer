# 日常利用と再実行

初回のインストールと単一文書の作成は [README](../../README.md#セットアップ) を参照してください。通常実行では生成先へ文書を渡し、利用枠や費用を消費します。`--dry-run` は設定・入力・保存予定先を検査し、外部 CLI の起動・認証・通信やファイルの作成はしません。

## 保存済み記事を URL で指定する

`source_roots` に設定したフォルダで保存済み Markdown を再帰検索します。入力の Frontmatter には元記事の `url` が必要で、本文は区切りの後に続けます。

```yaml
---
title: バックアップと復元確認
url: https://example.com/article
---
```

```shell
tkn-doc-summarizer summarize "https://example.com/article"
```

一致する文書が1件なら要約します。0件または複数件なら停止します。URL のフラグメントや `utm_` で始まる追跡パラメーターなどを除いて照合します。`cliptool: Codex` を持つ生成ノートは検索対象外です。Web ページ自体の取得はしません。見つからない場合は保存内容を確認するか、ファイルパスを直接指定してください。

## 連続ページを統合する

```shell
tkn-doc-summarizer synthesize "<page-1>" "<page-2>"
```

2件以上の文書パスまたは保存済み記事の URL をページ順に指定します。既定の `series` モードでは、引数の順序をページ順として扱います。同じローカルファイルを重複指定すると停止します。ページ共通の重複を抑え、ページをまたぐ論旨を保持するよう生成を依頼します。

## 独立した記事を比較する

```shell
tkn-doc-summarizer synthesize "<article-a>" "<article-b>" --mode compare
```

2件以上の文書に `S1`、`S2`…の出典 ID を付けて比較します。引数の順序が ID を決めますが、権威・優先順位・時系列は意味しません。共通概念、観点、相違・対立、各出典固有の知見を整理します。根拠のない対立を作らないよう生成を依頼します。比較モードではカスタム `summary_prompt` を使えないため、設定値は `null` にします。

両モードとも `--title "<title>"` でタイトルを指定できます。省略すると AI が全体から決めます。新規ノートの `--dry-run` では先頭文書のタイトルに基づく暫定パスが表示され、`details.generated_title_pending` が `true` になります。

## 言語と保存先を変更する

```shell
tkn-doc-summarizer summarize "<source-file>" --summary-profile default-en
tkn-doc-summarizer summarize "<source-file>" --output "<output-file>.md"
```

言語別のノートは共存できます。`--output` は特定ファイル、`--output-root "<output-directory>"` は自動命名するフォルダをその実行だけ変更します。`synthesize` でも使えます。保存先の詳細は [出力と実行結果](../reference/output-and-results.md)を参照してください。

## 既存ノートを再実行する

| 状態 | 通常実行の動作 |
| --- | --- |
| 対応するノートがない | AI で生成して新規作成 |
| 入力・生成条件が一致し検証にも成功 | `unchanged`。AI を呼び出さず再利用 |
| 入力、プロンプト、出力形式、明示したモデルなどが変わった | 上書きせず停止。再生成には `--overwrite` が必要 |
| 対応するノートの検証が失敗 | 自動置換せず停止 |
| 指定先が別の文書・文書の組・モード・プロファイル・プロンプト ID に属する | `--overwrite` でも置換せず停止 |
| 同じ識別情報のノートが複数ある | 暗黙に選ばず停止 |

**`--overwrite` は手動編集や確認済みの内容も置き換え、`reviewStatus` を `unreviewed` に戻します。** 自動バックアップは作りません。必要な版を別に保存してから実行してください。入力や生成条件が一致しても、`--overwrite` があれば再生成します。

```shell
tkn-doc-summarizer summarize "<source-file>" --overwrite --dry-run
tkn-doc-summarizer summarize "<source-file>" --overwrite
```

`synthesize` も同じ指定を使えます。同じノートの更新では `noteId` と作成日時 `date` を保持し、`updated` を更新します。既存ノートの識別条件は [出力と実行結果](../reference/output-and-results.md#ファイル名と既存ノートの識別)にまとめています。

## 失敗や中断からやり直す

エラーの理由と、表示されていれば JSON レポートのパスを確認します。入力・認証・保存先などの原因を直して同じコマンドを再実行します。途中の生成結果を再開する機能はなく、完成したノートが再利用できなければ生成をやり直します。

ノートは全体を組み立てて検証してから置き換えます。保存後の再検証やレポート保存で失敗した場合はノートだけ残ることがあります。中断後にノートがあれば `tkn-doc-summarizer validate "<summary-note>"` で確認してください。レポートと終了コードは [出力と実行結果](../reference/output-and-results.md#表示と実行レポート)を参照してください。
