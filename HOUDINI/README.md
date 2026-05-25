# Houdini Tools

本目錄收集自訂的 Houdini 擴充：

| 子目錄 | 用途 |
|---|---|
| [`husdplugins/outputprocessors/`](husdplugins/outputprocessors/README.md) | Solaris USD ROP 自訂 output processor（avalonpublish、projectrootvariable） |
| [`scripts/python/chd_toolkits/`](scripts/python/README.md) | Houdini 用 Python toolkit package（geometry/numpy 橋接、USD 查詢、COLMAP/Nerfstudio 匯入、USD Value Clips stitcher） |

## 安裝

兩個子目錄都靠同一條 `HOUDINI_PATH` 設定 — 把 `HOUDINI/` 加進 Houdini 的 search path，processors 與 Python package 會一次都掛上。

### 方法 A：Houdini package JSON（推薦）

Houdini 21 起官方推薦透過 package 機制管理擴充。把 [`scripts-collection.json`](scripts-collection.json) 複製到 Houdini 預設 packages 目錄（檔名可改、副檔名須為 `.json`）：

- Windows：`%USERPROFILE%/Documents/houdini21.0/packages/`
- Linux：`~/houdini21.0/packages/`
- macOS：`~/Library/Preferences/houdini/21.0/packages/`

如果你的 repo 不在 `D:/dev/scripts-collection/HOUDINI`，編輯 JSON 把路徑改成實際位置。注意 `value + method: append` 形式會在 Houdini 預設搜尋路徑後面**追加**（單純寫 `"HOUDINI_PATH": "..."` 會**覆蓋**預設）：

```json
{
    "env": [
        {
            "HOUDINI_PATH": {
                "value": "D:/dev/scripts-collection/HOUDINI",
                "method": "append"
            }
        }
    ]
}
```

package 機制好處：每個版本獨立檔案、Houdini 啟動時統一載入、`hconfig -p` 可印出生效路徑除錯。

### 方法 B：`houdini.env`

若不想用 package JSON 也可以直接在 `houdini.env`（`%USERPROFILE%/Documents/houdini21.0/houdini.env`）裡寫：

```ini
HOUDINI_PATH = D:/dev/scripts-collection/HOUDINI;&
```

結尾的 `&` 代表「保留 Houdini 預設搜尋路徑」，務必加。

### 驗證

啟動 Houdini 後：

```python
# Python shell
import chd_toolkits as ct  # 確認 toolkit 可 import
```

```text
# Solaris USD ROP 的 Output Processors 下拉，應出現：
#   - Avalon Publish
#   - Project Root Variable
```

## 相依

- Houdini 21+（也可在更早版本運作，但開發在 H21 上）
- Houdini 內建 `hou`、`pxr.Usd / UsdGeom / UsdShade / Sdf / Gf`、`numpy`
- 各子目錄各自額外依賴詳見其 README（例如 `scipy` 是 toolkit 可選依賴，部分 USD API 需要 USD 23.11+）

## 目錄結構

```text
HOUDINI/
├── README.md                       本檔
├── scripts-collection.json         範例 Houdini package JSON
├── husdplugins/
│   └── outputprocessors/           Solaris USD output processors
│       ├── README.md               功能與 API 說明
│       ├── avalonpublish.py
│       └── projectrootvariable.py
└── scripts/
    └── python/                     Houdini 自動加入 PYTHONPATH
        ├── README.md               chd_toolkits API 說明
        └── chd_toolkits/           Python package
            ├── __init__.py
            ├── core.py
            ├── colmap_points.py
            ├── nerfstudio_cam.py
            └── stitch_usd_clips.py
```

## 進階：使用其他 env 變數

`scripts-collection.json` 預設只設 `HOUDINI_PATH`。如果之後要擴充更多 env（例如 `PXR_PLUGINPATH_NAME`、`HOUDINI_OTLSCAN_PATH`），照 Houdini package JSON 規範新增 entry：

```json
{
    "env": [
        {
            "HOUDINI_PATH": {
                "value": "D:/dev/scripts-collection/HOUDINI",
                "method": "append"
            }
        },
        {
            "PXR_PLUGINPATH_NAME": {
                "value": "D:/dev/scripts-collection/HOUDINI/pxr_plugins",
                "method": "append"
            }
        }
    ]
}
```

## 參考

- Houdini Package System：<https://www.sidefx.com/docs/houdini/ref/plugins.html>
- Solaris USD Output Processors：<https://www.sidefx.com/docs/houdini/solaris/output.html#processors>
