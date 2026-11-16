# リリース手順

通常の修正・機能追加ではバージョンを変更しません。機能をまとめてリリースするタイミングで、対象バージョンと変更点を決めます。

1. 対象コミットを決め、`tests`・`distribution`・`real projects`・`onboarding` のGitHub Actionsが成功していることを確認する。macOSジョブも確認する。
2. [実プロジェクト検証](VALIDATION.md) の結果、READMEの導入手順、既知の制限を確認する。
3. リリースする場合に限り `pyproject.toml` のバージョンを更新し、変更点・互換性への影響をまとめる。既に公開済みのバージョンを再利用しない。
4. クリーンなチェックアウトで以下を実行する。

```bash
python -m pip install build twine
python -m build
python -m twine check dist/*
```

5. ソース配布物・wheelにMITのLICENSEが含まれ、wheelの `License-Expression` が `MIT`、`--version` が対象バージョンであることを確認する。
6. 対象コミットでCIを再確認し、タグとGitHub Releaseを作成して配布物を添付する。Action利用者向けに固定するコミットSHAも掲載する。

PyPI公開は別の作業として扱います。現状はPyPI公開用の資格情報・Trusted Publishing・自動リリースは設定していません。ビルド用CIはartifactを作るだけで、タグ・Release・PyPI公開は自動で行いません。
