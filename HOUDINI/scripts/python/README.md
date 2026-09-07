# Houdini Python Toolkit (`chd_toolkits`)

`HOUDINI/scripts/python/chd_toolkits/` 是一個 Houdini 用的 Python package，整合：

- Houdini geometry 與 numpy 的橋接
- 影像 2D 卷積
- USD prim / material / clip / layer 查詢（含 USD↔Houdini matrix 轉換）
- COLMAP `points3D.bin` → Houdini 點雲
- Nerfstudio `transforms.json` → Houdini 動畫相機
- USD Value Clips stitcher（純 Python 函式介面，無 CLI）
- Afanasy job submission（Houdini 內的 PySide6 面板）

安裝設定請參考 [`HOUDINI/README.md`](../../README.md)。安裝完成後在 Houdini 的 Python shell / Python SOP / HDA event handler 即可：

```python
import chd_toolkits as ct

ct.compute_prim_scale(prim, frame)
ct.point_attrib_to_numpy(geo, "P")

from chd_toolkits.colmap_points import read_points3d_binary_to_geo
from chd_toolkits.nerfstudio_cam import create_animated_camera
from chd_toolkits.stitch_usd_clips import stitch_clips
```

## 套件結構

```text
HOUDINI/scripts/python/
├── pyproject.toml             pytest 設定（非 packaged Python project）
├── chd_toolkits/
│   ├── __init__.py            re-export core helpers; defensive 對 plain Python（無 hou）
│   ├── core.py                Houdini / numpy / USD 核心 helper
│   ├── colmap_points.py       COLMAP .bin → Houdini geometry
│   ├── nerfstudio_cam.py      Nerfstudio transforms.json → Houdini 動畫相機
│   ├── afanasy_submitter.py   PySide6 面板 → Afanasy job submission
│   └── stitch_usd_clips.py    USD Value Clips stitcher（純 Python 函式介面）
└── tests/
    ├── conftest.py            sys.path 補上 chd_toolkits 上層
    ├── run_hython.py          $HFS/bin/hython -m pytest tests/ 的 wrapper
    ├── test_afanasy_submitter.py   command / submission / 面板流程（mock）
    ├── test_stitch_usd_clips.py    pxr-only；hython 或 plain Python 皆可
    ├── test_core_usd.py            core 的 USD 函式；hython only
    └── test_core_numpy.py          core 的 numpy 函式；hython only
```

`__init__.py` 採 try/except 包裹 `from .core import ...`，所以在 plain Python（無 `hou`、有 `pxr`）下也能 `from chd_toolkits.stitch_usd_clips import stitch_clips` 而不會被 `core` 的 import 失敗連帶卡住。

## 相依

- `hou`（Houdini 內建）— core / colmap_points / nerfstudio_cam 需要
- `numpy` — core / colmap_points 需要
- `pxr.Usd` / `pxr.UsdGeom` / `pxr.UsdShade` / `pxr.Sdf` / `pxr.Gf` — core / stitch_usd_clips 需要（Houdini 或 `pip install usd-core`）
- `scipy`（**可選**；若存在則自動暴露 `chd_toolkits.scipy_convolve2d`）
- `hou`、`PySide6` — afanasy_submitter 面板需要 Houdini 圖形介面環境
- `af`（CGRU/Afanasy）— 提交時需要能在 Houdini 內 `import af`，並已配置 Afanasy server 連線

## 測試

測試集中在 `tests/`，**主要設計在 Houdini 自帶的 hython 環境中跑** — 這樣 `pxr` 用的是 Houdini bundle 版而非 pip 的 `usd-core`，避免版本與 patch 差異導致「測試綠燈、實機壞」的情境。

### 在 hython 內跑（推薦）

1. 設好 `HFS` 指向 Houdini 安裝路徑：
   - Windows：`set HFS=C:\Program Files\Side Effects Software\Houdini 21.0.376`
   - Linux：`export HFS=/opt/hfs21.0.376`
2. 安裝 pytest 到 hython 的 Python（一次性）：
   ```shell
   "%HFS%\bin\hython" -m pip install pytest
   ```
3. 跑全部測試：
   ```shell
   python tests/run_hython.py
   ```
   或加 pytest 參數：
   ```shell
   python tests/run_hython.py -v -k stitch
   ```

