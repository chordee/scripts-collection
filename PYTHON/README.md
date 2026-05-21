# Python Tools

一般用途的 Python 工具集，與 DCC 應用程式無關，可在標準 Python 環境執行。兩個子目錄各自為獨立的 uv 專案，依賴鎖定在自己的 `uv.lock`。

## 目錄結構

```text
PYTHON/
├── PYSIDE/                 PySide6 桌面 GUI 範例
│   ├── pyproject.toml      uv 專案設定（依賴：pyside6）
│   ├── uv.lock
│   └── drag_drop_example.py
└── usd_toolkits/           USD hierarchy 與 stage 比對工具
    ├── pyproject.toml      uv 專案設定（依賴：usd-core）
    ├── uv.lock
    ├── __init__.py
    └── tools.py
```

## 環境準備

兩個子目錄各自獨立，需要分別 `uv sync` 才會建立 `.venv` 並安裝依賴：

```text
cd PYTHON/usd_toolkits
uv sync

cd PYTHON/PYSIDE
uv sync
```

之後可用 `uv run <command>` 在該目錄的虛擬環境執行命令，不必手動 activate。

## usd_toolkits

USD stage 處理工具，依賴 `usd-core>=26.5`，可在 mayapy 或標準 CPython 使用。

### `usd2json(stage, file_path)`

將 `Usd.Stage` 的階層輸出為 JSON：每個 prim 以名稱當 key，子 prim 巢狀，metadata（type / kind）放在 `"#"`。

```python
from pxr import Usd
from tools import usd2json

stage = Usd.Stage.Open("scene.usda")
usd2json(stage, "scene.json")
```

JSON 範例：

```text
{
  "root": {
    "#": {"type": "Xform", "kind": "group"},
    "geo": {
      "#": {"type": "Mesh", "kind": ""}
    }
  }
}
```

註：使用 `stage.Traverse()`，預設只列 active + defined prim。需要列 inactive 或 abstract prim 自行改成 `TraverseAll()`。

### `diff_usd_files(file1_path, file2_path, leaf_only=True)`

雙向比對兩個 USD 檔案的 prim path 是否存在。差異以 `logging.INFO` 輸出，模組層級不會自動設定 root logger，呼叫端需自行 `logging.basicConfig(level=logging.INFO)`。

```python
import logging
from tools import diff_usd_files

logging.basicConfig(level=logging.INFO)
diff_usd_files("v001.usda", "v002.usda", leaf_only=True)
```

`leaf_only=True` 只比對 leaf prim（沒有子 prim 的）；`False` 則比對全部 prim。當沒有可比對的 prim 時不會除以零，會輸出 `no primitives checked`。

## PYSIDE

PySide6 桌面範例。

### `drag_drop_example.py`

最小化 drag & drop demo：建立 `QMainWindow`，覆寫 `dragEnterEvent` 與 `dropEvent`，把拖入的檔案 URL 印到 stdout。

```text
cd PYTHON/PYSIDE
uv run python drag_drop_example.py
```

## 相依

- Python 3.10 以上（由各子目錄 `pyproject.toml::requires-python` 指定）
- uv（套件管理）
- `usd-core`（`usd_toolkits` 專用）
- `pyside6`（`PYSIDE` 專用）
