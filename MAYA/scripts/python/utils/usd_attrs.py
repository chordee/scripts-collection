from maya import cmds


USD_TYPE_NAME_ATTR = "USD_typeName"


def set_usd_type_name(obj, type_name):
    """
    在指定 Maya 節點上設定 USD_typeName 屬性，供 Maya-USD 匯出時識別 prim 型別。

    Args:
        obj: Maya 節點名稱（建議為長路徑）
        type_name: USD prim type 名稱，例如 "SkelRoot"、"Xform"、"Scope"
    """
    if not cmds.attributeQuery(USD_TYPE_NAME_ATTR, node=obj, exists=True):
        cmds.addAttr(obj, ln=USD_TYPE_NAME_ATTR, dt="string")
    cmds.setAttr(obj + "." + USD_TYPE_NAME_ATTR, type_name, typ="string")
