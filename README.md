# proton-rtsp-avpro-fix

VRChat（Linux / Proton）の AVPro プレイヤーで、RTSP ライブ配信の音声は出るのに映像が Loading のまま止まる問題を直す Proton 互換ツールです。

Wine の `IMFMediaEngine::GetNetworkState()` が、長さが正の無限大（ライブ）のソースで `IDLE` を返す場合だけ `LOADING` に補正します。AVPro はこの `IDLE` を見て `Pause → Load` の回復処理に入り、対象 Wine では `Load()` が未実装のため再生状態が壊れます。補正後は再生状態が維持されます。詳細は [docs/patch.md](docs/patch.md)。

対象は **proton-rtsp-11.0-20260609-4 / Linux x86_64 / AVPro native 3.4.0f1-ultra** に固定しています。上流のバージョンとハッシュはすべて [versions.lock.json](versions.lock.json) にあり、取得するものは毎回照合します。このリポジトリ単体でビルドが完結し、他のディレクトリを参照しません。

## 3 つの使い方

| 目的 | コマンド | 出力 |
| --- | --- | --- |
| Arch 系にパッケージで入れる | `make pkg-arch` | `packaging/arch/proton-rtsp-avpro-fix-bin-*.pkg.tar.zst` |
| Debian 系にパッケージで入れる | `make pkg-deb` | `packaging/deb/proton-rtsp-avpro-fix_*_amd64.deb` |
| バイナリだけ作る | `make binary` / `make tarball` | `dist/mfmediaengine.dll` / `dist/proton-rtsp-11.0-20260609-4-avpro-fix.tar.gz` |

いずれも固定リリースの tar.gz（約 490 MB）を取得し、`mfmediaengine.dll` だけを差し替えて、Steam 上の名前を `proton-rtsp-11.0-20260609-4-avpro-fix` にした Proton ツリーを作ります。元 DLL と出力 DLL の SHA-256 を両方検証し、一致しない入力は拒否します。

### 必要なもの（共通）

- Linux x86_64、Python 3.12 以上、bash、GNU tar、coreutils
- 初回のインターネット接続（Proton リリースのダウンロード）

### Arch Linux

```sh
make pkg-arch          # packaging/arch で makepkg -f を実行
sudo pacman -U packaging/arch/proton-rtsp-avpro-fix-bin-*.pkg.tar.zst
```

`/usr/share/steam/compatibilitytools.d/proton-rtsp-11.0-20260609-4-avpro-fix/` に入ります。AUR の `proton-rtsp-bin` とはディレクトリ名が違うので共存できます。依存関係は AUR の `proton-rtsp-bin` と同じです。

PKGBUILD の `source=` は同じディレクトリの symlink 経由でリポジトリ内のスクリプトを参照します。`scripts/patch_binary.py` や `scripts/make-compat-tool.sh` を編集したら `make pkg-sums` で `sha256sums` を更新してください（`make test` が不一致を検出します）。

### Debian / Ubuntu

```sh
make pkg-deb
sudo dpkg -i packaging/deb/proton-rtsp-avpro-fix_11.0.20260609.4-1_amd64.deb
```

`dpkg-deb` がホストにあればそれを使い、無ければ `versions.lock.json` で固定した SteamRT4 SDK の Docker イメージ内で実行します（Docker が必要）。`--docker` / `--no-docker` で強制できます。control の Maintainer は `DEB_MAINTAINER` 環境変数、無ければ `git config user.name` と `user.email` から取ります。

### バイナリだけ

```sh
make binary                        # dist/mfmediaengine.dll と .sha256
make tarball                       # 加えて compatibilitytools.d にそのまま展開できる tar.gz
make binary ARGS="--proton DIR"    # 取得済みの未修正 proton-rtsp-11.0-20260609-4 を使う
make binary ARGS="--tarball FILE"  # 取得済みのリリース tar.gz を使う
```

tar.gz は Steam の `compatibilitytools.d` に展開するだけで使えます。Flatpak 版 Steam は `/usr/share` を見ないので、この tar.gz を Flatpak 側の `data/Steam/compatibilitytools.d/` に展開してください。

### Steam 側の設定

1. Steam を再起動する。
2. VRChat の「プロパティ → 互換性」で `proton-rtsp-11.0-20260609-4-avpro-fix` を選ぶ。
3. 起動オプションに `--disable-hw-video-decoding` を付ける（動作確認はソフトウェアデコードで行いました）。
4. ワールドに入れる URL は `rtspt://HOST:PORT/STREAM`（RTSP over TCP）。`rtsps://` は TLS の別方式で、TCP 指定の代わりにはなりません。

戻すときは互換性設定を以前の Proton に戻し、パッケージを削除するか展開したディレクトリだけを消します。ゲームの compatdata は触りません。

## ソースからビルドして修正前後を再現する

パッケージは確認済みのバイナリパッチを使います。同じ修正を Wine ソースからビルドし、修正前後を自動比較するには以下を使います。

