# RuView実機テスト

このページは、RuViewをESP32-S3 1台とMacで動かしたときの再現手順です。
2026年9月8日に次の構成で確認しました。

- ESP32-S3 revision 0.2
- Flash 8 MB、PSRAM 8 MB
- RuView ESP32 firmware 0.8.8
- RuView source commit `d613a576ea848f96a9b15bac4e7f60b6be7c08e7`
- macOS、Rust 1.98.0

## 確認できたこと

学校のWi-FiにESP32-S3とMacを接続し、ESP32-S3からMacのUDP 5005へCSIが届きました。
実測時はRuView APIで次の状態を確認しました。

```text
node_id:       1
CSI status:    active
frame rate:    約11.3〜11.8 Hz
RSSI:          約-71〜-81 dBm
classification: present_moving
```

このネットワークでは端末間通信が許可されていました。学校やホテルのWi-Fiで
クライアント分離が有効な場合は、同じSSIDでもESP32-S3からMacへUDPが届きません。

RuViewの1台構成で信頼できる中心的な出力は、CSIの受信状態と信号変化です。
学習済み姿勢モデルを読み込んでいない状態でもUIは骨格や人数を生成しますが、今回の
実測では骨格点のconfidenceが0で、約5分の間にも推定人数が1から4まで変化しました。
表示された人型を、壁越しに測定した実際の姿勢や正確な人数として扱うことはできません。

## 1. 基板を確認する

シリアルモニターやグラフを終了してから、ポートとフラッシュ容量を確認します。

```bash
source "$HOME/.espressif/tools/activate_idf_v6.1.sh"
esptool --chip esp32s3 --port /dev/cu.usbmodem1101 flash-id
```

以降の例は`Detected flash size: 8MB`と表示された基板専用です。4 MB基板には必ず
RuViewの4 MB用バンドルを使います。

## 2. RuViewと公式ファームウェアを取得する

作業用ディレクトリへRuViewを取得します。sensing-serverのビルドにはサブモジュールも
必要です。

```bash
git clone --depth 1 https://github.com/ruvnet/RuView.git
cd RuView
git submodule update --init --depth 1

mkdir -p firmware-release
gh release download v0.8.8-esp32 \
  -R ruvnet/RuView \
  -p esp32-csi-node-v0.8.8-s3-8mb-flash-bundle.zip \
  -p SHA256SUMS.txt \
  -D firmware-release
```

ダウンロードしたZIPのハッシュを、リリースの`SHA256SUMS.txt`と照合します。その後、
ZIP内のファイルも照合します。

```bash
cd firmware-release
shasum -a 256 esp32-csi-node-v0.8.8-s3-8mb-flash-bundle.zip
grep esp32-csi-node-v0.8.8-s3-8mb-flash-bundle.zip SHA256SUMS.txt

unzip esp32-csi-node-v0.8.8-s3-8mb-flash-bundle.zip -d s3-8mb
cd s3-8mb
shasum -a 256 -c SHA256SUMS.txt
```

## 3. RuViewファームウェアを書き込む

この操作で、このリポジトリのCSIファームウェアはRuViewに置き換わります。4つの
書き込み先にNVS領域は含まれませんが、次のプロビジョニング操作ではNVSを書き換えます。

```bash
esptool --chip esp32s3 \
  --port /dev/cu.usbmodem1101 \
  --baud 460800 \
  write-flash \
  --flash-mode dio \
  --flash-size 8MB \
  0x0000 bootloader.bin \
  0x8000 partition-table.bin \
  0xf000 ota_data_initial.bin \
  0x20000 esp32-csi-node.bin
```

## 4. Wi-Fiと送信先を設定する

MacのLAN IPを確認します。通常は`en0`がWi-Fiです。

```bash
ipconfig getifaddr en0
ifconfig en0
```

RuViewリポジトリのルートへ戻り、SSID、パスワード、MacのLAN IPを設定します。
認証情報をGitへ追加しないでください。

```bash
python firmware/esp32-csi-node/provision.py \
  --port /dev/cu.usbmodem1101 \
  --chip esp32s3 \
  --ssid "YOUR_WIFI_SSID" \
  --password "YOUR_WIFI_PASSWORD" \
  --target-ip 192.168.1.20 \
  --target-port 5005 \
  --node-id 1
```

[Aterm公式案内](https://www.aterm.jp/support/guide/category/stable/mode/102/main.html)では、
初期SSIDの末尾`-g`が2.4 GHz、末尾`-a`が5 GHzです。
ESP32-S3で接続失敗理由`201`とRSSI `-128`が続く場合は、5 GHz側SSIDを指定して
いないか確認します。

Wi-Fiを切り替えた直後はMacのDHCPアドレスが変わることがあります。ESP32のログに
`sendto ENOMEM`が続く場合は`ipconfig getifaddr en0`を再実行し、新しいIPを
`--target-ip`へ設定してプロビジョニングし直します。

## 5. sensing-serverを起動する

Dockerを使わない場合はRustでMac用バイナリを作れます。

```bash
brew install rust
cd v2
cargo build --release -p wifi-densepose-sensing-server
```

ESP32の起動ログにある`Got IP`からESP32自身のIPを確認し、その1台だけを
`--udp-allow`で許可します。ESP32のIPが`192.168.1.50`の場合の例です。

```bash
./target/release/sensing-server \
  --source esp32 \
  --udp-port 5005 \
  --udp-bind 0.0.0.0 \
  --udp-allow 192.168.1.50/32 \
  --http-port 3000 \
  --ws-port 3001 \
  --ui-path ../ui \
  --no-edge-registry \
  --no-mdns
```

次のページを開きます。

- Dashboard: <http://localhost:3000/ui/index.html>
- Observatory: <http://localhost:3000/ui/observatory.html>

受信状態はAPIでも確認できます。

```bash
curl http://localhost:3000/health
curl http://localhost:3000/api/v1/nodes
curl http://localhost:3000/api/v1/sensing/latest
```

## 元のファームウェアへ戻す

RuViewのシリアルモニターとsensing-serverを止め、このリポジトリのルートで再度
書き込みます。Wi-Fi認証情報が残っている`sdkconfig`はGit管理外です。

```bash
source "$HOME/.espressif/tools/activate_idf_v6.1.sh"
idf.py -p /dev/cu.usbmodem1101 flash monitor
```