`tests/run_hython.py` 會找 `$HFS/bin/hython`、定位 `pyproject.toml`、用 hython 執行 `pytest tests/`。

### 在 plain Python 跑（可選）

`test_stitch_usd_clips.py` 是純 pxr，可以離開 Houdini 在 plain Python 跑：

```shell
pip install pytest usd-core
cd HOUDINI/scripts/python
pytest tests/test_stitch_usd_clips.py
```

`test_afanasy_submitter.py` 使用標準函式庫 `unittest`，以假的 Houdini、Qt 與 Afanasy 介面測試流程，可在 plain Python 執行，無須安裝 PySide6 或連線到 farm：

```powershell
# 在 HOUDINI/scripts/python 下，替換成已確認的 Python 執行檔完整路徑。
& 'C:\path\to\python.exe' -m unittest discover -s tests -p test_afanasy_submitter.py -v
```

其餘需要 `hou` 的測試會在缺少它時自動 skip（透過 `pytest.importorskip`）。

### 測試覆蓋現況

| 檔案 | 覆蓋 | 環境 |
|---|---|---|
| `test_afanasy_submitter.py` | Base64 路徑、command 與 frame step、job/block 組裝、環境變數注入（含 setEnv graceful fallback）、面板預設值、ROP 選取、存檔確認取消、錯誤訊息與視窗替換 | hython / plain Python；UI 與 af 使用 mock |
| `test_stitch_usd_clips.py` | 全部公開函式 + integration（含巢狀 primpath 階層保留、distinct `clip_primpath`、`frame_range`/`scene_range` 反向拒絕） | hython / plain Python |
| `test_core_usd.py` | `compute_prim_scale`、`get_material_from_prim`、`get_all_asset_paths_from_*`、`get_clip_*`、`get_all_layers_in_layer`（含 cycle detection、`report_missing`）、`get_all_asset_paths_from_stage` / `get_all_clip_sequences_from_stage`（relative `prim_path` 拒絕）、`get_all_shader_texture_paths_from_stage`（UDIM、missing、binding 無關、AssetArray input、time-sampled input）、`get_all_vdb_paths_from_stage`（time sample 聯集、default fallback、Field3DAsset 排除、missing）、`dump_json`、`set_prim_transform`（直接套用、replace_existing_local 逆矩陣抵消、recook 冪等性、型別支援、動態 timecode） | hython only |
| `test_core_numpy.py` | `convolve2d`（含 input validation、dtype 升格、kernel flip）、`scipy_convolve2d`（若 scipy 存在） | hython only |
| `test_core_hou.py` | `matrix_manipulate`（identity/translate/Matrix3 升格/shape 拒絕）、`primitive_xform`（identity/translate/int time wrap）、`point_attrib_to_numpy`（float/int 屬性、missing） | hython only |
| `test_colmap_points.py` | `read_points3d_binary_to_geo`（合成 COLMAP `.bin`、位置/色彩/error/track skip、`geo.clear()`、missing file、非 `.bin` 副檔名、截斷檔案 raise 且清空 geometry） | hython only |
| `test_nerfstudio_cam.py` | `create_animated_camera`（節點建立、custom subnet、focal length 計算、解析度、6 軌 keyframe、playbar range、缺檔/空 frames 回 None、destroy+rebuild） | hython only |

`conftest.py` 的 autouse fixture 在每個測試後自動 `hou.hipFile.clear()`，避免 `nerfstudio_cam` 建的 DAG / playbar 狀態污染下個測試。

`tests/conftest.py::MockSopNode` 是給 `colmap_points` 用的最小 `hou.SopNode` stub（只實作 `.geometry()`），避免測試要真的 cook Python SOP。

## API

### `afanasy_submitter` — Afanasy 提交面板

在 Houdini 的 Python Shell 或 Python Shelf Tool 中執行：

```python
from chd_toolkits import afanasy_submitter

afanasy_submitter.show()
```

`show()` 以 Houdini 主視窗為 parent 開啟 PySide6 面板並回傳 dialog；重複呼叫會關閉先前的面板。

#### 面板欄位

