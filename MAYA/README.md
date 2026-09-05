# Maya Tools

Autodesk Maya 用的 Python 工具集。一個 PySide2 主視窗加上分頁式的功能（System / USD），核心邏輯抽離到 `utils/`，可在無 UI 環境（mayapy、batch、外部腳本）直接呼叫。

## 目錄結構

```text
MAYA/
├── modules/
│   └── chordee-maya.mod         Maya module 定義（指向 scripts/python 等）
└── scripts/
    └── python/
        ├── main.py              入口，建立主視窗並注入 Maya main window
        ├── tabs/                UI 分頁
        │   ├── system_tab.py    System tab：Script Editor 字型、Parent Shape、Import References、Remove Namespaces
        │   └── usd_tab.py       USD tab：SkelRoot、USD Preview Shader、Materials Assignment、Arnold Materials 匯出
        └── utils/               純邏輯函式 / 類別，不依賴 PySide2
            ├── arnold_to_usd.py
            ├── character_usd_split.py
            ├── compare_bindposes.py
            ├── materials_assignment.py
            ├── usd_attrs.py
            ├── usd_preview_shader.py
            └── usd_utils.py
```

## 安裝（Maya module，推薦）

`chordee-maya.mod` 把 `scripts/python` 自動掛上 `PYTHONPATH`，不需要動 `Maya.env` 或 `userSetup.py`。註冊方式擇一：

**方式 A：把 `modules/` 加進 `MAYA_MODULE_PATH`**（建議；不複製檔案）

在 `Maya.env` 加：

```ini
MAYA_MODULE_PATH = <path-to-repo>/MAYA/modules
```

Windows 多條 path 用 `;` 分隔，Linux/macOS 用 `:`。

**方式 B：把 `.mod` 複製到 Maya 預設 modules 目錄**

複製 `MAYA/modules/chordee-maya.mod` 到下列其中一個（隨 OS 與版本）：

- Windows：`%USERPROFILE%/Documents/maya/<version>/modules/`
- Linux：`~/maya/<version>/modules/`
- macOS：`~/Library/Preferences/Autodesk/maya/<version>/modules/`

要注意 `.mod` 第三欄 `..` 是相對於該檔案位置；複製過去後，`scripts/python` 必須仍在 `<該檔位置>/../scripts/python`。要嘛在那邊建好對應結構，要嘛改用方式 A。

### 啟動 UI

在 Maya 的 Script Editor（Python）執行：

```python
import main
main.show()
```

若把這段存成 shelf button，每次點擊都是同一個 Python session，`import main`
之後 module 已被快取，改了 `main.py` 原始碼不會反映——這種情況要重新載入：

```python
import importlib
import main
importlib.reload(main)
main.show()
```

`main.show()` 會偵測同名舊視窗並先關閉，再開新視窗，避免疊圖。

### 之後要擴充（plug-ins / shelves / icons）

`chordee-maya.mod` 末三行**原本就以 `//` 註解保留**，不需要新增；建立對應目錄後直接把那三行的 `//` 去掉即可：

