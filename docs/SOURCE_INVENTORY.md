# ソース公開のための確認候補を作る

`--source-tree` は、Gitの固定コミットに含まれるファイルを棚卸しし、[配布対応記録](DISTRIBUTION_REVIEW_DESIGN.md) の未確認項目へつなげます。インストール済みPython依存の検査とは別のモードです。

```bash
oss-license-checker --source-tree /path/to/repository --source-ref HEAD \
  --format json --output source-inventory.json
oss-license-checker --source-tree /path/to/repository --source-ref HEAD \
  --format html --output source-inventory.html
```

`--source-tree` はリポジトリのルートを指定します。refは既定でHEAD、ブランチやコミットSHAも指定できます。作業中の変更・未追跡ファイルは含めません。疎なチェックアウトでも、手元にあるGit treeの全追跡エントリを調べます。Gitが必要ですが、パッケージのインストールやソースコードの実行は行いません。

## 出力

- 解決したコミットとtreeのID、全エントリのパス・mode・Git object ID。
- パス一覧を含む正規化JSONから計算したSHA-256。公開するアーカイブ自体のハッシュとは区別します。
- LICENSE・NOTICE等の名前、外部コードを示唆するディレクトリ名、画像・データ・バイナリの拡張子に基づく確認候補。
- リンクとサブモジュールを別途確認するための候補。リンク先やサブモジュール内には入りません。
- `review_draft`：候補をすべて `needs_review` にした配布対応記録。候補が0でも範囲確認の1件は残します。

JSONには全一覧と記録のドラフトを含みます。HTML・Markdown・ターミナルは範囲・限界と候補を表示し、CSVは候補一覧のみです。完全なprovenanceが必要な場合はJSONも保存してください。

通常は検査を実行できれば終了コード0、無効なref・非Gitディレクトリ・不適切なオプション等は2です。差分モードの `--fail-on-change` は変更時に1を返します。0は「棚卸しを作れた」という意味で、配布承認ではありません。常に `distribution_readiness: not_assessed` とし、第三者素材や違反を自動断定しません。検査対象コミットにあるファイルを `--output` で上書きする指定も拒否します。

## 前回のソースとの差分

```bash
# 親コミットの棚卸しを基準として保存（親のGitオブジェクトが手元に必要）
oss-license-checker --source-tree /path/to/repository --source-ref 'HEAD^' \
  --format json --output source-baseline.json

# 現在のコミットを比較。変更があれば1を返し、レポートは保存する
oss-license-checker --source-tree /path/to/repository --source-ref HEAD \
  --baseline source-baseline.json --fail-on-change \
  --format json --output source-changes.json
```

- 追跡パスの `added` / `removed` / `changed` を検出します。変更の判定はGit object ID・mode・object typeで行い、内容・実行権限・リンクやサブモジュールの参照変更を拾います。renameは削除と追加として扱います。
- ヒューリスティックの候補に一致しない通常のコードも比較します。候補0件でも、公開ソースへの新しいコピー等を見逃さないためです。ただし差分の検出自体はライセンス変更や違反の判定ではありません。
- JSONの `changes` に変更前後のエントリを残します。HTML・Markdown・ターミナル・CSVでは変更行と現在の候補を表示し、変更行の種類は `added` / `removed` / `changed` です。
- 変更した各パスは `review_draft` に新しい未確認記録として追加します。過去の完了・承認状態は自動で引き継ぎません。差分がなくても現在の候補と範囲確認の未確認記録は残ります。
- 基準にはソース検査のJSONのみを使えます。GitコミットID・tree・一覧・件数・一覧ハッシュを、手元のGitオブジェクトから再確認します。異なる内容の一覧、不正なJSON、パッケージ一覧、基準を出力先で上書きする指定は終了コード2です。
- 比較元のコミットがないshallow cloneでは、そのコミットを明示的にfetchしてから再実行してください。基準は入力として固定し、人が編集したレビュー記録とは別に管理します。検証するのはGit snapshotとの一致で、過去のレビュー判断の正当性ではありません。

## 配布対応記録へつなげる

```bash
python -c 'import json; r=json.load(open("source-inventory.json")); json.dump(r["review_draft"], open("source-review.json", "w"), indent=2)'
python -m pip install -e '.[test]'
python scripts/validate_distribution_review.py source-review.json
```

ドラフトを別ファイルに保存し、各候補の出典・適用条件・対応内容・実配布物を確認して記録を更新します。再検査は新しいJSONへ出力し、人が更新したレビュー記録を自動で上書きしない運用にします。Python依存検査の基準JSON・ポリシー・ZIP収集とは混在させません。

基準の `review_draft` から作ったレビュー記録は、次の検査で参照できます。記録内の配布IDと `source-tree` の参照先は、元の基準コミットとツリーの値を保持してください。

```bash
oss-license-checker --source-tree /path/to/repository \
  --baseline source-baseline.json --prior-source-review source-review.json \
  --format html --output source-follow-up.html
```

前回の未完了項目は `open`、完了・対象外だった項目はツリーに変更があれば `recheck`、同じツリーなら `historical` と表示します。候補に直接関係するパスが変わった項目には印を付けます。ツリーが変わった場合は、候補のパスに差分がなくても、配布物全体に結びつく完了記録を再確認します。JSONの `prior_review` には前回の項目IDと状態が入ります。新しい `review_draft` は今回の確認用で、元の記録はそのまま参照できます。終了コードは従来どおり検査の成否と `--fail-on-change` で決まります。

## Calibrexでの受け入れ確認

コミット `75bbb1528f967ace2439b69627529a5d65585531` で、28,434エントリ・確認候補10件・範囲確認を含む11件の未確認記録を確認しました。

- `docs/assets/evidence-demos/source/comma/LICENSE` を本文確認候補として取得。
- `tools/external` を外部素材の候補として取得。
- `docs/assets`・リソース・データ類を確認候補にし、由来や権利を断定しない。
- `license_boundaries.md` のような説明文も名前で候補になり得ます。本文がライセンスそのものとは自動判定しません。

同じコミットの再比較では変更0件・終了コード0でした。親コミット `0e90966d6bb56a4529ea25c3f77c21167ed1cd97` との実履歴比較では、README・`docs/getting_started.md`・`docs/tutorials/your_own_data.md` の3件の変更を検出し、`--fail-on-change` で1を返しました。候補10件と範囲確認に変更パス3件を加えた14件の未確認記録を生成し、記録の検証も通過しました。この履歴差分をライセンス違反とは判定していません。

これは権利者の網羅的な同定や、ソースコピーの類似性検出ではありません。名前を変えた第三者コード、未対応の拡張子、独自の同梱形式は見逃す可能性があります。候補数が少ないことやファイルが見つからないことを、義務がない証拠には使いません。合成fixtureの由来などは、manifest・生成元を引き続き確認します。
