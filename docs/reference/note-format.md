# 要約ノートの形式

生成ノートは YAML Frontmatter と Markdown 本文で構成します。ここでは現在の新規出力を示します。値を `<...>` とした例は形を示すもので、実際の生成結果ではありません。

| コマンド | 形式 | `schemaVersion` | 出典 |
| --- | --- | --- | --- |
| `summarize` | 単一文書 | `"8.0"` | `source` と `sourceSha256` |
| `synthesize`（既定） | 連続ページ | `"9.0"` | 順序付きの `sources` |
| `synthesize --mode compare` | 比較 | `"7.0"` | 出典 ID 付きの `sources` |

版番号は数値ではなく文字列です。`validate` は旧形式の `schemaVersion` 2.0〜9.0 も各版の規則で検証します。

## Frontmatter の例

単一文書の全項目を、出力順で示します。Windows の `source` は既定でネイティブパスです。`url` は元記事の URL があればその値、なければ元ファイルの `file:` URI です。

```yaml
---
type: summary
schemaVersion: "8.0"
title: "バックアップと復元確認"
description: "結論から作られた短い説明"
cover: null
url: "file:///C:/path/to/article.md"
cliptool: Codex
source: 'C:\path\to\article.md'
sourceSha256: "<sha256>"
generator: "<接続先とモデル>"
promptId: "<uuid>"
promptVersion: "<version>"
promptSha256: "<sha256>"
summaryProfile: "default-ja"
summaryProfileSha256: "<sha256>"
outputSchemaId: "<uuid>"
outputSchemaVersion: "<version>"
outputSchemaSha256: "<sha256>"
templateId: "<uuid>"
templateVersion: "<version>"
templateSha256: "<sha256>"
promptEnvelopeVersion: "<version>"
reviewStatus: unreviewed
date: "<作成日時>"
updated: "<更新日時>"
noteId: "<uuid>"
---
```

連続ページと比較では、上の `source`・`sourceSha256` に代わり、`cliptool` の直後に次の項目を置きます。`sources` の順序は入力引数の順序です。その後に `generator` 以降の共通項目が続きます。比較形式には `outputSchemaId`・`outputSchemaVersion` がありません。

```yaml
synthesisMode: series # 比較は compare
sourceSetId: "<uuid>"
sourceSetPublished: null
sourceSetSha256: "<sha256>"
sources:
  - id: "S1"
    source: 'C:\path\to\page-1.md'
    sourceSha256: "<sha256>"
  - id: "S2"
    source: 'C:\path\to\page-2.md'
    sourceSha256: "<sha256>"
```

上のブロックは Frontmatter の差分です。コメントと `<...>` は説明用です。

## 項目一覧

| 項目 | 単一 | 連続・比較 | 意味 |
| --- | --- | --- | --- |
| `type`, `schemaVersion` | ○ | ○ | ノート種別 `summary` と検証形式の版 |
| `title`, `description` | ○ | ○ | 表示名と一覧用の説明。単一・連続は結論、比較は生成された説明を空白整理して最大240文字に短縮 |
| `cover`, `url`, `cliptool` | ○ | ○ | 表紙、代表出典への参照、生成ツール `Codex` |
| `source`, `sourceSha256` | ○ | — | 元文書の絶対パスと内容の SHA-256 |
| `synthesisMode` | — | ○ | `series` または `compare` |
| `sourceSetId`, `sourceSetPublished`, `sourceSetSha256` | — | ○ | 順序付き出典の組の識別子、代表公開日、内容ハッシュ |
| `sources` | — | ○ | 各出典の `id`、絶対 `source`、`sourceSha256` |
| `generator` | ○ | ○ | 実際の生成先。モデル名を取得できた場合は含む |
| `promptId`, `promptVersion`, `promptSha256` | ○ | ○ | 生成指示の識別・版・内容ハッシュ |
| `summaryProfile`, `summaryProfileSha256` | ○ | ○ | 言語・形式を選ぶプロファイルとそのハッシュ |
| `outputSchemaId`, `outputSchemaVersion` | ○ | 連続のみ | 生成 JSON スキーマの識別・版 |
| `outputSchemaSha256` | ○ | ○ | 生成 JSON スキーマの内容ハッシュ |
| `templateId`, `templateVersion`, `templateSha256` | ○ | ○ | Markdown テンプレートの識別・版・内容ハッシュ |
| `promptEnvelopeVersion` | ○ | ○ | 入力を生成指示へ渡す際の包み方の版 |
| `reviewStatus` | ○ | ○ | 人による確認状態。生成直後は `unreviewed` |
| `date`, `updated`, `noteId` | ○ | ○ | 作成日時、更新日時、ノート UUID |

`reviewStatus` の有効値は `unreviewed`、`pending`、`reviewing`、`accepted`、`needs-revision`、`rejected` です。確認後に変更できますが、明示的な `--overwrite` は確認済み内容も再生成し、`unreviewed` に戻します。

`source` と `sources[].source` は既定で OS の絶対パスです。`source_path_format: file-uri` なら `file:///C:/path/to/article.md` のような URI になり、両形式を検証できます。設定変更だけでは既存ノートを書き換えません。

## 本文の構成

| 形式 | 日本語版の見出し順 |
| --- | --- |
| 単一・連続 | 要約 → 結論 → 要点 → 構造（抽象から具体へ）→ 専門用語 |
| 比較 | 比較要約 → 共通概念 → 観点別の捉え方 → 相違・対立 → 各ソース固有の知見 → 専門用語 → 結論 |

英語プロファイルでは本文と見出しを英語にします。比較では主張に `[S1, S2]` のような出典 ID を付けます。表紙がある場合はタイトル直下に表示します。単一・連続の日本語プロファイルは要約約250〜400字、要点5〜8件、専門用語3〜7件などを生成指示の目安にします。文書が短い場合に無理に満たす条件ではありません。

単一・連続の英語要約は約120〜200語を目安にします。結論は概要の直後に置き、日本語は通常2〜3段落・約300〜500字、英語は約150〜250語を目安に、結論・根拠と原文にある場合の実用上の含意をまとめます。構造の節は大分類の H3 と、必要に応じた中分類の H4・箇条書きで整理します。動画埋め込みやタイムスタンプは作りません。付随する広告・勧誘は除外しますが、それ自体が主題なら説明に残します。

出典の本文全体や分類用の `nouns` はノートの Frontmatter へ追加しません。Frontmatter と本文の構造は [ノートの検証](../../src/doc_summarizer/validation.py)で確認できます。