```text
+ chordee-maya 0.2.0 ..
PYTHONPATH +:= scripts/python
// 以下三行已在 .mod 內預留為註解；建立對應目錄後移除行首 `// ` 即可生效：
// MAYA_PLUG_IN_PATH +:= plug-ins
// MAYA_SHELF_PATH +:= shelves
// XBMLANGPATH +:= icons
```

## 安裝（fallback：直接設 PYTHONPATH）

若不想用 module 機制，也可以直接把 `MAYA/scripts/python/` 加進 `PYTHONPATH`：

```ini
PYTHONPATH = <path-to-repo>/MAYA/scripts/python
```

或在 `userSetup.py`：

```python
import sys
sys.path.append(r"<path-to-repo>/MAYA/scripts/python")
```

## 分頁說明

### System tab（`tabs/system_tab.py`）

| 按鈕 | 功能 |
| --- | --- |
| Change Script Editor Font Style | 透過 styleSheet 變更 Script Editor 字型與大小，支援 Maya 2020/2022+ 兩種選擇器 |
| Parent Shape | 將第一個選取物件的 shape parent 到第二個物件下（`-r -s`），若原 transform 因此變空會自動刪除 |
| Import All References | 反覆 import scene reference，最多 100 圈防止無窮迴圈 |
| Remove All Namespaces | 依深度由深至淺移除，跳過 `shared` 與 `UI` |

### USD tab（`tabs/usd_tab.py`）

| 按鈕 | 功能 |
| --- | --- |
| Create SkelRoot Attribute | 在選取物件加上 `USD_typeName = "SkelRoot"` 屬性（Maya-USD 匯出時識別 prim 型別） |
| Build USD Preview Shader | 開啟對話框，依輸入通道路徑建立 `usdPreviewSurface` 與貼圖節點 |
| Export Materials Assignment | 將選取 DAG 物件下所有 shape 的材質指派匯出為 USD |
| Export Selection Arnold Materials | 透過 `arnoldExportAss` 匯出 Arnold shader graph 並轉為 USD scope 結構 |

## utils（無 UI 依賴）

下列模組可在 mayapy 或任何 Maya Python 環境直接 import，不需要 PySide2 或主視窗。

### `usd_attrs`

```python
from utils.usd_attrs import set_usd_type_name

set_usd_type_name("|root|skeleton_grp", "SkelRoot")
set_usd_type_name("|root|materials_grp", "Scope")
```

在指定 Maya 節點上設定 `USD_typeName` 屬性。屬性已存在時只更新值，不會重新建立。

### `materials_assignment`

```python
from utils.materials_assignment import build_materials_assignment_stage

stage = build_materials_assignment_stage(
    "|root|geo",
    scope_name="Looks",
    purpose="",            # "" 代表 allPurpose
    asset_version="v001",
    asset_name="myAsset",
)
if stage:
    stage.Export("D:/out/materials.usda")
```

依據選定 DAG 物件下所有 shape 節點的材質指派，建構 in-memory `Usd.Stage` 並回傳。沒有 shape 子節點時回傳 `None`。

### `usd_preview_shader`

```python
from utils.usd_preview_shader import build_usd_preview_shader

shader = build_usd_preview_shader(
    name="myShader",
    textures={
        "diffuse": "D:/tex/diff.png",
        "normal":  "D:/tex/nrm.png",
        "roughness": "D:/tex/rough.png",
    },
)
```

建立 `usdPreviewSurface` shader 與對應 `shadingGroup`，依字典逐通道連接 `file` 與 `place2dTexture`。支援通道：`diffuse`、`emissive`、`occlusion`、`opacity`、`ior`、`metallic`、`roughness`、`specular`、`normal`、`displacement`；未列在內部對應表的通道預設使用 `outColorR` 連到 shader 同名屬性。

### `arnold_to_usd`

```python
from utils.arnold_to_usd import MtoaShadersToUSD

exporter = MtoaShadersToUSD("D:/out/shaders.usda", "|root|geo")
exporter.exportUSD()
```

呼叫 `arnoldExportAss` 匯出 Arnold shader graph，再對 USD 做命名空間整理（將 shader 收進 `/Looks/shaders`）與連線修正。需要 Arnold for Maya（mtoa）。

### `compare_bindposes`

```python
from utils.compare_bindposes import (
    compare_dagpose_nodes,
    compare_skincluster_bindposes,
)

compare_dagpose_nodes(tolerance=1e-5)
compare_skincluster_bindposes(tolerance=1e-5)
```

掃描場景中所有 `dagPose` 或 `skinCluster` 節點，回報同一關節在不同節點中綁定矩陣的不一致。回傳 `True` 代表全部相符，`False` 代表有差異，明細以 `print` 輸出。

`compare_skincluster_bindposes` 是刻意保留的檢查：實際的 artist 流程常會產生多個 skinCluster 但 `bindPreMatrix` 應相同，差異多半代表綁定狀態出問題。

### `usd_utils`

```python
from utils.usd_utils import (
    ensure_usd_plugin,
    create_empty_stage,
    create_stage_from_file,
    add_sublayer,
    add_reference,
)

