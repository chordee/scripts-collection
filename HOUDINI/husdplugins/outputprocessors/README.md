# Houdini USD Output Processors

本目錄存放自訂的 Houdini Solaris USD Output Processor。

官方文件參考：
- Houdini Solaris Output Processors：<https://www.sidefx.com/docs/houdini/solaris/output.html#processors>
- USD Variable Expressions：<https://openusd.org/dev/user_guides/variable_expressions.html>（供 `projectrootvariable.py` 用到的 `` `"${VAR}/..."` `` 語法與 `Sdf.Layer.expressionVariables` 規格參考）

## 什麼是 Output Processor

Output Processor 是 Solaris (LOP) 在輸出 USD 時的「攔截器」。當 USD ROP（例如 `usd_rop`、`usdrender_rop`）寫出 stage 時，processor 可以：

- 改寫 reference / sublayer / payload 的路徑（轉相對路徑、改 search path 等）
- 改寫實際的存檔路徑
- 修改即將寫出的 `Sdf.Layer`（例如塞入 `customLayerData`）
- 在 begin/end 時掛入額外動作

安裝設定請參考 [`HOUDINI/README.md`](../../README.md)。安裝完成後在 USD ROP 的 **Output Processors** 多重參數即可選到自訂的 processor。

## 開發者 API 摘要

每個 processor 是一個 Python module，需在最末提供 module-level function：

```python
def usdOutputProcessor():
    return YourProcessorClass
```

Class 需繼承 `husd.outputprocessor.OutputProcessor`，並覆寫以下方法（按需）：

| 方法 | 用途 |
|------|------|
| `name()` *(static)* | processor 內部識別字串，必填 |
| `displayName()` *(static)* | UI 顯示名稱，必填 |
| `hidden()` *(static, 可選)* | 回傳 True 可從 UI 隱藏但仍可程式啟用 |
| `parameters()` *(static, 可選)* | 回傳 Houdini dialog script，定義 processor 自身的參數 |
| `beginSave(config_node, config_overrides, lop_node, t, stage_variables)` | 寫檔開始時呼叫；務必 `super().beginSave(...)` |
| `endSave(..., saved_paths, error_messages)` | 寫檔結束時呼叫（成功與否皆會） |
| `processReferencePath(asset_path, referencing_layer_path, asset_is_layer)` | 改寫 reference / sublayer 內記錄的路徑（寫進 USD 文字內容） |
| `processSavePath(asset_path, referencing_layer_path, asset_is_layer)` | 改寫實際存檔到磁碟的路徑 |
| `processReferenceExpression(asset_path, referencing_layer_path, asset_is_layer)` | 處理含有變數運算式的 reference 路徑 |
| `processLayer(layer)` | 在 layer 寫檔前直接修改 `pxr.Sdf.Layer`，回傳是否有修改 |

`evalConfig(parameter_name, config_node, config_overrides, t)` 是基底類別提供的工具，會優先讀 `config_overrides`，否則 fallback 到節點參數；參數不存在時回傳 `None`，呼叫端自行 `or default`。

### 注意事項

- **多個 processor 串接時**：`processSavePath` 與 `processReferencePath` 是依序呼叫的，只有第一個會拿到 Houdini 原始 `asset_path`，後面拿到的是前面 processor 處理過的結果。
- **`asset_is_layer`**：當資產不是 USD layer（例如貼圖、VDB、Python procedural）時為 False。若你的路徑改寫只該作用於 layer，請在開頭擋掉。
- **Windows 路徑比較**：用 `startswith()` 比較路徑時要 `.lower()` 並補上分隔符尾巴，避免大小寫與前綴誤判（例如 `C:/foo/barbaz` 不是 `C:/foo/bar` 的子路徑）。
- **`hou.text.abspath` / `hou.text.relpath` / `hou.text.normpath`**：優先使用這些，會正確處理 Houdini 變數（`$HIP`、`$JOB`…）與斜線方向。
- **`os.getlogin()`**：在無 controlling terminal 的環境（背景 render、batch hython）會丟 OSError，請改用 `getpass.getuser()`。

## 目錄內的 Processor

### `portablereferences.py` — Portable References

讓輸出 USD 整包可搬移的 output processor，做三件事：

1. **將 reference 路徑改為相對於引用 layer 的相對路徑**，前提是該 reference 位於輸出目錄底下；不在輸出目錄底下的 reference 維持絕對路徑。Python procedural（檔名 `.py` 結尾，例如 Houdini Ocean Procedural 的 `invokegraph.py`）會原樣保留，不被改寫，因為它們是由 USD plugin 解析，而非檔案路徑。
2. **將 save 路徑視為相對於主 USD 檔目錄**，自動補成絕對路徑。
3. **寫入 customLayerData**：`hip_file`、`create_time`、`user` 三個欄位，方便下游追蹤 layer 是誰、什麼時候、從哪個場景輸出的。

#### 使用方式

在 USD ROP 的 **Output Processors** 中加一筆，下拉選 `Portable References` 即可。

#### 限制

- Reference 路徑改寫不檢查 `asset_is_layer`；如果你引用了輸出目錄底下的貼圖/VDB，路徑也會被轉成相對。實務上這通常正是想要的結果，但若不是請自行加入過濾。
- 路徑比對採大小寫不敏感（針對 Windows）；若你在 Linux 上跑且依賴大小寫區分目錄，請改寫該段邏輯。

### `projectrootvariable.py` — Project Root Variable

將輸出 USD 中符合「專案根目錄」前綴的絕對 asset path 改寫成 USD variable expression，並在輸出 layer 的 `expressionVariables` metadata 寫入對應變數，方便日後跨機器/平台搬移與重新解析。

#### 參數

- **Project Root**（字串）：可輸入絕對路徑或含 Houdini 變數（`$JOB`、`$HIP`…），會以 `hou.text.expandString` 展開後再做比對。空字串時整個 processor 無動作。

#### 行為

1. 在每個輸出 layer 的 `expressionVariables` 寫入 `PROJECT_ROOT = <展開後的絕對路徑>`。
2. 對 `processReferencePath` 收到的 asset path：若是絕對路徑且前綴符合 `PROJECT_ROOT`，改寫為 `` `"${PROJECT_ROOT}/<rel>"` ``（references / payloads / sublayers，以及 asset-valued attributes 如 shader texture 都涵蓋）。
3. 不符合前綴、或 path 中已含 backtick / `${` 的 expression，原樣保留。
4. 不覆寫 `processSavePath`，不影響實際存檔位置。

#### 使用方式

在 USD ROP 的 **Output Processors** 中加一筆，下拉選 `Project Root Variable`，在參數區填入專案根目錄。

#### 限制

- 變數名固定為 `PROJECT_ROOT`，目前不支援多個變數或自訂變數名。
- **只改寫本身就是絕對路徑的 asset path**；相對路徑與已含 expression（backtick 或 `${`）的 path 一律 pass-through，不嘗試解析。
- 路徑前綴比對的大小寫策略依平台：Windows 採大小寫不敏感（`.lower()` 比對），Linux/macOS 嚴格比對。判定依 `sys.platform`。
- 與 `portablereferences` 並用時注意串接順序：後執行的 processor 拿到的是前一個處理過的結果，可能影響預期。
- 依賴 `Sdf.Layer.expressionVariables` API（USD 23.11 之後）；若 Houdini 內含的 USD 過舊，`processLayer` 會靜默跳過 metadata 寫入（path 改寫仍會發生，但下游無法解析）。
