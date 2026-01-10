import struct
import numpy as np
import os
import hou

def read_points3d_binary_to_geo(path_to_model_file, parent_node):
    if not os.path.exists(path_to_model_file):
        hou.ui.displayMessage(f"File not found: {path_to_model_file}")
        return

    # Simple extension check
    if not path_to_model_file.endswith('.bin'):
        hou.ui.displayMessage("Error: This script only supports COLMAP .bin format.\nIf you want to read .ply, please use File SOP directly.")
        return

    geo = parent_node.geometry()
    geo.clear()
    
    # Add attributes
    attr_Cd = geo.addAttrib(hou.attribType.Point, "Cd", (0.0, 0.0, 0.0))
    attr_err = geo.addAttrib(hou.attribType.Point, "error", 0.0)

    print(f"Reading {path_to_model_file}...")
    
    with open(path_to_model_file, "rb") as fid:
        # 1. Read total number of points (uint64)
        data = fid.read(8)
        if len(data) < 8:
            raise ValueError("File is too small or empty.")
            
        num_points = struct.unpack("<Q", data)[0]
        print(f"Total points to read: {num_points}")

        # Use Houdini progress bar to prevent UI freeze with large files
        with hou.InterruptableOperation("Importing COLMAP Points", open_interrupt_dialog=True) as operation:
            
            for i in range(num_points):
                # Update progress every 1000 points
                if i % 1000 == 0:
                    percent = float(i) / num_points
                    operation.updateProgress(percent)
                
                # 2. Read POINT3D_ID(8), X,Y,Z(24), R,G,B(3), ERROR(8) = 43 bytes
                binary_content = fid.read(43)
                
                # [Critical Fix]: If less than 43 bytes read, it means EOF or format error
                if len(binary_content) < 43:
                    print(f"Error at point {i}: Expected 43 bytes, got {len(binary_content)}")
                    break 

                struct_fmt = "<QdddBBBd"
                data = struct.unpack(struct_fmt, binary_content)
                
                # Parse data
                # point3D_id = data[0] # ID not used for now
                xyz = (data[1], data[2], data[3])
                rgb = (data[4]/255.0, data[5]/255.0, data[6]/255.0) # Convert to 0-1
                error = data[7]
                
                # 3. Read Track length
                track_len_data = fid.read(8)
                if len(track_len_data) < 8:
                    break
                track_length = struct.unpack("<Q", track_len_data)[0]
                
                # 4. Skip Track content (we only want point cloud positions)
                # Each track element is 2 uint32 (4+4=8 bytes)
                fid.seek(track_length * 8, 1) # 1 means move from current position
                
                # Create point in Houdini
                pt = geo.createPoint()
                
                # Fix coordinate system (NeRF Z-up -> Houdini Y-up)
                # Manual swap: (x, y, z) -> (x, -z, y) depending on your transforms.json
                # Keeping original data for now, you can fix it later with Transform SOP
                pt.setPosition(xyz)
                
                pt.setAttribValue(attr_Cd, rgb)
                pt.setAttribValue(attr_err, error)

    print("Done.")