ensure_usd_plugin()

# 空 stage
stage = create_empty_stage(name="myStage")

# 從檔案載入
stage = create_stage_from_file("D:/assets/foo.usda", name="foo")

# 加 sublayer（index=0 為最強）
add_sublayer(stage, "D:/assets/override.usda", index=0)

# 加 reference；prim 不存在會自動 Define 一個 Xform
add_reference(
    stage,
    prim_path="/World/Assets/Foo",
    ref_file_path="D:/assets/foo_geo.usda",
    ref_prim_path=None,           # 預設使用該檔案的 defaultPrim
    on_root_layer=True,           # 確保 author 在 root layer，不受 edit target 影響
)
```

Maya USD plugin（`mayaUsdPlugin`）必須可載入；`ensure_usd_plugin()` 會自動 load。

- 失敗時會 raise `RuntimeError` / `FileNotFoundError` / `ValueError`，呼叫端不會拿到「半成品」stage。
- `add_sublayer` 比對 sublayer 時做路徑正規化（forward slash + 折疊冗餘 `.`），避免 `a/b.usd` 與 `./a/b.usd` 重複加入。
- `add_reference` 預設用 `Usd.EditContext` 強制 author 在 root layer；若要沿用當前 edit target，把 `on_root_layer=False`。
- 訊息透過 `logging.getLogger(__name__)`，呼叫端可自行設 level、轉接 handler。

### `character_usd_split`

```python
from utils.character_usd_split import split_character_usd

geo_path, skel_path, anim_path = split_character_usd("character.usd")

