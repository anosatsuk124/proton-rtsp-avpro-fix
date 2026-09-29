# パッチ仕様

[English version](patch.md)

## Wine ソース版

[`0001-live-network-state.patch`](../patches/0001-live-network-state.patch) を `versions.lock.json` の Wine コミットへ適用する。

```c
if (engine->network_state == MF_MEDIA_ENGINE_NETWORK_IDLE && engine->duration == INFINITY)
    return MF_MEDIA_ENGINE_NETWORK_LOADING;
```

状態の保存値は書き換えず、この getter の返値だけを補正する。

| 元の network state | duration | 戻り値 |
| --- | --- | --- |
| IDLE (1) | +INFINITY | LOADING (2) |
| IDLE (1) | 有限値 / NaN / -INFINITY | IDLE (1) |
| IDLE 以外 | 任意 | 元の値 |

ソースビルドは `scripts/build-wine.sh` に固定した設定で行う。Vulkan XML もハッシュ固定して事前取得し、コンテナ内ビルドはネットワーク無効で実行する。元リリースと同じ DLL バイト列を作ることは要求しない。同じ入力からビルドでき、修正前後の動作を比較できることを目的とする。

`--without-gstreamer` などは、この DLL のみを生成するビルド用設定である。実再生に使う Wine GStreamer / デコーダー / DXVK は固定 Proton リリース側のコンポーネントを使う。

## 正確なバイナリ版

[`patch_binary.py`](../scripts/patch_binary.py) は元 DLL と出力 DLL の SHA-256 を両方検証する。別バージョンへの推測による書き換えは行わない。

- 対象: `files/lib/wine/x86_64-windows/mfmediaengine.dll`
- 元 SHA-256: `93df6c48dc46c6927411234e12c11e4a733a1c18e9b7d6609d826b7b6825ab39`
- 出力 SHA-256: `a0c4a0a26e50158a12dca61971c47371191e67d606dfbd2ee0d2e970994111ed`
- 対象関数: `media_engine_GetNetworkState`, RVA `0x33b0`
- この DLL では対象位置の `.text` RVA と raw file offset が一致。
- `0x33b0..0x33bd` の prologue を維持し、`0x33be..0x3409` の本体を差し替える。
- 対象ビルド限定の構造体オフセット: duration `+0x70`, network_state `+0x80`。
- 保存レジスター、stack size、epilogue、PE unwind 情報の整合性を維持。
- 残りの関数領域を NOP で埋める。バイナリ版はこの getter 内の TRACE を省略する。

対応するアセンブリは [`live-network-body.s`](../patches/live-network-body.s)。正の無限大の IEEE 754 ビットパターン `0x7ff0000000000000` と一致した場合だけ補正する。

元ファイルと同じ出力先、想定外の入力ハッシュ、別内容の既存出力、symlink 出力は拒否する。すでに正しい出力がある場合はそのまま成功する。書き出し途中の DLL を公開しないよう、一時ファイルから atomic に別名作成する。

## 適用場所

Proton 自体を別名コピーして、その `files/lib/wine/x86_64-windows/` 内の DLL を置き換える。診断中、prefix の `system32` への配置だけでは組み込み DLL の選択が期待どおりにならず、`WINEDLLOVERRIDES=mfmediaengine=n` の強制は AVPro 初期化の失敗を招いた。そのためインストールスクリプトはこの方法を採用しない。

元 Proton、現在 VRChat が使用している Proton、ゲーム用 prefix の DLL は自動変更しない。