| 欄位 | 預設 | 用途 |
|---|---|---|
| Job Name | 目前 HIP 檔名（不含副檔名） | Afanasy job 名稱 |
| Hython | 目前 Houdini 的 `$HFS/bin/hython.exe`（非 Windows 為 `hython`） | Worker 執行檔路徑，可修改或 Browse |
| ROP Node | 空白 | 用 Browse 開啟 Houdini 節點選擇器 |
| Use Selected ROP | 未勾選 | 改用按下 Submit 當下的 Houdini 選取節點，取代 ROP Node 欄位 |
| Frame Start / End | 目前 playback range | 渲染起訖幀 |
| Frame Step | `1` | 幀增量，同時傳給 Afanasy 與 ROP |
| Frames per task | `1` | 每個 task 的幀數，交由 Afanasy numeric block 拆分 |
| Capacity | `800` | `block.setCapacity()` |
| Job Priority | `80` | `job.setPriority()` |

勾選 **Use Selected ROP** 時必須恰好選取一個節點，且通過 `isinstance(node, hou.RopNode)`，可接受其子類別。未選取、多選或型別不符都會中止提交；Browse 指定的節點也使用同樣的型別檢查。

#### 提交流程

1. 按 Submit 後驗證欄位與 ROP。尚未命名的新 HIP 必須先 Save As；Frame Start 不得大於 End，Step、Frames per task 與 Capacity 必須為正數。
2. 顯示 **Save and Submit** 對話框與目前 HIP 路徑。按 **OK** 才呼叫 `hou.hipFile.save()`；按 **Cancel** 或關閉對話框就終止，不存檔、不提交。預設按鈕為 Cancel。
3. 儲存成功後，在 Houdini 內使用 `af` 建立一個 `af.Job` 和一個 service 為 `hbatch` 的 `af.Block`，設定 command、numeric frame range、capacity 與 priority。同時透過 `block.setEnv()` 將當前 Houdini session 的所有環境變數（包含 `HOUDINI_PATH`、`HFS`、`PYTHONPATH`、`OCIO` 等）全數注入至該 block，確保 farm worker 上的 hython 能夠完整重現提交端的環境配置，再呼叫 `job.send()`。
4. 顯示提交結果；驗證、存檔或送出失敗時顯示錯誤訊息。處理期間 Submit 暫時停用，結束或取消後恢復。

Worker 實際執行的是 `hython -c "..."`：解碼 HIP／ROP 路徑、載入 HIP、找到 ROP，再呼叫 `render(frame_range=(task_start, task_end, frame_step))`。HIP 與 ROP 路徑以 UTF-8 URL-safe Base64 嵌入 command；兩個 `@#@` 由 Afanasy 替換成 task 起訖幀。

Worker 不需要安裝 `chd_toolkits`，也不需要共用臨時 Python 腳本；但必須能存取指定的 hython、HIP、場景資產及輸出路徑，並具備所需授權。工具沒有自動路徑映射，也不建立 HIP 快照，後續再儲存同一份 HIP 會影響尚未載入它的 tasks。

`submit_job()` 目前不會呼叫 `job.setNativeOS()` 限制 job 只跑在提交端的原生作業系統——這是刻意的假設：目前 render farm 全部是 Windows worker，尚無混合 OS 的情境。若未來 farm 加入非 Windows worker，需要補上 `setNativeOS()`（或依實際情境改用 `setAnyOS()`），否則命令列（`hython.exe`、路徑分隔符號等）在跨平台派送時會失敗。

上述確認對話框屬於面板流程；直接呼叫底層 `submit_job()` 會驗證、存檔並提交，不顯示確認視窗。自動化測試涵蓋 mock 流程，不代表已驗證真實面板顯示或 farm 渲染。

---

### `core` — Houdini / numpy / USD helpers

#### `matrix_manipulate`

```python
matrix_manipulate(
    matrix: Union[hou.Matrix3, hou.Matrix4],
    data: np.ndarray,
) -> Optional[np.ndarray]
```

用 Houdini 矩陣變換一組 row vector。內部把 `hou.Matrix3` 升為 `hou.Matrix4`，再以 homogeneous coordinate 做乘法。

- `matrix`：`hou.Matrix3` 或 `hou.Matrix4`。
- `data`：`np.ndarray`，shape 必須為 `(N, 3)`；不符合則回 `None`。
- 回傳：`np.ndarray`（`float32`，shape `(N, 3)`）；輸入 shape 不對時回 `None`。

#### `point_attrib_to_numpy`

```python
point_attrib_to_numpy(
    geo: hou.Geometry,
    attr: str = "P",
) -> Optional[np.ndarray]
```

