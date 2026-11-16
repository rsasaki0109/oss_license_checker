# 変更履歴

## 未リリース

以下は初回リリースに向けてまとめた変更です。

### 機能

- インストール済みPythonパッケージと推移依存のライセンス検査。extrasと環境マーカーに対応。
- SPDX識別子・例外名・式の検証、許可・禁止ポリシー、不明ライセンス検出。
- TOML設定と、根拠・確認バージョンを記録するパッケージ単位のライセンス補正。
- ターミナル・JSON・CSV・HTML・Markdownレポート。
- 前回のJSONとの差分検出、変更時のCIエラー。
- LICENSE・NOTICE等を元のバイト列でZIP収集し、取得元・SHA-256・欠落をmanifestに記録。
- 再利用可能なGitHub Action、Job Summary表示、artifact保存。
- `--version` と `python -m oss_license_checker` に対応。MITライセンス。

### 導入と互換性

- Python 3.11以上。実行依存は `packaging>=24.2`。ビルドには `setuptools>=77` が必要。
- 旧来の `License` 欄も、SPDX式として検証可能なら判定。自由文やClassifierは不明のまま保持。
- JSON・CSVに `reason`・`effective_license`・`override_reason` を含む。差分JSONは配列ではなく `packages` / `changes` を持つオブジェクト。
- 以前のJSON一覧も基準として利用可能。`effective_license` がない行は元の `license` を使って比較。
- 補正対象のバージョンが変わると終了コード2になり、再確認が必要。

### 確認範囲と制限

- LinuxでPython 3.11〜3.13、最小依存版 `packaging==24.2` をCI検証。macOSではPython 3.12を検証。
- Requests・HTTPX・Richの配布物と実行時依存をLinux・macOSで検証。
- 依存の自動インストール、ライセンス本文の自動同定、法的な互換性判断は行わない。
- 本ツールによるライセンス検査はローカルメタデータを使う。導入やCIの依存取得・artifact保存にはネットワークが必要。
- Windowsは現在のCI確認範囲に含まれない。
- 初見の人による「10分で導入」の確認は未実施。

検証済みコミットと公開前の残作業は [リリース候補の確認記録](docs/RELEASE_CANDIDATE.md) を参照してください。
