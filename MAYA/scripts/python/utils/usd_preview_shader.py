from maya import cmds


# 通道對應到 file -> shader 的 (source attr, destination attr)；未列出者預設 outColorR -> <channel>
_CHANNEL_CONNECTION_MAP = {
    "diffuse": ("outColor", "diffuseColor"),
    "emissive": ("outColor", "emissiveColor"),
    "specular": ("outColor", "specularColor"),
    "normal": ("outColor", "normal"),
}


def build_usd_preview_shader(name, textures):
    """
    建立 usdPreviewSurface shader 與對應 shadingGroup，並依 textures 字典連接貼圖。

    Args:
        name: shader 名稱前綴，空字串代表使用 Maya 預設命名
        textures: {channel: file_path}，channel 可為 diffuse/emissive/specular/normal/
            occlusion/opacity/ior/metallic/roughness/displacement

    Returns:
        建立的 shader 節點名稱
    """
    shader_name = name if name else None

    create_shader_args = {"asShader": 1}
    create_sg_args = {"empty": True, "renderable": True, "noSurfaceShader": True}
    if shader_name:
        create_shader_args["name"] = shader_name.title()
        create_sg_args["name"] = shader_name.title() + "_SG"

    shader = cmds.shadingNode("usdPreviewSurface", **create_shader_args)
    shader_sg = cmds.sets(**create_sg_args)
    cmds.connectAttr(shader + ".outColor", shader_sg + ".surfaceShader")

    for channel, file_path in textures.items():
        if not file_path:
            continue

        create_tex_args = {"at": True}
        create_place2d_args = {"au": True}
        if shader_name:
            create_tex_args["name"] = (
                shader_name.title() + "_" + channel.title() + "_file"
            )
            create_place2d_args["name"] = shader_name.title() + "_place2dTexture"

        file_node = cmds.shadingNode("file", **create_tex_args)
        cmds.setAttr(file_node + ".fileTextureName", file_path, typ="string")
        place2d_node = cmds.shadingNode("place2dTexture", **create_place2d_args)
        cmds.connectAttr(place2d_node + ".outUV", file_node + ".uvCoord")

        src_attr, dst_attr = _CHANNEL_CONNECTION_MAP.get(channel, ("outColorR", channel))
        cmds.connectAttr(file_node + "." + src_attr, shader + "." + dst_attr)

    return shader
