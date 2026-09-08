# ESP32-S3 Wi-Fi CSI receiver

ESP32-S3で2.4 GHz Wi-FiのCSI（Channel State Information）を受信し、
USBシリアル経由でMacのターミナルへ数値を出力するESP-IDFプロジェクトです。

```text
Wi-Fi router  ~~~~~  ESP32-S3  ── USB ──  Mac
                       ↑
                 CSIを受信・出力
```

現在の範囲は生のCSIデータ取得までです。人の有無や動きの判定、OLED表示はまだ行いません。

## 必要なもの

- ESP32-S3開発ボード
- データ通信対応のUSBケーブル
- 2.4 GHz Wi-Fiネットワーク
- macOSとHomebrew

ESP32-S3のWi-Fiは2.4 GHz帯を使用します。5 GHz専用のSSIDには接続できません。

## 開発環境

このプロジェクトはESP-IDF v6.1でビルドを確認しています。

Homebrewが未導入の場合は[Homebrew公式サイト](https://brew.sh/ja/)の手順で導入します。
その後、ESP-IDFの前提パッケージとEspressif Installation Managerを入れます。

```bash
brew install libgcrypt glib pixman sdl2 libslirp dfu-util cmake python git
brew tap espressif/eim
brew trust espressif/eim
brew install eim
eim install -i v6.1
```

`brew trust` が不要なHomebrewでは、その行を飛ばして構いません。

新しいターミナルを開くたびに、ESP-IDF v6.1の環境を有効化します。

```bash
source "$HOME/.espressif/tools/activate_idf_v6.1.sh"
idf.py --version
```

`ESP-IDF v6.1` と表示されれば準備完了です。

## Wi-Fi設定

リポジトリのルートでESP32-S3をターゲットに設定します。

```bash
idf.py set-target esp32s3
idf.py menuconfig
```

設定画面で `Wi-Fi CSI configuration` を開き、次の2項目を入力して保存します。

- `2.4 GHz Wi-Fi SSID`
- `Wi-Fi password`

設定値はGit管理外の `sdkconfig` に保存されます。SSIDやパスワードをソースコードへ
書く必要はありません。

同じ画面で、シリアル出力量も調整できます。

- `Print every Nth CSI frame`: 何フレームごとに1回表示するか（初期値20）
- `CSI bytes to print per frame`: 1行に表示するCSIバイト数（初期値32）

## ビルド

```bash
idf.py build
```

最後に `Project build complete.` と表示されれば成功です。

## 書き込みとモニター

ESP32-S3をMacへUSB接続し、シリアルポートを確認します。

```bash
ls /dev/cu.*
```

`/dev/cu.usbmodem1101` が見つかった場合は、次のように書き込みとモニターを開始します。

```bash
idf.py -p /dev/cu.usbmodem1101 flash monitor
```

モニターを終了するキーは `Ctrl + ]` です。

接続に成功すると、ログにIPアドレスとCSIデータが表示されます。

```text
I (...) wifi_csi: Connecting to Wi-Fi...
I (...) wifi_csi: CSI enabled
I (...) wifi_csi: Got IP: 192.168.1.123
CSI: RSSI=-48 len=128 first_word_invalid=0 data=[-3,12,-4,11,...]
```

`data` は符号付き8ビットのCSI値で、虚数部、実数部の順にI/Qペアが並びます。
`first_word_invalid=1` のフレームでは、ハードウェア制約により先頭4バイトを解析から
除外する必要があります。表示は生データの確認を目的としているため、その4バイトも
そのまま出力します。

## リアルタイムグラフ

`idf.py monitor` を実行中なら、先に `Ctrl + ]` で終了します。同じシリアルポートを
モニターとグラフで同時に開くことはできません。

リポジトリのルートでPython環境と依存ライブラリを準備します。初回だけ必要です。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

ESP32-S3を接続した状態でグラフを起動します。USBシリアルポートが1つなら自動選択されます。

```bash
python -m tools.plot_csi
```

複数のUSBシリアル機器がある場合はポートを指定します。

```bash
python -m tools.plot_csi /dev/cu.usbmodem1101
```

グラフ上段には次の2本が表示されます。

- `Mean amplitude`: 各I/Qペアを `sqrt(I² + Q²)` へ変換した平均振幅
- `Frame change`: 前フレームからのサブキャリア振幅変化の平均値

人がルーターとESP32-S3の間を動くと、特に `Frame change` が跳ねる様子を確認できます。
下段には、最後に受信したフレームのサブキャリア別振幅が表示されます。

利用可能なポートだけを確認する場合は次を実行します。

```bash
python -m tools.plot_csi --list-ports
```

## 動作確認

ルーターとESP32-S3を1〜3 mほど離し、その間を歩いてCSI値の変化を観察します。

```text
Router  ~~~~~~~~~~~~~  person  ~~~~~~~~~~~~~  ESP32-S3
```

グラフの変化は動きの影響を観察するための指標です。この段階では固定しきい値による
人検知は行っていません。環境ごとの静止時データを集めた後、変化量の基準を決めます。

## 値が流れない場合

- `Got IP` が出ていなければ、SSID、パスワード、2.4 GHz接続を確認する
- USBポートが現れなければ、充電専用ではないUSBケーブルへ交換する
- 同じWi-Fi上で通信を発生させ、ESP32-S3が受信するパケットを増やす
- `CONFIG_ESP_WIFI_CSI_ENABLED=y` が `sdkconfig.defaults` にあることを確認する
- グラフでポート使用中のエラーが出たら、`idf.py monitor` を終了する

APIの詳細は[ESP-IDF Wi-FiドライバーのCSI説明](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32s3/api-guides/wifi.html#wi-fi-channel-state-information)と
[Espressifのesp-csiサンプル](https://github.com/espressif/esp-csi)を参照してください。