把點屬性原始 buffer 直接 reinterpret 成 numpy array，不複製。

- `geo`：`hou.Geometry`。
- `attr`：`str`，點屬性名稱，預設 `"P"`。
- 回傳：`np.ndarray`，shape `(npoints, attr_size)`；int 屬性 dtype 為 `int32`、float 屬性為 `float32`。屬性不存在或非數值型別回 `None`。

#### `convolve2d`

```python
convolve2d(
    image: np.ndarray,
    kernel: np.ndarray,
    padding: int = 0,
    strides: int = 1,
    pad_mode: Optional[str] = None,
) -> np.ndarray
```

純 numpy 實作的 2D 卷積（會 flip kernel，行為與 `scipy_convolve2d` 一致）。簡單但慢，用於驗證或教學。

- `image`：2D `np.ndarray`；非 2D 丟 `ValueError`。
- `kernel`：2D `np.ndarray`；非 2D 丟 `ValueError`。
- `padding`：`int ≥ 0`，padding 量；負數或非整數丟 `ValueError`。
- `strides`：`int ≥ 1`，步長；小於 1 或非整數丟 `ValueError`。
- `pad_mode`：`Optional[str]`，傳給 `np.pad` 的 mode，預設 `None`（內部當 `"constant"`）。
- 回傳：`np.ndarray`，dtype 用 `np.result_type(image.dtype, kernel.dtype, np.float64)` 升格，shape `((H+2P-Kh)//strides + 1, (W+2P-Kw)//strides + 1)`。kernel 大於 padded image 時丟 `ValueError`。

#### `scipy_convolve2d`

```python
scipy_convolve2d(
    image: np.ndarray,
    kernel: np.ndarray,
    mode: str = "same",
    boundary: str = "symm",
) -> np.ndarray
```

`scipy.signal.convolve2d` 的薄封裝。**只有在 scipy 可 import 時才會被定義**（透過 `importlib.util.find_spec` 偵測），否則不會出現在 module 命名空間。

- `image`、`kernel`：2D `np.ndarray`。
- `mode`：`str`，`"full"` / `"valid"` / `"same"`，預設 `"same"`。
- `boundary`：`str`，`"fill"` / `"wrap"` / `"symm"`，預設 `"symm"`。
- 回傳：`np.ndarray`，shape 視 `mode` 而定。

#### `compute_prim_scale`

```python
compute_prim_scale(
    prim: Usd.Prim,
    time: Union[int, float, Usd.TimeCode] = Usd.TimeCode.Default(),
) -> Optional[List[float]]
```

世界空間 scale vector，內部用 `Gf.Matrix4d.Factor()` 做完整分解（不是 row length），能正確處理 shear 與非均勻 scale；mirror（rotation determinant < 0）會在 x 軸帶出負號。

- `prim`：`Usd.Prim`；非 `Xformable` 回 `None`。
- `time`：`int` / `float` / `Usd.TimeCode`；非 `TimeCode` 會自動包成 `Usd.TimeCode(time)`。預設 `Usd.TimeCode.Default()`。
- 回傳：`List[float]`，三元素 `[sx, sy, sz]`；Factor 失敗或非 Xformable 回 `None`。

#### `primitive_xform`

```python
primitive_xform(
    prim: Usd.Prim,
    time: Union[int, float, Usd.TimeCode] = Usd.TimeCode.Default(),
) -> Optional[hou.Matrix4]
```

世界空間 transform 轉 `hou.Matrix4`。

- `prim`：`Usd.Prim`；非 `Xformable` 回 `None`。
- `time`：`int` / `float` / `Usd.TimeCode`，預設 `Usd.TimeCode.Default()`。
- 回傳：`hou.Matrix4`，由 `Gf.Matrix4d` 的四個 row 顯式構造；非 Xformable 回 `None`。

#### `set_prim_transform`

```python
set_prim_transform(
    prim: Union[Usd.Prim, UsdGeom.Xformable],
    matrix: Union[Gf.Matrix4d, hou.Matrix4, Sequence[float], np.ndarray],
    time: Union[int, float, Usd.TimeCode] = Usd.TimeCode.Default(),
    op_suffix: str = "sopTransform",
    replace_existing_local: bool = False,
) -> UsdGeom.XformOp
```

