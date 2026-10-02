# Changelog

## Unreleased

- `config show` を `config list` に変更しました。旧コマンドは受け付けません。既存の手順・スクリプトは `config list` に変更してください。
- 設定一覧の既定出力を、1行ごとの `key=value` に変更しました。入れ子・配列も展開し、Windows パスはそのままコピーできます。従来の JSON 出力を利用する処理は `config list --json` に変更してください。
- 一覧表示の案内は標準エラーへ INFO レベルで表示します。`--quiet` でログを省略できます。
- インストール済み CLI へ反映するには、リポジトリで `uv tool install . --reinstall` を実行してください。設定ファイルの変更は不要です。

過去のリリース履歴は、この変更履歴では未整理です。
