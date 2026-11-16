# 初回リリース候補の確認記録

確認日: 2026-11-16（日本時間）。

## 検証対象

対象コミット: [`05240a102a3bb40a54140d4484cc98a468190ae5`](https://github.com/rsasaki0109/oss_license_checker/commit/05240a102a3bb40a54140d4484cc98a468190ae5)。この記録を追加するドキュメントのコミットとは区別します。実際に公開するコミットを変える場合は、そのコミットのCIも確認します。

| 確認 | 結果 | 証拠 |
| --- | --- | --- |
| 単体テスト・Action・レポート | 5構成すべて成功。Linux Python 3.11〜3.13、最小依存版24.2、macOS Python 3.12 | [tests](https://github.com/rsasaki0109/oss_license_checker/actions/runs/43808148380) |
| 実プロジェクト | Requests・HTTPX・Rich × Linux・macOSの6構成すべて成功 | [real projects](https://github.com/rsasaki0109/oss_license_checker/actions/runs/43808148319) |
| README導入 | Linux・macOSで新規clone・仮想環境・HTML生成が成功 | [onboarding](https://github.com/rsasaki0109/oss_license_checker/actions/runs/43808148384) |
| 配布物 | ソース配布物からのwheelビルド・メタデータ検証・独立環境へのインストールが成功 | [distribution](https://github.com/rsasaki0109/oss_license_checker/actions/runs/43808148360) |

## 配布物の追加確認

CIのartifact取得はダウンロード先のHTTP 403で失敗したため、CI生成バイナリのローカル再検査はできませんでした。代わりに対象コミットを `git archive` でクリーンに展開してビルドし、次を確認しました。

- wheel・ソース配布物とも `twine check` が成功。
- wheelの `License-Expression` は `MIT`。両配布物にLICENSEを同梱。
- 新規仮想環境にwheelをインストールし、ソースツリー外で `python -I -m oss_license_checker --version` が配布メタデータと一致することを確認。
- 本ツール自身と推移依存に `--fail-unknown`・`--fail-missing-license-files` を指定して通過し、JSONとZIPを生成。

以下はこの追加確認でローカルに作ったファイルのSHA-256です。CIのバイナリのハッシュや、再ビルド時に同じハッシュになることを示すものではありません。

```text
7fa80d5d351dc8f64805301956e7cc7d048d9e47c0df80bac8c18c2b60261da7  wheel
fb351d4c76216bf216246d6db0de036d12ac4a31369f6b12eef84ce51a3955ec  source distribution
```

## 公開前の残作業

1. [初見ユーザーの導入確認](USER_TEST.md) を実施し、最初のレポートまでの時間・迷った箇所・手助けを記録する。現時点で未実施。
2. 指摘を反映した場合は対象コミットのCIを再確認する。
3. 公開するバージョン・対象コミット・[変更履歴](../CHANGELOG.md) を確定し、[リリース手順](RELEASING.md) に従う。

この段階ではタグ・GitHub Release・PyPI公開は作成していません。機能追加を再開する前に、残っている導入確認を優先します。