在 USD Prim 上設定 `xformOp:transform`，並將其 prepend 到 `xformOpOrder` 的最前端（index 0）。支援在 Houdini Python LOP / Inline Script 中快速套用 SOP 或外部矩陣。

- `prim`：`Usd.Prim` 或 `UsdGeom.Xformable`。
- `matrix`：支援 `Gf.Matrix4d`、`hou.Matrix4`、16-float Sequence（list/tuple）、4x4 巢狀序列或 numpy array。
- `time`：`int` / `float` / `Usd.TimeCode`，預設 `Usd.TimeCode.Default()`。若為動態變換可傳入當前 frame（如 `hou.frame()`）。
- `op_suffix`：`xformOp:transform` 的 suffix，預設 `"sopTransform"`。若已存在同名 op 則重複使用，避免每次 cook 重複堆疊 op。
- `replace_existing_local`：`bool`，預設 `False`。
  - `False`：直接將目標矩陣寫入該 op（作為 local pre-transform）。
  - `True`：排除該 op 自身，計算 Prim 上原有其他 xformOps 的 local transform 並取逆矩陣抵消，使最終的 local transformation 剛好等於 `matrix`。
- 回傳：`UsdGeom.XformOp`，已建立或更新的 transform op。

#### `get_material_from_prim`

```python
get_material_from_prim(prim: Usd.Prim) -> Optional[UsdShade.Material]
```

透過 `UsdShade.MaterialBindingAPI.GetDirectBinding` 取得直接綁定的 material。

- `prim`：`Usd.Prim`。
- 回傳：`UsdShade.Material`；無 direct binding（`GetMaterialPath().IsEmpty()`）或 material prim invalid 時回 `None`。

#### `get_all_asset_paths_from_prim`

```python
get_all_asset_paths_from_prim(prim: Usd.Prim) -> List[str]
```

收集 prim 上所有 `Sdf.ValueTypeNames.Asset` / `AssetArray` 型屬性的已解析路徑，含 timesamples，去重。空字串路徑（resolve 失敗）會被略過。

#### `get_clip_names`

```python
get_clip_names(prim: Usd.Prim) -> Optional[List[str]]
```

列出 prim 上 `clips` metadata 內所有 clipSet 名稱。無 `clips` metadata 時回 `None`。

#### `get_clip_sequences_from_prim`

```python
get_clip_sequences_from_prim(
    prim: Usd.Prim,
    clip: str = 'default',
) -> Optional[List[str]]
```

取指定 clipSet 的 `assetPaths` 已解析路徑（去重）。**template 形式的 clip（用 `templateAssetPath` 而非 `assetPaths`）會回 `None`**。

#### `get_all_clip_sequences_from_prim`

```python
get_all_clip_sequences_from_prim(prim: Usd.Prim) -> Optional[List[str]]
```

對 prim 上**所有** clipSet 做 `assetPaths` union；無 `clips` metadata 回 `None`。

#### `get_all_asset_paths_from_stage`

```python
get_all_asset_paths_from_stage(
    stage: Usd.Stage,
    prim_path: Union[str, Sdf.Path] = '/',
) -> List[str]
```

從 `prim_path` 開始用 `Usd.PrimRange` traverse，對每個 prim 呼叫 `get_all_asset_paths_from_prim` 並 union。`prim_path` 必須是絕對路徑（`Sdf.Path(prim_path).IsAbsolutePath()`），否則 `raise ValueError`——`Usd.Stage.GetPrimAtPath` 對相對路徑會回傳 invalid prim 而不是報錯，若不擋下來會靜默回傳空 list。

#### `get_all_clip_sequences_from_stage`

```python
get_all_clip_sequences_from_stage(
    stage: Usd.Stage,
    prim_path: Union[str, Sdf.Path] = '/',
) -> List[str]
```

從 `prim_path` 開始 traverse stage，對每個有 `clips` metadata 的 prim 呼叫 `get_all_clip_sequences_from_prim` 並 union。`prim_path` 必須是絕對路徑（`Sdf.Path(prim_path).IsAbsolutePath()`），否則 `raise ValueError`——`Usd.Stage.GetPrimAtPath` 對相對路徑會回傳 invalid prim 而不是報錯，若不擋下來會靜默回傳空 list。

#### `get_all_layers_in_layer`

```python
get_all_layers_in_layer(
    usd_layer: Union[str, Sdf.Layer],
    report_missing: bool = False,
) -> Union[List[str], Tuple[List[str], List[str]]]
```

