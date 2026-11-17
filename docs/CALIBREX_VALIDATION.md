# 自作OSSでの検証：Calibrex

2026-11-17（日本時間）、Linux / Python 3.12で実施。対象は [Calibrex](https://github.com/rsasaki0109/Calibrex) の [`75bbb1528f967ace2439b69627529a5d65585531`](https://github.com/rsasaki0109/Calibrex/commit/75bbb1528f967ace2439b69627529a5d65585531)、検査ツールは [`8fe39c1`](https://github.com/rsasaki0109/oss_license_checker/commit/8fe39c1) です。Calibrex側のコードや設定は変更していません。

## 結果

許可・禁止リストを指定せず、SPDX検証、不明検出、証拠ファイル欠落検出を実行しました。`allowed` は識別可能な式がポリシーで拒否されなかったという意味で、Calibrexの利用条件に適合すると判断したものではありません。

| 対象 | 推移依存込み | SPDX式として判定可能 | 不明 | 収集ファイル | 証拠欠落 | 終了コード |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| コア | 14 | 13 | 1 | 38 | なし | 1 |
| `images,mcap` extras込み | 18 | 15 | 3 | 41 | mcap | 1 |

不明・欠落をCIエラーにする指定により、両方とも意図どおり終了コード1です。終了コード2の実行エラーは発生していません。Calibrex本体はApache-2.0を認識し、LICENSEとNOTICEの両方を収集しました。収集した全ファイルのSHA-256を検証しました。

### 確認が必要な依存

| 依存 | 確認した版 | 不明の理由 | インストール済み配布物の証拠 |
| --- | --- | --- | --- |
| SciPy | 1.18.1 | `License` が自由文の本文。SPDX式として検証できない | 5ファイルを収集 |
| lz4 | 4.4.5 | ClassifierのBSD表記のみ | LICENSEを収集 |
| mcap | 1.6.0 | ClassifierのMIT表記のみ | ファイル一覧にLICENSE・NOTICE等がなく収集0件 |

mcapの結果は、この環境にインストールした配布物の観測です。上流ソースにLICENSEがない、利用禁止である、と結論づけるものではありません。上流の該当コミット・配布物を確認し、必要なファイルを別途確保する必要があります。SPDXへの補正は、本文を確認してからバージョンと根拠を記録してください。今回、これらを通すための補正・除外は追加していません。

### extrasと差分

`images,mcap` の選択でPillow・mcap・lz4・zstandardの4パッケージが追加されました。extrasをインストールした後でも、ルートを `calibrex` のみにすればコア14件だけが検査されます。

同じ対象の再検査は差分0、コアからextras込みへの比較は4件の `added` になりました。差分の終了コードを分離して確認するため、その確認だけは `--no-fail-unknown` と `--fail-on-change` を指定し、差分なしで0・差分ありで1になることを確認しました。これは不明ライセンスを承認した設定ではありません。

## 再現方法

本リポジトリのルートで実行します。以下の取得にはGitとネットワークが必要です。固定依存はLinux / Python 3.12で確認した組み合わせです。

```bash
git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/rsasaki0109/Calibrex.git /tmp/calibrex-license-source
git -C /tmp/calibrex-license-source fetch --depth 1 origin \
  75bbb1528f967ace2439b69627529a5d65585531
git -C /tmp/calibrex-license-source checkout --detach \
  75bbb1528f967ace2439b69627529a5d65585531
git -C /tmp/calibrex-license-source sparse-checkout set --no-cone \
  /pyproject.toml /README.md /LICENSE /NOTICE /AGENTS.md /src/
python -m venv /tmp/calibrex-license-env
/tmp/calibrex-license-env/bin/python -m pip install \
  -r examples/validation/calibrex/requirements.txt
/tmp/calibrex-license-env/bin/python -m pip install --no-deps /tmp/calibrex-license-source .

# 意図した終了コードは1。HTMLと証拠ZIPは保存されます。
/tmp/calibrex-license-env/bin/oss-license-checker 'calibrex[images,mcap]' --recursive \
  --fail-unknown --fail-missing-license-files \
  --format html --output calibrex-licenses.html --license-bundle calibrex-licenses.zip
```

コアだけを調べる場合はルートを `calibrex` にします。固定依存ファイルにはextrasの依存も含みますが、検査対象はルートとextrasの指定から決まります。

[機械可読の確認結果とprovenance](../examples/validation/calibrex/result.json) に依存の版・判定・ライセンスメタデータのハッシュ・検査条件を記録しています。元のHTML・JSON・ZIPにはライセンス本文を含み、再現コマンドで生成できます。Calibrexの機能・キャリブレーション精度、ROS/C++やGPU用の依存、未指定extras、法的なライセンス互換性は今回の検証範囲外です。
