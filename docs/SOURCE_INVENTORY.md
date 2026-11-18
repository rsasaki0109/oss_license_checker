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

検査を実行できれば終了コード0、無効なref・非Gitディレクトリ・不適切なオプション等は2です。0は「棚卸しを作れた」という意味で、配布承認ではありません。常に `distribution_readiness: not_assessed` とし、第三者素材や違反を自動断定しません。検査対象コミットにあるファイルを `--output` で上書きする指定も拒否します。

## 配布対応記録へつなげる

```bash
python -c 'import json; r=json.load(open("source-inventory.json")); json.dump(r["review_draft"], open("source-review.json", "w"), indent=2)'
python -m pip install -e '.[test]'
python scripts/validate_distribution_review.py source-review.json
```

ドラフトを別ファイルに保存し、各候補の出典・適用条件・対応内容・実配布物を確認して記録を更新します。再検査は新しいJSONへ出力し、人が更新したレビュー記録を自動で上書きしない運用にします。既存のPython依存向け `--baseline`・ポリシー・ZIP収集とは混在させません。

## Calibrexでの受け入れ確認

コミット `75bbb1528f967ace2439b69627529a5d65585531` で、28,434エントリ・確認候補10件・範囲確認を含む11件の未確認記録を確認しました。

- `docs/assets/evidence-demos/source/comma/LICENSE` を本文確認候補として取得。
- `tools/external` を外部素材の候補として取得。
- `docs/assets`・リソース・データ類を確認候補にし、由来や権利を断定しない。
- `license_boundaries.md` のような説明文も名前で候補になり得ます。本文がライセンスそのものとは自動判定しません。

これは権利者の網羅的な同定や、ソースコピーの類似性検出ではありません。名前を変えた第三者コード、未対応の拡張子、独自の同梱形式は見逃す可能性があります。候補数が少ないことやファイルが見つからないことを、義務がない証拠には使いません。合成fixtureの由来などは、manifest・生成元を引き続き確認します。