走訪 layer 的所有 composition asset dependencies（sublayer / reference / payload，用 `Sdf.Layer.GetCompositionAssetDependencies`）並遞迴展開。Cycle detection key 用 `layer.realPath`（fallback `identifier`）統一比對，避免 root 用相對路徑開啟時繞過檢查。主 layer 開不起來時回空 list（`report_missing=True` 時回 `([], [])`）。

`report_missing=True` 時回傳 `(found, missing)` tuple：`missing` 是打不開的依賴路徑（壞掉的 reference、被刪除的檔案等）；這些路徑仍然會出現在 `found` 裡（因為確實有被引用到），只是不會再往下遞迴展開。預設 `report_missing=False` 行為完全不變，只回傳 `found`。

#### `get_all_shader_texture_paths_from_stage`

```python
get_all_shader_texture_paths_from_stage(
    stage: Usd.Stage,
    prim_path: Union[str, Sdf.Path] = '/',
    report_missing: bool = False,
) -> Union[List[str], Tuple[List[str], List[str]]]
```

走訪 `prim_path` 底下所有 `UsdShade.Shader` prim（不論有沒有被 material binding 綁定），收集每個 shader input 裡型別是 `Asset` / `AssetArray` 的值（不篩參數名稱，非 `inputs:file` 的自訂 shader 參數也抓得到）。`prim_path` 必須是絕對路徑，否則 `raise ValueError`（同 `get_all_clip_sequences_from_stage`）。

**UDIM**：路徑帶 `<UDIM>` token（例如 `diffuse.<UDIM>.exr`）時，因為 resolver 不會展開 token，`resolvedPath` 一定是空的；這種路徑會被辨識出來、以原始 template 字串回傳，不會被濾掉也不會被誤判成 `missing`。不做 tile 展開（不會去 glob `1001`/`1002`... 等實際檔案）。

`report_missing=True` 時回傳 `(found, missing)`：`missing` 是解析失敗、且不是 UDIM template 的原始 asset path。跟 `get_all_layers_in_layer` 不同的是，這裡的 `missing` 路徑**不會**同時出現在 `found` 裡（沒有 UDIM 的不可解析貼圖路徑沒有意義上的「找到」）。

#### `get_all_vdb_paths_from_stage`

```python
get_all_vdb_paths_from_stage(
    stage: Usd.Stage,
    prim_path: Union[str, Sdf.Path] = '/',
    report_missing: bool = False,
) -> Union[List[str], Tuple[List[str], List[str]]]
```

走訪 `prim_path` 底下所有 `UsdVol.OpenVDBAsset` prim，讀取 `filePath` 屬性。只認 `OpenVDBAsset`，不含 `UsdVol.Field3DAsset`（`.f3d` 格式，跟 `.vdb` 無關，儘管共用 `UsdVol.FieldAsset` base schema）。`prim_path` 必須是絕對路徑，否則 `raise ValueError`（同 `get_all_clip_sequences_from_stage` / `get_all_shader_texture_paths_from_stage`）。

**Time sample**：VDB 序列幾乎都是用 time sample 存每一幀不同的實際檔名（例如 `sim.0001.vdb`、`sim.0002.vdb`），不是單一 default 值，所以會遍歷 `attr.GetTimeSamples()` 全部時間點並聯集；沒有 time sample 時才 fallback 讀 default 值。不做 UDIM 判斷（VDB 檔名不會有 `<UDIM>` 這種 2D 貼圖 tiling token）。

`report_missing=True` 時回傳 `(found, missing)`：解析失敗的路徑只會出現在 `missing`，不會同時出現在 `found`（跟 `get_all_shader_texture_paths_from_stage` 同樣的 found/missing 不重疊語意，跟 `get_all_layers_in_layer` 不同）。

#### `dump_json`

```python
dump_json(data, path: Union[str, Path, None] = None) -> Optional[str]
```

把 `data`（例如上面幾個函式回傳的 list / tuple / dict）序列化成 JSON。不給 `path` 就回傳 JSON 字串；給 `path` 就直接寫檔（UTF-8）並回傳 `None`。不依賴 `hou` / `pxr`，純 `json` + `pathlib`。

```python
dump_json(get_all_layers_in_layer(layer), "deps.json")

found, missing = get_all_layers_in_layer(layer, report_missing=True)
dump_json({"found": found, "missing": missing}, "deps.json")
```

