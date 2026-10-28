# 文字起こしから会話記録を作る

`conversation-ja` は、会話の文字起こしから「短い概要＋根拠付きの会話記録」を作ります。複数録音は既存の `series` で入力順に一つの会合として扱います。手作業の結合は不要です。単一録音は `summarize` で処理できます。

## 録音順の一覧を用意する

UTF-8 の `sources.txt` に、文字起こしのパスを録音順に書きます。相対パスは一覧ファイルのフォルダを基準に解決します。録音が4件なら `S1`〜`S4` が対応します。

```text
# 録音順。引用符は付けない。
transcripts/recording-1.md
transcripts/recording-2.md
transcripts/recording-3.md
transcripts/recording-4.md
```

当時メモや事前の話題案は、この録音一覧に混ぜず、`--context` へテキストまたは UTF-8 ファイルのパスを指定して補足として渡せます。複数指定も可能です。補足があるだけで人物同定を確定扱いにはしません。

```shell
tkn-doc-summarizer synthesize --sources-file sources.txt --mode series --summary-profile conversation-ja --conversation-date 2026-10-17 --output "C:\path\to\conversation.md" --dry-run
tkn-doc-summarizer synthesize --sources-file sources.txt --mode series --summary-profile conversation-ja --conversation-date 2026-10-17 --output "C:\path\to\conversation.md"
```

`--dry-run` は外部生成や書き込みを行いません。通常実行は入力本文を選択した Bridge 接続先に渡します。全文を一度に渡す方式なので、入力上限内でも生成成功や網羅性は保証されません。

会話日は `--conversation-date YYYY-MM-DD` で明示します。文字起こしの生成日時から推定しません。Frontmatter の `conversationDate` は指定日または `null`、`created` / `updated` は要約ノートの作成・更新日時です。自動ファイル名は指定した会話日を優先します。会話日を省略すると `conversationDate: null` のまま保存し、ファイル名の日付は開催日の証明として扱いません。

単一録音の例です。

```shell
tkn-doc-summarizer summarize "<transcript-file>" --summary-profile conversation-ja --conversation-date 2026-10-17 --dry-run
```

`--mode compare` は `conversation-ja` に対応しません。`--conversation-date` は `conversation-ja` または後述の `meeting-minutes-ja` の実行時に指定できます。

## 出力と記録方針

| 節 | 内容 |
| --- | --- |
| 会合・資料情報 | 会話日、入力一覧と S番号の対応、ファイル内の時刻・話者ラベルの読み方 |
| 短い概要 | 数百字程度で話題の全体像を把握する説明 |
| 話題別の記録 | 近況、好み、趣味、困りごと、希望、思い出など。小さな具体も残す |
| 約束・予定・願望 | 明示的な約束・決定、予定案、願望を区別。該当なしも表示 |
| 未確認事項・読み取り上の制約 | 人物名、対象、作品名、意味の曖昧さ、誤認識など |

各記録項目は、発言内容、種別、話題の対象、話者名と同定状態、同定根拠、留保、出典を持ちます。種別は「発言・体験談／伝聞／冗談／推測／願望／予定案／約束・決定」です。現実の事実と、そう発言されたことを区別します。

次は人工例です。

```markdown
### 子どもの好み

- 子どもがあるキャラクターのグッズを欲しがる、と語られた。（種別: 発言・体験談 / 対象: 発言者の子ども（親の実名は未確認） / 話者: 不明・未確認 / 同定根拠: 実名との対応未確認 / 留保: 発言内容の事実性は未確認） [S2 00:18:48–00:19:24 / Speaker 3](file:///C:/path/to/recording-2.md)
```

`S2` と時刻の組が原文へ戻る手がかりです。リンク先は文字起こしファイルです。時刻への音声シークや行番号ジャンプは行いません。

- 時刻は各録音の先頭からの経過時間です。会合全体の累積時間や時計時刻へ換算しません。
- `S1 / Speaker 1` と `S2 / Speaker 1` は別の識別子です。同じファイル内の分離誤りや店員の発言もあり得るため、ラベル数から参加人数を確定しません。
- 実名は原則未確認です。推定には根拠と留保を残し、明示確認は引用範囲に直接の根拠がある場合に限るよう指示します。話題の一致だけで人物を確定しません。
- 「誰が話したか」と「誰について話したか」を分けます。子どもの好みを発言者本人の好みに付け替えません。
- 性格、隠れた意図、相手の評価、プレゼントの提案は記録に含めません。後から原資料と記録を使って検討します。
- 時刻自体がない入力では時刻不明と表示します。時刻付き入力の出典時刻を省略した結果は受け付けません。