# 指定輸出目錄（預設 None：輸出到輸入檔案同一個資料夾）
split_character_usd("character.usd", output_dir="D:/out")
```

把 `mayaUSDExport` 匯出的合併角色 USD（geo + UsdSkel skinning + skeleton +
animation + blendshape）拆成三個獨立檔案：

- `<name>_geo.usd`：純幾何，不含任何 skinning / skeleton 資料（不論該
  mesh 原本有沒有被蒙皮綁定）。
- `<name>_skel.usd`：只含**有實際蒙皮綁定**的 `Skeleton`／`BlendShape`
  prim，以及疊加在 mesh 路徑上的完整 skinning 資料（`jointIndices` /
  `jointWeights` / `geomBindTransform` / `skel:joints`（局部 joint
  子集合對照表，若有 author）/ `skel:skinningMethod`（`classicLinear`
  或 `dualQuaternion`，若有 author）與 `skel:skeleton` 關係）——這些
  mesh 路徑本身是沒有型別的 `over`/`def`，不含幾何資料。
- `<name>_anim.usd`：只含**有實際蒙皮綁定**之骨架的 `UsdSkelAnimation`
  （joint 動畫時間量資料，以及 blendshape 的 `blendShapeWeights`）。

三個檔案完全獨立，互不 `reference`／`payload`。要組合使用（例如把
`_skel.usd` 的蒙皮資料疊回 `_geo.usd` 的幾何上）由下游自行決定要用
reference、payload 還是 sublayer——`split_character_usd` 不預設任何一種；
三個檔案共用同一個 `defaultPrim` 路徑，`reference`／`sublayer` 都能直接
組合起來。

`_skel.usd` 的 `Skeleton` 會把 `skel:animationSource` 指向 `_anim.usd`
裡對應 `UsdSkelAnimation` 的 prim 路徑——這個路徑只是 composed namespace
裡的一個位置，不是指向 `_anim.usd` 這個檔案本身，所以只要 `_anim.usd`
（或任何路徑相同的替代動畫檔）也被組合進來就會自動解析，沒組合進來時
單純懸空、不影響其他部分。這代表把三個檔案 sublayer 或 reference 在一起
就會是完整可動畫的角色；要換掉某個 shot 的動畫，只要換一個 `_anim.usd`
（維持同樣的 Animation prim 路徑）即可，不需要改 `_skel.usd`。

真實 `mayaUSDExport` 輸出常包含大量**未被蒙皮綁定**的 `Skeleton` +
`Animation` prim pair（例如 Maya FK/IK 控制骨架的每根控制關節都會各自
匯出一組），這些不屬於任何 mesh 的 skinning，因此三個輸出檔案都不會有
它們——只有透過 `UsdSkel.Cache.ComputeSkelBindings` 真正解析出蒙皮綁定
關係的骨架才會進到 `_skel.usd`／`_anim.usd`。

三個選用旗標（預設都是 `False`，不影響既有行為）：

```python
split_character_usd(
    "character.usd",
    hide_curves=True,           # _geo.usd 裡的 BasisCurves/NurbsCurves 設 visibility=invisible
    hide_skeleton=True,         # _skel.usd 裡的 Skeleton 設 visibility=invisible
    curves_purpose_guide=True,  # _geo.usd 裡的 BasisCurves/NurbsCurves 設 purpose=guide
)
```

`hide_curves`／`curves_purpose_guide` 針對的是同一批 curve prim，兩者互相
獨立、可以同時開啟；`visibility`/`purpose` 都是寫死的靜態值，不是
time-sampled。

不是 Maya-USD Export Chaser plugin，單純函式，匯出後手動呼叫：

```python
cmds.mayaUSDExport(file="character.usd", ...)
geo_path, skel_path, anim_path = split_character_usd("character.usd")
```

- 用 `UsdSkel.Cache` + `UsdSkel.BindingAPI` 做 schema-based 探索，不假設
  prim 路徑深度；但 `SkelRoot` 到被綁定 mesh 之間，中繼 prim 必須有明確型別
  （`Xform`/`Scope`），沒有型別的中繼 prim 會讓探索找不到 skinning target。
- blendshape 的靜態 target 資料歸 `_skel.usd`（跟 Skeleton 同類，屬於「可以
  怎麼變形」的結構資料）；`blendShapeWeights` 時間量資料歸 `_anim.usd`
  （跟 joint 動畫共用同一個 `UsdSkelAnimation` prim，不需要額外拆檔）。
- 找不到輸入檔案 `raise FileNotFoundError`；輸入完全沒有 UsdSkel binding
  （純靜態 geo，沒有骨架）`raise ValueError`。

## 相依

- Maya 2022 以上（Python 3、PySide2 / shiboken2）
- `pxr.Usd`、`pxr.UsdGeom`、`pxr.UsdShade`、`pxr.Sdf`（Maya-USD plugin 內建）
- `maya.api.OpenMaya`（Maya 內建 API 2.0）
- `mayaUsd.ufe`、`mayaUsd_createStageWithNewLayer`（**僅** `usd_utils` 需要；Maya-USD plugin 內建）
- `mtoa`（**僅** `arnold_to_usd` 與 USD tab 的 Arnold 匯出按鈕需要）

## 設計筆記

- **UI 與邏輯分離**：所有可重用的 Maya / USD 操作放在 `utils/`，`tabs/` 只負責收集 UI 輸入、開檔案對話框、呼叫 util，再做 export / select 等收尾。
- **新增 tab**：在 `tabs/` 新增模組（建議命名 `<name>_tab.py`），class 繼承 `QtWidgets.QWidget`，再到 `main.py::MainWidget.initUI` 註冊。
- **新增 util**：純邏輯放 `utils/`。如果跨 tab 共用，從 tab 端 import 即可，不必經由 `__init__.py` 重新匯出。
- **`materials_assignment` 與 `arnold_to_usd` 的 `DEFAULT_SCOPE_NAME`** 各自定義，名稱皆為 USD 慣例 `"Looks"`，刻意不集中以降低跨模組相依。