---

### `colmap_points` — COLMAP `.bin` → Houdini geometry

#### `read_points3d_binary_to_geo`

```python
read_points3d_binary_to_geo(
    path_to_model_file: str,
    parent_node: hou.SopNode,
) -> Optional[int]
```

讀 COLMAP `points3D.bin` 寫入 Python SOP 的 geometry，建立 `P`、`Cd`（0–1 normalize）與 `error` 屬性，含 `InterruptableOperation` 進度條。

- `path_to_model_file`：`points3D.bin` 路徑。非 `.bin` 副檔名或檔案不存在會跳訊息並回 `None`。
- `parent_node`：Python SOP，其 `geometry()` 是接收點雲的容器。
- 回傳：實際寫入的點數；檔案缺失或副檔名不符回 `None`。
- 檔案內容被截斷（header 宣告的點數比實際能讀到的多）會 `raise ValueError` 並清空 geometry，不會回傳部分成功的點數。

座標系統保持 COLMAP 原樣（Z-up）；要在 Houdini Y-up 顯示自行接 Transform SOP。

#### 使用方式

在 Python SOP 內：

```python
from chd_toolkits.colmap_points import read_points3d_binary_to_geo
node = hou.pwd()
read_points3d_binary_to_geo("/path/to/points3D.bin", node)
```

---

### `nerfstudio_cam` — Nerfstudio `transforms.json` → 動畫相機

#### `create_animated_camera`

```python
create_animated_camera(
    json_path: str,
    global_scale: float = 1.0,
    cam_name: str = "Nerfstudio_Animated_Cam",
    aperture_width: float = 36.0,
    subnet_name: str = "NeRF_Import",
) -> Optional[hou.ObjNode]
```

讀 Nerfstudio `transforms.json`，在 `/obj/<subnet_name>` 下建立一台 keyframed 相機，每個 JSON frame → 一組 tx/ty/tz/rx/ry/rz keyframe，套 `linear()`。

- `json_path`：Nerfstudio JSON 路徑。
- `global_scale`：translation 縮放倍率。
- `cam_name`：相機節點名（已存在會 destroy 再重建）。
- `aperture_width`：底片寬度 (mm)，與 JSON 的 `fl_x`、`w` 一起算 focal length (mm)。
- `subnet_name`：容納相機的 subnet，無則建立。
- 回傳：建立的 `hou.ObjNode`；檔案不存在或無 frame 時回 `None`。

執行後會把 playbar 範圍設成首末 frame，並 set current frame 到起始 frame。座標系統校正目前是 identity（`hou.hmath.buildRotate(0, 0, 0)`），預留 hook，需要再自行接 Transform。

---

### `stitch_usd_clips` — USD Value Clips stitcher

把逐 frame 的 USD cache 串成單一 stage 的 USD Value Clips 形式，含 manifest / topology 自動產出與遞迴偵測 animated prim。

#### `stitch_clips`

```python
stitch_clips(
    filepath_template: str,
    primpath: str,
    output_path: str,
    frame_range: tuple[int, int],
    scene_range: tuple[int, int] | None = None,
    loop: bool = False,
    clip_set: str = "default",
    clip_primpath: str | None = None,
    strict: bool = False,
    gen_topology: bool = True,
    gen_manifest: bool = True,
    probe_frame: int | None = None,
    auto_detect_prim: bool = True,
    fps: float | None = None,
) -> None
```

支援的 frame token：

- Python `.format` 風格：`/cache/sim.{frame:04d}.usd`
- Houdini `$F` 風格：`/cache/sim.$F4.usd`

主要參數：

| 參數 | 預設 | 用途 |
|---|---|---|
| `filepath_template` | (必填) | 逐 frame 路徑樣板，支援 `{frame:04d}` 或 `$F4` |
| `primpath` | (必填) | 套用 clips 的 stage prim path |
| `output_path` | (必填) | 輸出 `.usd` / `.usda` / `.usdc` |
| `frame_range` | (必填) | 原始檔案 frame 範圍 `(start, end)`（含尾） |
| `scene_range` | `None` | 場景時間軸範圍；`None` 等於 `frame_range` |
| `loop` | `False` | scene_range 比 frame_range 長時迴圈延伸 |
| `clip_set` | `"default"` | clip set 名稱 |
| `clip_primpath` | `None` | clip 檔案內的 prim 路徑；`None` 等於 `primpath` |
| `strict` | `False` | 任一 frame 檔案缺失即 raise `FileNotFoundError` |
| `gen_topology` / `gen_manifest` | `True` | 是否自動產生 topology / manifest |
| `probe_frame` | `None` | 生成 topology / manifest 的 frame；`None` 用 `frame_range` 起點 |
| `auto_detect_prim` | `True` | 遞迴偵測 animated child prim |
| `fps` | `None` | 輸出 stage 的 FPS；`None` 自動從 probe frame 偵測 |

