from pxr import Usd
import json
import logging

logger = logging.getLogger(__name__)


def usd2json(stage: Usd.Stage, file_path: str) -> None:
    """
    usd2json Convert USD hierarchy to json file

    Args:
        stage (Usd.Stage): USD stage
        file_path (str): json file path
    """
    stage_data: dict = {}

    for prim in stage.Traverse():
        parent_components = str(prim.GetPath()).split("/")[1:-1]
        iter_data = stage_data
        for comp in parent_components:
            iter_data = iter_data[comp]
        iter_data[prim.GetName()] = {
            "#": {
                "type": prim.GetTypeName(),
                "kind": Usd.ModelAPI(prim).GetKind(),
            }
        }

    with open(file_path, "w") as f:
        json.dump(stage_data, f, indent=4, sort_keys=True)


def diff_usd_files(file1_path: str, file2_path: str, leaf_only: bool = True) -> None:
    """
    diff_usd_files Compare 2 USD files

    Args:
        file1_path (str): usd file path
        file2_path (str): usd file path
        leaf_only (bool, optional): if compare leaf primitives only. Defaults to True.
    """

    file_paths = (file1_path, file2_path)

    stage1 = Usd.Stage.Open(file1_path)
    stage2 = Usd.Stage.Open(file2_path)

    stages = (stage1, stage2)

    for i in range(2):
        main_stage = stages[i]
        alt_stage = stages[1 - i]

        main_path = file_paths[i]
        alt_path = file_paths[1 - i]

        logger.info("")
        logger.info("===")
        logger.info(f"check primitives in {main_path}")
        logger.info("")

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
                logger.info(f'{prim_path}\tin "{main_path}", not in "{alt_path}"')
        logger.info("")
        if nums == 0:
            logger.info("no primitives checked")
        else:
            logger.info(f"err ratio: {err / nums * 100:.2f}%")
