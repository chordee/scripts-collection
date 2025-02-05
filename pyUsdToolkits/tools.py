from pxr import Usd, UsdGeom
import json
import math


def usd2json(stage: Usd.Stage, file_path: str) -> None:
    """
    usd2json Convter USD hirechy to json file

    Args:
        stage (Usd.Stage): USD stage
        file_path (str): json file path
    """
    stage_data = {}

    for prim in stage.TraverseAll():

        name = prim.GetName()
        if prim.GetParent().IsPseudoRoot():
            data = stage_data
            root_level = True
        else:
            data = {}
            root_level = False
        type_name = prim.GetTypeName()
        kind = Usd.ModelAPI(prim).GetKind()

        misc_data = {'type': type_name}
        misc_data['kind'] = kind
        prim_data = {'#': misc_data}
        data[name] = prim_data

        if not root_level:
            parents = str(prim.GetPath()).split('/')[1:-1]
            iter_data = stage_data
            for parent in parents:
                iter_data = iter_data[parent]
            iter_data[name] = data[name]

    j = json.dumps(stage_data, indent=4)

    with open(file_path, 'w') as f:
        json.dump(stage_data, f)


def diff_usd_files(file1_path: str, file2_path: str, leaf_only: bool = True) -> None:
    """
    diff_usd_files Compare 2 USD files

    Args:
        file1_path (str): usd file path
        file2_path (str): usd file path
        leaf_only (bool, optional): if compare leaf primitive only. Defaults to True.
    """

    file_paths = (file1_path, file2_path)

    stage1 = Usd.Stage.Open(file1_path)
    stage2 = Usd.Stage.Open(file2_path)

    stages = (stage1, stage2)

    for i in range(2):
        main_stage = stages[i]
        alt_stage = stages[1-i]

        main_path = file_paths[i]
        alt_path = file_paths[1-i]

        print()
        print('===')
        print(f'check primities in {main_path}')
        print()

        nums = 0
        err = 0
        for prim in main_stage.TraverseAll():
            if leaf_only:
                children = prim.GetAllChildren()
                if len(children) != 0:
                    continue
            nums += 1
            prim_path = prim.GetPath()
            prim_ = alt_stage.GetPrimAtPath(prim_path)
            if not prim_.IsValid():
                err += 1
                print(prim_path, end='\t')
                print(f'in "{main_path}" , not in "{alt_path}')
        print()
        print(f'err ratio: {0:.2f}%'.format(err / nums * 100), end='\n')


def orth_turntable_camera(stage: Usd.Stage, prim_path: str, start_frame: int, frame_range: int,
                          padding_scale: float = 1.2, camera_root: str = "/turntable", camera_name: str = "camera") -> None:
    """
    orth_turntable_camera Turntable camera generator

    Args:
        stage (Usd.Stage): USD stage to add turntable camera
        prim_path (str): focus primtive
        start_frame (int): start frame
        frame_range (int): end frame
        padding_scale (float, optional): Screen window padding. Defaults to 1.2.
        camera_root (str, optional): The parent primtive of camaera. This primtive will be rotated 360 degrees. Defaults to "/turntable".
        camera_name (str, optional): Camera primtive which will offset away from focus primtive. Defaults to "camera".
    """
    prim = stage.GetPrimAtPath(prim_path)

    bb = UsdGeom.Boundable(prim)

    bb_data = bb.ComputeWorldBound(1, 'default')
    box = bb_data.GetBox()
    bb_min = box.GetMin()
    bb_max = box.GetMax()
    all_widths = bb_max - bb_min
    cen = all_widths/2 + bb_min
    max_width = pow(all_widths[1] ** 2 + all_widths[2] ** 2, .5)
    trans = cen + [0, 0, max_width*2]
    scale = (math.floor(max_width*100)+1)/(10/padding_scale)

    tall = bb_max[1] - bb_min[1]
    width = max_width
    ratio = tall / width

    cam = UsdGeom.Camera.Define(stage, camera_root + '/' + camera_name)
    cam.CreateProjectionAttr().Set('orthographic')
    cam.CreateHorizontalApertureAttr().Set(1)
    cam.CreateVerticalApertureAttr().Set(ratio)
    cam.CreateClippingRangeAttr().Set((0, 100000))

    cam.AddTranslateOp().Set(trans)
    cam.AddScaleOp().Set((scale, scale, scale))
    xform_prim = UsdGeom.Xform.Define(stage, camera_root)

    rot_attr = xform_prim.AddRotateXYZOp()

    for i in range(start_frame, start_frame + frame_range+1):
        step = 360/frame_range
        rot_attr.Set((0, i*step, 0), time=i+1)
