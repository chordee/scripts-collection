# Nuke Tools

本目錄收集自訂的 Nuke 擴充（Nuke 16 以上，PySide6）。

| 檔案 | 用途 |
|---|---|
| `init.py` | 把 `python/` 加進 Nuke 的 plugin path 與 `sys.path` |
| `menu.py` | 在 Nuke 選單加入 **CHD › Afanasy Submitter** |
| `python/chd_nuke/afanasy_submitter.py` | 把目前 script 的 Write node 送到 Afanasy |

## 安裝

把本目錄加進 `NUKE_PATH`，例如：

```
NUKE_PATH=<path-to-repo>/NUKE
```

重新啟動 Nuke 後，選單會出現 **CHD › Afanasy Submitter**。

## Afanasy Submitter

一個 job 底下，每個勾選的 Write node 各是一個 block（service `nuke`），在 farm 上以下列命令算圖：

```
<Nuke 執行檔> -x [--nukex] -X <Write 完整名稱> -F <start>-<end>x<step> <script.nk>
```

### 對話框

| 欄位 | 預設值 |
|---|---|
| Job Name | `.nk` 檔名 |
| Nuke | 目前執行中的 Nuke（`nuke.EXE_PATH`） |
| NukeX (`--nukex`) | 目前 session 是否為 NukeX；勾選後以 nukex_r 授權算圖 |
| Write Nodes | 有選取的 Write 就只勾選取的，否則勾所有未 disable 的；Group 內的 Write 以 `Group1.Write1` 形式列出 |
| Frame Start / End | `root` 的 first / last frame |
| Frame Step、Frames per task、Capacity、Job Priority | 1、1、800、80 |

- Write 開了 **Limit to range** 時，該 block 用 Write 自己的範圍，否則用對話框的範圍。
- 送出前會確認並自動存檔；未存檔的新 script、未勾選任何 Write、勾選了 disabled 的 Write 都會被擋下。
- Windows 上整串命令外再包一層引號：Afanasy 經 `cmd.exe /c` 執行時會剝掉頭尾各一個引號，否則含空白的路徑會被截斷。

### 帶到 farm 的環境變數

`block.setEnv()` 是**覆蓋** worker 上的值，不是附加，所以只送白名單內的變數：

- 名稱：`NUKE_PATH`、`PYTHONPATH`、`OFX_PLUGIN_PATH`、`OCIO`（不分大小寫）
- 前綴：`CGRU_`、`RP_`、`PUB_`、`JOB_`、`AXIOM_`、`REZ_`
- 一律排除：名稱含 `KEY`、`TOKEN`、`PASSWORD`、`PASS`、`SECRET`、`PASSWD`、`PWD`、`CREDENTIAL`、`AUTH`、`LICENSE` 的變數

刻意不送的：

| 變數 | 原因 |
|---|---|
| `PATH` | 會蓋掉 worker 自己的 `PATH`，Windows 找 DLL 也靠它 |
| `NUKE_*` / `FN_*` 前綴 | 執行中的 Nuke 會自行加入 `NUKE_R_<build 日期>`（一長串授權雜湊）、`NUKE_TEMP_DIR`（本機暫存路徑）、`FN_ENT_*` 等，不屬於其他機器 |
| 名稱含 `LICENSE` 的變數（如 `foundry_LICENSE`） | 授權伺服器交給 farm 自行設定；本機自架授權時其值是 `5053@localhost` |

路徑類變數（名稱以 `PATH` 結尾，以及 `OCIO`）會展開 Windows 8.3 短路徑並統一為正斜線。

## 測試

```
# 送出邏輯（假的 nuke / af 模組），plain Python 即可
python -m unittest discover -s NUKE/python/tests

# 含對話框（需要 PySide6 與 QApplication），在 Nuke 內執行
Nuke17.0.exe --tg NUKE/python/tests/run_tests.py
```

`Nuke -t` 只有 QCoreApplication，無法建立 widget，對話框測試要用 `--tg`。
