# 実プロジェクト検証

2026-11-15、Linux / Python 3.12、プロジェクトごとに独立した仮想環境で実施。ソースから作ったwheelをインストールして検査しました。対象は公開されているライブラリの配布物と実行時依存です。各プロジェクトのソースリポジトリ全体や開発用依存を検査したものではありません。

| 対象 | バージョン | 推移依存込みの件数 | 収集ファイル数 | 厳格なポリシー検査 |
| --- | --- | ---: | ---: | --- |
| Requests | 2.34.2 | 5 | 6 | 通過 |
| HTTPX | 0.28.1 | 7 | 7 | 通過 |
| Rich | 15.0.0 | 4 | 6 | 確認済み補正2件を適用して通過 |

3件それぞれで、許可リスト・不明ライセンスの検出・証拠ファイル欠落検出、収集した全ファイルのSHA-256、差分なしの終了コード0、バージョン差分ありの終了コード1、禁止ポリシーの終了コード1、Markdown・HTML出力を確認しました。これは利用条件の法的な互換性を保証するものではありません。

## 見つかった問題と対応

古い `License` 欄の `MIT` / `Apache-2.0` / `MPL-2.0` / `BSD-3-Clause` が、ポリシーに同じ文字列がなければ不明扱いでした。公式SPDX識別子・式として検証できる場合は、大文字小文字を正規化して判定するよう修正しました。自由文とClassifierは引き続き推測で変換しません。

Richの依存である `markdown-it-py==4.3.0` と `mdurl==0.1.2` はClassifierのみでした。配布物のLICENSEの許諾・免責条項を確認し、MITのバージョン限定補正を設定しました。確認元とSHA-256は [Richの設定](../examples/validation/rich/policy.toml) に記録しています。更新時には再確認が必要です。

本ツール自身のLICENSEはユーザーの指定に従いMITとし、配布メタデータにSPDX式とLICENSEファイルを含めました。

既存CIのAction動作確認は、Classifierしか持たない `packaging==24.2` を厳格な検査で通す想定になっていました。成功ケースの対象を本ツールのwheel（MIT）に変更しました。Classifierのみなら不明とする動作は回帰テストで確認します。

## 再現方法

リポジトリのルートで実行します。`PROJECT` を `requests` / `httpx` / `rich` に切り替え、別々の仮想環境を使ってください。

```bash
python -m pip install build
python -m build
PROJECT=requests
python -m venv "/tmp/license-validation-$PROJECT"
"/tmp/license-validation-$PROJECT/bin/python" -m pip install \
  -r "examples/validation/$PROJECT/requirements.txt" dist/*.whl
python scripts/validate_real_project.py \
  --python "/tmp/license-validation-$PROJECT/bin/python" \
  --project "$PROJECT" --output "/tmp/license-results-$PROJECT"
```

固定した依存バージョンと検証用ポリシーは `examples/validation/` にあります。ポリシーは検証用で、あらゆるプロジェクトへの推奨設定ではありません。パッケージはPyPIから取得するため、通信可能な環境が必要です。`summary.json` に実際のバージョン・件数・実施した検査を記録します。GitHub Actionsの `real projects` ワークフローも同じ手順を実行し、検査結果をartifactに保存します。

## 初回リリースまでの残り

- [リリース候補の確認記録](RELEASE_CANDIDATE.md) に記載したコミットで、macOS・Linuxの導入確認、単体テスト、配布物、実プロジェクトCIの成功を確認済み。
- 初めて導入する人の所要時間・使いやすさは [ユーザーテスト](USER_TEST.md) で確認する。未実施。
- [リリース手順](RELEASING.md) に沿って対象コミットを固定し、リリースする。通常の機能追加ではバージョンを変更しない。
