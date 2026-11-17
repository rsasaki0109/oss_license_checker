# Calibrex：検出後のライセンス確認

2026-11-17（日本時間）。[初回検証](CALIBREX_VALIDATION.md) で不明となったSciPy・lz4・mcapを確認しました。対象のCalibrexコミット・依存の版・Linux環境は初回と同じです。Calibrex側のコード・設定は変更していません。

## 確認結果

| 依存 | 確認内容 | 今回の扱い |
| --- | --- | --- |
| lz4 4.4.5 | Python側のLICENSEはBSD-3-Clause。上流の同じ版の `lz4libs` の全9ファイルのライセンスコメントはBSD-2-Clause | `BSD-3-Clause AND BSD-2-Clause` の版限定補正 |
| mcap 1.6.0 | 該当リリースタグのルートLICENSEはMIT。タグのコミットとPythonの `__version__` を照合 | MITの版限定補正。上流LICENSEを補足証拠として保存 |
| SciPy 1.18.1 | BSDの本文に加えて、同梱バイナリの複数のライセンス・例外が記載されている | 単一のBSDへの補正は行わず、不明を維持 |

この確認はメタデータ補正の根拠整理です。全バイナリと上流ソースの同一性や、Calibrexの配布条件への適合を保証するものではありません。依存の更新時は再確認が必要です。

## 根拠と保存した証拠

- lz4のタグ `v4.4.5` はコミット `59b2d8176072bdee50d38cc68ec65c33b928a980`。上流LICENSEはインストール済みLICENSEとバイト単位で一致しました。BSD-2-Clauseの許諾・免責条項は9個のCソース・ヘッダの先頭コメントで確認しました。
- mcapのタグ `releases/python/mcap/v1.6.0` はコミット `ceaf05f1c33a7b8bca567092865d52cf41639e2d`。同コミットの `python/mcap/mcap/__init__.py` は `1.6.0` を宣言しています。
- [証拠一覧・取得元の不変URL・SHA-256](../examples/validation/calibrex/review-evidence/provenance.json) と、元の著作権表示を保持したライセンス本文・コメント抜粋を `review-evidence/` に保存しました。ソースからの抜粋範囲も記録しています。

### SciPyで追加検討が必要な部分

インストール済みの `scipy-1.18.1.dist-info/LICENSE.txt` には、以下の同梱ソフトウェアの宣言がありました。

| 同梱対象 | 記載されたライセンス |
| --- | --- |
| OpenBLAS | BSD-3-Clause |
| LAPACK（OpenBLASに同梱） | BSD-3-Clause-Open-MPI |
| libgfortran | GPL-3.0-or-later WITH GCC-exception-3.1 |
| libquadmath | LGPL-2.1-or-later |

`scipy.libs/` にOpenBLAS・libgfortran・libquadmathの `.so` が実在することも確認しました。これは今回のLinux wheelの構成に関する観測です。SciPy本体や他の収集ファイルの条件も含め、実際の配布形態・リンク方法・例外の適用条件・必要な表示や提供物を確認する必要があります。推測で複合SPDX式を作って検査を通すことはしていません。

## 補正後の再検査

初回と同じ仮想環境・extrasを使い、[確認用ポリシー](../examples/validation/calibrex/review-policy.toml) を追加しました。このファイルは確認済みのメタデータを補正する例で、組織の許可リストではありません。

```bash
/tmp/calibrex-license-env/bin/oss-license-checker 'calibrex[images,mcap]' --recursive \
  --config examples/validation/calibrex/review-policy.toml \
  --fail-missing-license-files --format html --output calibrex-reviewed.html \
  --license-bundle calibrex-reviewed.zip
```

| 項目 | 補正前 | 補正後 |
| --- | --- | --- |
| 不明 | SciPy・lz4・mcap | SciPy |
| インストール済み証拠の欠落 | mcap | mcap（維持） |
| 厳格な検査の終了コード | 1 | 1 |

HTML・JSON・Markdownを生成し、元のClassifier表記・補正後の式・根拠が保持されることを確認しました。さらに、許可リストにMITとBSD-3-Clauseしか指定しない場合は、BSD-2-Clauseも必要なlz4が拒否されることを確認しました。補正で許可ルールを迂回しないことも検証しています。

[機械可読の再検査結果](../examples/validation/calibrex/review-result.json) に条件と結果を記録しています。

## mcapの補足証拠の扱い

インストール済みmcapからは引き続きLICENSE・NOTICEを収集できません。上流のLICENSEを取得しても、既存の自動収集ZIPの `evidence_status` は `missing` のままです。上流の証拠と自動収集の証拠を混同しないためです。

同じ版の上流LICENSEは [mcap-LICENSE.txt](../examples/validation/calibrex/review-evidence/mcap-LICENSE.txt) に保存しました。配布準備では、自動収集ZIPに加えてこの補足資料とprovenanceを保持し、依存更新時の差し替えも管理してください。今回の作業では、外部証拠を自動収集に取り込む機能や、欠落検査の除外は追加していません。

残る作業は、SciPyの同梱ライブラリを含む配布条件の確認と、mcapの補足証拠を実際の配布物へどう同梱するかの決定です。終了コード1を維持したまま、これらをレビュー対象として残しています。
