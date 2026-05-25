# Houdini Python Toolkit (`chd_toolkits`)

`HOUDINI/scripts/python/chd_toolkits/` 是一個 Houdini 用的 Python package，整合：

- Houdini geometry 與 numpy 的橋接
- 影像 2D 卷積
- USD prim / material / clip / layer 查詢（含 USD↔Houdini matrix 轉換）
- COLMAP `points3D.bin` → Houdini 點雲
- Nerfstudio `transforms.json` → Houdini 動畫相機
- USD Value Clips stitcher（純 Python 函式介面，無 CLI）

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
HOUDINI/scripts/python/chd_toolkits/
├── __init__.py            re-export core helpers; defensive 對 plain Python（無 hou）
├── core.py                Houdini / numpy / USD 核心 helper
├── colmap_points.py       COLMAP .bin → Houdini geometry
├── nerfstudio_cam.py      Nerfstudio transforms.json → Houdini 動畫相機
└── stitch_usd_clips.py    USD Value Clips stitcher（純 Python 函式介面）
```

`__init__.py` 採 try/except 包裹 `from .core import ...`，所以在 plain Python（無 `hou`、有 `pxr`）下也能 `from chd_toolkits.stitch_usd_clips import stitch_clips` 而不會被 `core` 的 import 失敗連帶卡住。

## 相依

- `hou`（Houdini 內建）— core / colmap_points / nerfstudio_cam 需要
- `numpy` — core / colmap_points 需要
- `pxr.Usd` / `pxr.UsdGeom` / `pxr.UsdShade` / `pxr.Sdf` / `pxr.Gf` — core / stitch_usd_clips 需要（Houdini 或 `pip install usd-core`）
- `scipy`（**可選**；若存在則自動暴露 `chd_toolkits.scipy_convolve2d`）

## API

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

從 `prim_path` 開始用 `Usd.PrimRange` traverse，對每個 prim 呼叫 `get_all_asset_paths_from_prim` 並 union。`prim_path` 不存在時回空 list。

#### `get_all_clip_sequences_from_stage`

```python
get_all_clip_sequences_from_stage(
    stage: Usd.Stage,
    prim_path: Union[str, Sdf.Path] = '/',
) -> List[str]
```

從 `prim_path` 開始 traverse stage，對每個有 `clips` metadata 的 prim 呼叫 `get_all_clip_sequences_from_prim` 並 union。

#### `get_all_layers_in_layer`

```python
get_all_layers_in_layer(usd_layer: Union[str, Sdf.Layer]) -> List[str]
```

走訪 layer 的所有 composition asset dependencies（sublayer / reference / payload，用 `Sdf.Layer.GetCompositionAssetDependencies`）並遞迴展開。Cycle detection key 用 `layer.realPath`（fallback `identifier`）統一比對，避免 root 用相對路徑開啟時繞過檢查。主 layer 開不起來時回空 list。

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
- 回傳：實際寫入的點數；失敗回 `None`。

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