追加で必要なもの:

- 同じユーザーから使える Docker daemon（SDK と MediaMTX は digest で固定）
- Git、GNU Make
- ホストの FFmpeg / ffprobe（`libx264` と AAC encoder）
- 実再生診断のみ: 通常のデスクトップセッション、Vulkan 対応 GPU、Steam、Steam Linux Runtime 4、ユーザーが所有する VRChat の `AVProVideo.dll`、Steam の H.264 動画再生環境

```sh
make fetch            # 固定 Proton tar.gz / Wine コミット / Vulkan XML / コンテナイメージを取得・照合
make build JOBS=2     # SDK 内（ネットワーク無効）で修正前後の mfmediaengine.dll をビルド
make patch            # 固定リリースにバイナリパッチを適用し SHA-256 を照合
make probe            # 診断用の最小 AVPro host と Media Foundation probe をコンパイル
make test             # 単体テスト（アセンブリとバイト列の一致、ハッシュ整合、ガード）
```

`make build` は固定 Wine コミットから `mfmediaengine.dll` だけをビルドし、実行時は固定 Proton リリースの残りと組み合わせます。Proton 全体を作り直す手順ではありません。出力先:

| 出力 | 内容 |
| --- | --- |
| `artifacts/binary-patched/` | 確認済みのバイナリパッチ版 DLL と manifest |
| `artifacts/source-baseline/` | 同じ SDK でソースビルドした未修正版 |
| `artifacts/source-patched/` | Wine ソースパッチ適用版 |
| `artifacts/probes/` | 診断用 EXE |
| `build/source-*.log` | コンパイラ出力 |

未修正の対象 Proton がすでにある場合は、ダウンロードの代わりにそのディレクトリを指定できます（DLL のハッシュで照合）。

```sh
make patch ARGS="--proton /path/to/proton-rtsp-11.0-20260609-4"
```

### 再現

Steam から VRChat を起動した状態でプロセス ID を調べ、そのプロセスから `STEAMVIDEOTOKEN` だけをメモリー上で引き継ぎます。値を引数に渡したり保存したりはしません。

```sh
pgrep -f '^S:.*VRChat.exe'
make reproduce ARGS="--inherit-video-token-from 12345"
```

自動で行うこと:

1. localhost の一時ポートに MediaMTX を起動し、FFmpeg のテスト映像と正弦波を H.264/AAC の RTSP over TCP で配信。
2. 公式未修正版・バイナリ修正版・ソース未修正版・ソース修正版を、毎回新しい診断用 prefix で順番に実行。
3. AVPro の再生状態、映像フレーム数、再生時刻、音声の非ゼロ振幅を検査。
4. 8 秒の有限長 MP4 が最後まで再生できることを検査。
5. 診断用の FFmpeg / MediaMTX / prefix を片付け、数値結果を `artifacts/runs/` に保存。

未修正版のライブ診断は `reproduced`、修正版は `passed`、MP4 は `passed` を期待します。期待と違えば非ゼロで終了します。Steam が別の場所にある場合は `--steam-root`、`--avpro-dll`、`--runtime` を指定します。実配信で試すには `--url rtsp://HOST:PORT/STREAM` を指定します（`rtspt://` に変換して TCP を明示。URL は保存しません）。

`make install` は、パッケージを使わずにユーザーの Steam `compatibilitytools.d` へ別名でコピーします（`ARGS="--variant source-patched"` でソース版）。

## 制約

- ライブ中は AVPro の `IsBuffering` が true のままになる場合があります。有限長動画には同じ補正をしません。
- ハードウェアデコード、他のワールド、AVPro の別バージョンとの互換性は保証しません。
- 実ゲームで確認したのはバイナリパッチ版です。ソースビルド版は単体診断（RTSP と MP4）まで確認しています。
- Flatpak Steam の sandbox 内からの自動診断は未検証です。

## ファイル

- `patches/0001-live-network-state.patch`: Wine ソースへのパッチ
- `patches/live-network-body.s`: バイナリパッチと同じ内容のアセンブリ
- `scripts/patch_binary.py`: 固定リリースの DLL へのバイナリパッチ（入出力ハッシュ検証つき）
- `scripts/make-compat-tool.sh`: 差し替え済み Proton ツリーの組み立て（パッケージとバイナリ出力で共通）
- `scripts/build-binary.sh`, `packaging/arch/PKGBUILD`, `packaging/deb/build-deb.sh`
- `scripts/repro.py`, `scripts/build-wine.sh`, `probes/`, `fixtures/`, `tests/`: ソースビルドと再現

## ライセンス

修正した `mfmediaengine.dll` は Wine 由来で LGPL-2.1-or-later です。対応するソースパッチは `patches/` にあります。Proton、SteamRT SDK、MediaMTX、FFmpeg、AVPro、Steam の各コンポーネントの条件は [THIRD_PARTY.md](THIRD_PARTY.md) を参照してください。AVPro DLL と Steam の動画トークンは配布物に含みません。
