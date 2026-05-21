import maya.cmds as cmds

def compare_dagpose_nodes(pose_nodes=None, tolerance=1e-5):
    # 方法一：比較 dagPose 節點
    if not pose_nodes:
        pose_nodes = cmds.ls(type='dagPose')
        
    if len(pose_nodes) < 2:
        print("場景中的 dagPose 節點少於 2 個，無需比較。")
        return True

    # 儲存結構: {joint_name: {pose_node: [matrix_elements]}}
    joint_matrices = {}
    
    for pose in pose_nodes:
        members = cmds.dagPose(pose, query=True, members=True)
        if not members:
            continue

        for member in members:
            if not cmds.objExists(member):
                continue

            # 查詢該成員實際連接到 dagPose.worldMatrix 的索引
            connections = cmds.listConnections(
                f"{member}.worldMatrix[0]", plugs=True, destination=True
            ) or []
            conn_index = None
            for conn in connections:
                if f"{pose}.worldMatrix[" in conn:
                    conn_index = int(conn.split('[')[-1].split(']')[0])
                    break

            if conn_index is None:
                continue

            try:
                matrix = cmds.getAttr(f"{pose}.worldMatrix[{conn_index}]")
            except Exception:
                continue

            if member not in joint_matrices:
                joint_matrices[member] = {}
            joint_matrices[member][pose] = matrix

    mismatch_count = 0
    for joint, poses in joint_matrices.items():
        if len(poses) < 2:
            continue
            
        pose_names = list(poses.keys())
        base_pose = pose_names[0]
        base_matrix = poses[base_pose]
        
        for other_pose in pose_names[1:]:
            other_matrix = poses[other_pose]
            
            # 比對 16 個矩陣元素
            is_different = False
            for v1, v2 in zip(base_matrix, other_matrix):
                if abs(v1 - v2) > tolerance:
                    is_different = True
                    break
            
            if is_different:
                print(f"[不一致] 關節 '{joint}' 在 '{base_pose}' 與 '{other_pose}' 中的 bindpose 矩陣不同！")
                mismatch_count += 1

    return mismatch_count == 0


def compare_skincluster_bindposes(skin_clusters=None, tolerance=1e-5):
    # 方法二：比較 skinCluster 綁定矩陣（最準確）
    if not skin_clusters:
        skin_clusters = cmds.ls(type='skinCluster')
        
    if len(skin_clusters) < 2:
        print("場景中的 skinCluster 節點少於 2 個，無需比較。")
        return True

    # 儲存結構: {joint_name: {skin_cluster: [bind_pre_matrix]}}
    joint_bind_matrices = {}

    for sc in skin_clusters:
        influences = cmds.skinCluster(sc, query=True, influence=True) or []
        
        for inf in influences:
            # 尋找該關節連接到 skinCluster.matrix[X] 的索引 X
            connections = cmds.listConnections(f"{inf}.worldMatrix[0]", plugs=True, destination=True) or []
            conn_index = None
            for conn in connections:
                if f"{sc}.matrix[" in conn:
                    conn_index = int(conn.split('[')[-1].split(']')[0])
                    break
            
            if conn_index is not None:
                try:
                    # 讀取綁定時的逆世界矩陣 (bindPreMatrix)
                    matrix = cmds.getAttr(f"{sc}.bindPreMatrix[{conn_index}]")
                except Exception:
                    continue
                
                if inf not in joint_bind_matrices:
                    joint_bind_matrices[inf] = {}
                joint_bind_matrices[inf][sc] = matrix

    mismatch_count = 0
    for joint, scs in joint_bind_matrices.items():
        if len(scs) < 2:
            continue
            
        sc_names = list(scs.keys())
        base_sc = sc_names[0]
        base_matrix = scs[base_sc]
        
        for other_sc in sc_names[1:]:
            other_matrix = scs[other_sc]
            
            # 比對 16 個矩陣元素
            is_different = False
            for v1, v2 in zip(base_matrix, other_matrix):
                if abs(v1 - v2) > tolerance:
                    is_different = True
                    break
            
            if is_different:
                print(f"[不一致] 關節 '{joint}' 在 '{base_sc}' 與 '{other_sc}' 中的 bindPreMatrix 不同！")
                mismatch_count += 1

    return mismatch_count == 0