## 検証と再実行

プロファイルは専用の `prompt.md`・`output.schema.json`・`template.md` を持ちます。JSON の各記録項目では evidence（source_id / start / end / speaker_label）と人物同定状態が必須です。記事用の結論や専門用語は要求しません。

生成時は JSON の型、入力全件の出典使用、未知の出典ID、時刻の前後関係、原文区間の開始・終了時刻、引用範囲に実在する話者ラベル、約束欄の種別を検査します。時刻のない入力に時刻を作ることも拒否します。

時刻とラベルの照合は、`tkn_audio_transcriber` が作る `[HH:MM:SS - HH:MM:SS] [Speaker N] 発言` の行形式を対象にします。時刻の小数表記や他形式のタイムコードはこの照合に対応していません。

```shell
tkn-doc-summarizer validate "C:\path\to\conversation.md"
```

保存済み Markdown の検証は Frontmatter・見出し・各記録項目の出典と帰属欄、引用リンクと S番号の対応、時刻・話者ラベル、原文ハッシュを照合します。発言の意味、引用範囲が要約を本当に裏付けるか、実名同定の妥当性、網羅性は自動判定できません。音声も再聴取しません。

入力・プロファイル・指定会話日が同じで検証に通る既存ノートは再利用します。日付や本文を変更して再生成する場合は `--overwrite` が必要です。更新時は `noteId` と `created` を引き継ぎ、`updated` を更新して `reviewStatus: unreviewed` に戻します。手動編集も置き換わります。

生成条件をカスタマイズする場合は `prompt init conversation.md --summary-profile conversation-ja` でコピーを作れます。`--summary-prompt` で変えられるのは生成指示で、会話用の JSON の型・テンプレート・検証は維持します。

## 会議後の議事メモを作る

業務会議の状況・事実・未決事項・対応を整理する場合は `meeting-minutes-ja` を使います。`conversation-ja` の詳細な会話記録とは別の profile です。

```shell
tkn-doc-summarizer summarize "C:\path\to\transcript.md" --summary-profile meeting-minutes-ja --conversation-date 2026-10-15 --context "会社Aから会社Bへの質問と認識合わせ。時間切れで終了。" --context "C:\path\to\context.md" --output "C:\path\to\meeting-minutes.md"
tkn-doc-summarizer synthesize --sources-file sources.txt --summary-profile meeting-minutes-ja --conversation-date 2026-10-15 --context "C:\path\to\context.md" --dry-run
```

出力は、概要（エグゼクティブ・サマリーの箇条書き）、会話で確認できた事実、認識差・未決事項、RAID（Risk / Action / Issue / Decision）、次回確認事項の5節です。概要には会話日・入力一覧・読み取り上の制約も併記します。会話日を省略すると未確認となります。

発言・資料記載・ユーザー補足・解釈と、確定／暫定／要確認を各項目に表示します。RAID の担当・期限が分からなければ会社名・役割または不明／未指定として残し、条件付きの方針を確定した決定にしないよう指示します。話者ラベルだけで実名や人数は断定しません。該当のない節は、その旨を表示します。

context は案件固有の手掛かり、表記、テキスト化した資料や別ツールの要約に使えます。`--context` 自体に指定したファイルは読み込みますが、その本文に書いた参照パスをさらに開く機能ではありません。[context の入力方法と扱い](../reference/configuration.md#実行ごとの補足-context)を確認してください。

生成時は専用 JSON の型、全入力の出典使用、未知・重複した S番号、補足だけの主張に出典を付けていないこと、事実の節へ補足・解釈を混ぜていないことを検査します。保存後は Frontmatter・見出し・概要の箇条書き・RAID の列・出典ID・原文ハッシュを検査します。`conversation-ja` と異なり、ファイル内時刻・話者ラベルの厳密な区間照合は行いません。数値の確度、発言の意味、根拠が主張を裏付けるか、人物の同定や RAID の分類の妥当性は元文書と照合してください。

補足の変更も既存ノートの更新条件です。同じ補足を渡せば再利用でき、追加・変更・削除して再生成するには `--overwrite` が必要です。`prompt init meeting.md --summary-profile meeting-minutes-ja` と `--summary-prompt` で指示を調整する場合も、議事メモの型・テンプレートは維持します。