失敗條件：
- `frame_range` 或 `scene_range` 的 end < start → `ValueError`
- `probe_frame` 不在 `frame_range` 內 → `ValueError`
- `probe_frame` 對應檔案不存在 → `FileNotFoundError`
- `strict=True` 且任一 frame 檔案缺失 → `FileNotFoundError`
- 無法在 stage 上 define `primpath` → `RuntimeError`

#### 使用範例

```python
from chd_toolkits.stitch_usd_clips import stitch_clips

stitch_clips(
    filepath_template="/cache/sim.{frame:04d}.usd",
    primpath="/World/Geo/sim",
    output_path="/cache/stitched.usd",
    frame_range=(1, 50),
)
```

#### 輔助函式

`stitch_usd_clips` 也對外暴露幾個可獨立使用的工具：

- `resolve_filepath(template, frame)` — 解析 `{frame:04d}` / `$F` 樣板
- `build_clip_frame_lists(frame_range, scene_range, loop)` — 計算 scene/file frame 對應 list
- `validate_files(filepaths, strict=False)` — 檢查檔案存在
- `find_all_animated_prims(probe_frame_path, root_primpath)` — 走訪 probe frame 找出有 timesample 的 prim
- `generate_topology(probe_frame_path, clip_primpath, topology_path)` — 產生 topology layer
- `generate_manifest(probe_frame_path, clip_primpath, manifest_path)` — 產生 manifest layer

## 設計筆記

- **命名**：全部 snake_case，與 Python 慣例一致。
- **回傳型別**：`Optional[List[...]]` 用於「資源不存在」回 None 的查詢；恆定回 list 的函式直接標 `List[...]`。
- **時間參數**：`core` 的 `compute_prim_scale` / `primitive_xform` 接受 `int`、`float` 或 `Usd.TimeCode`；非 TimeCode 會自動包成 `Usd.TimeCode(time)`。
- **mirror 偵測**：`compute_prim_scale` 用 rotation determinant < 0 判定鏡像，慣例上在 x 軸帶出負號。
- **cycle detection**：`get_all_layers_in_layer` 用 visited set 追蹤 `layer.realPath` / 絕對路徑，避免 sublayer 互相 reference 造成無窮遞迴。
- **scipy 是 optional**：透過 `importlib.util.find_spec` 偵測；不存在時 `scipy_convolve2d` 不會被定義（不是 stub），呼叫端會看到 `AttributeError` 而非靜默走錯路徑。
- **無 Houdini 的場景**：`__init__.py` 對 `from .core import ...` 加 try/except，純 Python（無 `hou`、有 `pxr`）也能 `from chd_toolkits.stitch_usd_clips import stitch_clips` 當函式用。

## 參考文件

- HOM Geometry：<https://www.sidefx.com/docs/houdini/hom/hou/Geometry.html>
- HOM Matrix4：<https://www.sidefx.com/docs/houdini/hom/hou/Matrix4.html>
- HOM InterruptableOperation：<https://www.sidefx.com/docs/houdini/hom/hou/InterruptableOperation.html>
- Gf.Matrix4d：<https://openusd.org/release/api/class_gf_matrix4d.html>
- UsdGeomXformable：<https://openusd.org/release/api/class_usd_geom_xformable.html>
- UsdShade MaterialBindingAPI：<https://openusd.org/release/api/class_usd_shade_material_binding_a_p_i.html>
- USD Value Clips：<https://openusd.org/release/api/_usd__page__value_clips.html>
- Sdf.Layer：<https://openusd.org/release/api/class_sdf_layer.html>
- COLMAP Output Format：<https://colmap.github.io/format.html>
- Nerfstudio `transforms.json`：<https://docs.nerf.studio/quickstart/data_conventions.html>
