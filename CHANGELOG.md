# Changelog

## 0.5.0

- `conversation-ja` を追加しました。単一の文字起こしと、`synthesize --mode series` で入力順に並べた複数録音から、概要・話題別記録・約束／予定／願望・未確認事項を作ります。専用のプロンプト、JSON の型、テンプレートを持ち、結論や専門用語は要求しません。
- 各項目に出典ID、ファイル内時刻、元の話者ラベル、実名同定の確認状態、発言の対象と留保を残します。異なるファイルの同じ話者ラベルを同一人物と扱わず、人物分析・プレゼント提案を記録に混ぜない方針です。
- `--conversation-date YYYY-MM-DD` を追加しました。会話日と文字起こし・要約生成日を分け、会話日を自動ファイル名に反映します。省略時の会話日は未確認です。
- 会話用の新規出力は `schemaVersion` 10.0（単一）／11.0（複数）です。生成時と保存済みノートの検証で出典ID・時刻・話者ラベルを照合します。従来の出力も引き続き検証できます。
- インストール済み CLI への反映は `uv tool install . --reinstall` です。通常の生成は外部接続を使い、`--dry-run` は生成・書き込みを行いません。

## 0.4.0

- `synthesize --mode compare --extend-sources --output FILE --overwrite` で、出典を追加した比較・主張整理ノートを同じファイルへ更新できます。既存の出典をすべて含み、追加があることを検査し、モード・profile・promptの識別チェックも維持します。
- 更新時は `noteId` と `created` を保持し、`updated` を更新して `reviewStatus` を `unreviewed` に戻します。既存ファイル・明示した保存先・上書き指定が必要です。`--dry-run` では生成も書き込みも行いません。
- 比較ノートの生成中に保存先が編集・削除された場合、その変更を上書きせず停止します。

## 0.3.0

- `synthesize --sources-file FILE` で、UTF-8の一覧から複数の入力を読み込めます。1行1パスまたはURL、空行・`#`で始まるコメント行、BOMに対応し、相対パスは一覧ファイルの場所を基準に解決します。位置引数との混在と重複入力はエラーです。
- `synthesize --mode compare --comparison-profile claims-ja` を追加しました。同一話者の要約群から、繰り返される主張、論点別の論拠、留保、個別動画の主張を整理します。
- `claims-ja` は各項目から元ノートへ直接リンクし、参照した要約一覧とreviewStatusを出力します。同じドライブではノート間の相対リンク、異なるドライブではfile URIを使います。入力全件が本文のいずれかで参照されていることも検証します。
- インストール済みCLIへの反映は `uv tool install . --reinstall` です。
- Windows junction等の別名パスをネイティブ出典参照でも保持し、複数文書の出典ハッシュとの不一致で保存できない問題を修正しました。

## 0.2.2

- ノート生成日時を `date` から `created` に変更し、日時はダブルクォート、Windows パスはシングルクォートで出力します（URL スキーム付きの値を除く）。
- 旧 `date` の読み込みと検証を継続し、再生成時は作成日時の表記・精度を保持して `created` へ移します。


## Unreleased

- アプリ設定を `schema_version: "2.0.0"` に変更しました。`generation.summary`／`generation.comparison` にそれぞれ `default_profile` と `profiles` を置き、各プロファイル内で Bridge の接続先と要約／比較の出力形式をまとめて指定します。`--profile` は実行モード側のプロファイルを選びます。比較の形式・接続先・モデルは要約側から独立し、要約用の `summary_prompt` 設定も比較には適用しません。
- 旧 `generation.active_profile`／`generation.profiles`／`generation.summary_profile`、トップレベルの旧 AI 設定、`--codex-executable`／`--codex-timeout-seconds` は廃止しました。既存の設定は保存先等を維持して手動移行してください。`config list` の `generationResolved` は `summary`／`comparison` 別に表示します。
- 生成コマンドを `summarize` に統一し、`synthesize` は廃止しました。既定の `--mode series` は1件なら単一要約、複数件なら入力順の統合要約を生成し、`--mode compare` は2件以上を比較します。位置引数と `--sources-file FILE` のどちらでも入力でき、実行レポートの `command` も `summarize` になります。既存のノート形式と再利用条件は維持します。
- 同梱リソースを `src\profiles\summary\<profile名>\` と `src\profiles\comparison\<profile名>\` に整理しました。要約用は単一・複数入力で共用します。CLI の profile 名、リソース内容・ID・ハッシュは変えず、リソース参照は `package:profiles/summary/...` / `package:profiles/comparison/...` へ更新しました。
- README に、文字起こし1件を `conversation-ja` と補足 context で要約する、パス・内容を匿名化した PowerShell の実行例を追加しました。
- `meeting-minutes-ja` を追加しました。単一・複数文字起こしを指定する `summarize --mode series` から、概要（箇条書き）・会話で確認できた事実・認識差／未決事項・RAID・次回確認事項を生成します。根拠種別と確度、担当・期限を区別する専用プロンプト・JSON スキーマ・テンプレートを持ち、会話日も指定できます。ノート形式は単一が12.0、複数が13.0です。
- 全要約 profile と比較に、実行ごとの `--context TEXT_OR_FILE` を追加しました。テキストまたは UTF-8 ファイルのパスを複数指定でき、指定順に空行で結合します。パス形式なのに存在しない場合はエラーです。補足を原文と区別して生成・dry-run に渡し、補足本文内の参照パスの再帰的な読込や PPTX／DOCX の抽出は行いません。従来の `--context-file FILE` は廃止し、`--context FILE` に集約しました。
- context のハッシュをノートと実行結果に記録し、補足の追加・変更・削除にも明示的な `--overwrite` を要求します。補足全文は Frontmatter・実行レポートへ保存せず、context なしの既存ノートの検証・再利用を維持します。
- `config show` を `config list` に変更しました。旧コマンドは受け付けません。既存の手順・スクリプトは `config list` に変更してください。
- 設定一覧の既定出力を、1行ごとの `key=value` に変更しました。入れ子・配列も展開し、Windows パスはそのままコピーできます。従来の JSON 出力を利用する処理は `config list --json` に変更してください。
- 一覧表示の案内は標準エラーへ INFO レベルで表示します。`--quiet` でログを省略できます。
- インストール済み CLI へ反映するには、リポジトリで `uv tool install . --reinstall` を実行してください。旧設定を使っている場合は、[設定の移行手順](docs/reference/configuration.md#旧形式からの移行)に従って新形式へ変更してください。

過去のリリース履歴は、この変更履歴では未整理です。
