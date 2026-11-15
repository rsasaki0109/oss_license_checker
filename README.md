# oss-license-checker

![OSS License Checker — ライセンスを一覧化し、リリース前にポリシー違反を検出するCLIのデモ](docs/assets/hero.gif)

[![Tests](https://github.com/rsasaki0109/oss_license_checker/actions/workflows/test.yml/badge.svg)](https://github.com/rsasaki0109/oss_license_checker/actions/workflows/test.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-9de9b5?logo=python&logoColor=white&labelColor=121b26)
![Dependency traversal](https://img.shields.io/badge/dependencies-transitive_scan-9de9b5?labelColor=121b26)

**Know what ships.** 依存ライセンスの可視化から、リリース前のポリシー検査まで。

Python環境にインストールされたパッケージのライセンスを一覧化し、CIで許可・禁止ルールを検査するCLIです。Python 3.11以上。パッケージのコードは実行せず、ローカルの配布メタデータを読み取ります。依存指定の解析には `packaging` を使用します。

## インストールと実行

```bash
python -m pip install -e .
oss-license-checker
oss-license-checker requests --format json
oss-license-checker --format csv --output licenses.csv
```

対象プロジェクトの仮想環境に依存パッケージと本ツールをインストールして実行してください。引数なしでは、その環境の全パッケージ（推移依存、開発用ツール、本ツール自身を含む）を検査します。名前だけ指定した場合は指定パッケージのみ検査します。

## プロジェクトの推移依存を検査

```bash
oss-license-checker requests --recursive --format json
oss-license-checker 'httpx[http2]' --recursive --fail-unknown
```

`--recursive` はルートパッケージと、その `Requires-Dist` を再帰的に検査します。現在のPython・OSに適用される環境マーカーと、明示したextrasを評価します。循環依存でも停止します。未インストールの依存、バージョン条件の不一致、不明なextrasは終了コード2で報告します。レジストリへの問い合わせや自動インストールは行いません。直接URLの依存は名前で照合し、インストール元URLの一致は検証しません。

## ポリシーを保存

`pyproject.toml` に以下を追加できます。

```toml
[tool.oss-license-checker]
allow = ["MIT", "Apache-2.0", "BSD-3-Clause"]
deny = ["GPL-3.0-only"]
fail-unknown = true
```

```bash
oss-license-checker your-package --recursive --config pyproject.toml
```

専用のTOMLファイルではテーブル見出しを省略し、同じ3つのキーをトップレベルに置きます。設定は `--config` で明示した場合のみ読み込みます。CLIの `--allow` / `--deny` は対応する設定リストを置き換えます。`--fail-unknown` / `--no-fail-unknown` で設定値を上書きできます。未知のキーや型の誤りは終了コード2になります。

## CIでの利用

```bash
oss-license-checker --allow MIT --allow Apache-2.0 --allow BSD-3-Clause \
  --deny GPL-3.0-only --fail-unknown --format json --output licenses.json
```

- `--allow` / `--deny` は繰り返し指定できます。識別子は大文字小文字を区別します。
- 許可リストを指定すると、リスト外のライセンスは拒否されます。禁止指定は許可指定より優先します。
- `AND` は両方の許可、`OR` はいずれかの許可が必要です。例えば `MIT OR GPL-3.0-only` はMITが許可されていれば通ります。禁止指定はOR式全体の無条件拒否を意味しません。
- 括弧と `WITH` に対応します。例外付きライセンスを許可するには `--allow 'Apache-2.0 WITH LLVM-exception'` のように全体を指定してください。基底ライセンスの禁止は例外付きにも適用します。
- `--fail-unknown` は不明なライセンスもCIエラーにします。

終了コード: `0` = 検査通過、`1` = ルール違反または不明（`--fail-unknown`時）、`2` = 未インストールのパッケージやファイル出力などの実行エラー。

## 判定の範囲

`License-Expression` を優先し、次に古い `License`、ライセンス関連の `Classifier` を証拠として記録します。古い `License` は許可・禁止リストとの完全一致でのみ判定し、自由文とClassifierは不明として扱います。ライセンス本文の同定、SPDX識別子の公式一覧との照合、法的な互換性判定、NOTICEの作成は行いません。`allowed` は指定ポリシーに適合する意味です。ポリシー未指定時は認識できる式を許可します。

メタデータが欠落・不正確な場合もあるため、配布物のLICENSE/NOTICEや利用条件の確認には別途レビューが必要です。CSVにはメタデータをそのまま出力するため、信頼できない依存パッケージのレポートを表計算ソフトで開く場合は文字列として取り込んでください。

## 開発

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

READMEのGIFは架空のパッケージメタデータに対する実際のCLI判定を使ったデモです。開発用にPillowをインストールし、`python scripts/render_hero.py` で再生成できます（DejaVuフォントが必要）。PillowはCLIの実行依存には含みません。
