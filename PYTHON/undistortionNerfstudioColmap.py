import json
import cv2
import numpy as np
import os
from pathlib import Path
import argparse

# ==============================================================================
# Configuration Area
# ==============================================================================
# Whether to crop the black borders generated after undistortion?
# True: Crop (FOV will be slightly narrower, but full frame)
# False: Keep black borders (Maximize FOV, but image edges will have black curved areas)
CROP_TO_VALID = True
# ==============================================================================

def undistort_process(json_path, output_dir, crop_to_valid):
    # Convert paths to absolute to handle relative paths correctly
    json_path = Path(os.path.abspath(json_path))
    output_path = Path(os.path.abspath(output_dir))

    if not json_path.exists():
        print(f"Error: JSON file not found: {json_path}")
        return

    # Create output directory
    images_out_dir = output_path / "images_undistorted"
    images_out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading JSON: {json_path}")
    with open(json_path, 'r') as f:
        data = json.load(f)

    # 1. Read camera parameters
    w = int(data.get("w", 1920))
    h = int(data.get("h", 1080))
    fl_x = float(data.get("fl_x", 1000))
    fl_y = float(data.get("fl_y", fl_x)) # If fl_y is missing, it usually defaults to fl_x
    cx = float(data.get("cx", w / 2))
    cy = float(data.get("cy", h / 2))

    # 2. Read distortion coefficients
    k1 = float(data.get("k1", 0.0))
    k2 = float(data.get("k2", 0.0))
    k3 = float(data.get("k3", 0.0))
    k4 = float(data.get("k4", 0.0))
    p1 = float(data.get("p1", 0.0))
    p2 = float(data.get("p2", 0.0))

    # Construct Camera Matrix
    K = np.array([
        [fl_x, 0,    cx],
        [0,    fl_y, cy],
        [0,    0,    1 ]
    ])

    # Construct Distortion Vector
    D = np.array([k1, k2, p1, p2, k3, k4, 0.0, 0.0]) # OpenCV order

    print(f"Camera Matrix:\n{K}")
    print(f"Distortion Coeffs: {D}")

    # 3. Calculate Optimal New Camera Matrix
    # This step is important because after straightening the image, the original focal length and optical center might change
    # alpha=0: Crop all black borders (FOV becomes smaller)
    # alpha=1: Keep all pixels (will have black borders)
    alpha = 0 if crop_to_valid else 1
    new_K, roi = cv2.getOptimalNewCameraMatrix(K, D, (w, h), alpha, (w, h))
    
    # ROI for cropping (x, y, w, h)
    x, y, w_roi, h_roi = roi

    # 4. Prepare new JSON data
    new_data = data.copy()
    
    # Update intrinsics in JSON to the new values "after undistortion"
    new_data["fl_x"] = new_K[0, 0]
    new_data["fl_y"] = new_K[1, 1]
    new_data["cx"] = new_K[0, 2]
    new_data["cy"] = new_K[1, 2]
    new_data["w"] = w_roi if crop_to_valid else w
    new_data["h"] = h_roi if crop_to_valid else h
    
    # Zero out distortion parameters (since the image is now straight)
    for key in ["k1", "k2", "k3", "k4", "p1", "p2"]:
        new_data[key] = 0.0

    new_frames = []
    frames = data.get("frames", [])
    
    print(f"Processing {len(frames)} images...")

    # 5. Start batch processing images
    json_dir = Path(json_path).parent

    for idx, frame in enumerate(frames):
        # Process path
        rel_path = frame["file_path"]
        # Try to combine absolute path
        img_path = json_dir / rel_path
        
        if not img_path.exists():
            print(f"Warning: Image not found: {img_path}")
            continue

        # Read image
        img = cv2.imread(str(img_path))
        if img is None:
            continue

        # [Core Step] Undistort
        dst = cv2.undistort(img, K, D, None, new_K)

        # Crop (if CROP_TO_VALID = True)
        if crop_to_valid:
            dst = dst[y:y+h_roi, x:x+w_roi]

        # Save file
        img_name = Path(rel_path).name
        save_path = images_out_dir / img_name
        cv2.imwrite(str(save_path), dst)

        # Update frame's file_path to point to the new image
        new_frame = frame.copy()
        # Write relative path here for easier JSON portability
        new_frame["file_path"] = f"images_undistorted/{img_name}"
        new_frames.append(new_frame)

        if idx % 20 == 0:
            print(f"Processed {idx}/{len(frames)}...")

    new_data["frames"] = new_frames

    # 6. Save new JSON
    new_json_path = output_path / "transforms_undistorted.json"
    with open(new_json_path, 'w') as f:
        json.dump(new_data, f, indent=4)

    print("Done!")
    print(f"Undistorted images saved to: {images_out_dir}")
    print(f"New JSON saved to: {new_json_path}")
    print("Use this new JSON in Houdini!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Undistort images and transforms.json")
    parser.add_argument("--json_path", type=str, required=True, help="Path to input transforms.json")
    parser.add_argument("--output_dir", type=str, required=True, help="Path to output directory")
    parser.add_argument("--crop", dest="crop_to_valid", action="store_true", help="Crop to valid region")
    parser.add_argument("--no-crop", dest="crop_to_valid", action="store_false", help="Do not crop")
    parser.set_defaults(crop_to_valid=CROP_TO_VALID)
    
    args = parser.parse_args()
    undistort_process(args.json_path, args.output_dir, args.crop_to_valid)