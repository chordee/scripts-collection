import struct
import argparse
from pathlib import Path
import sys

# Expected layout for Unreal GS plugin:
# x, y, z                → 3 floats
# nx, ny, nz             → 3 floats (dummy 0.0, 0.0, 1.0)
# f_dc_0..2              → 3 floats
# f_rest_0..44           → 45 floats
# opacity                → 1 float
# scale_0..2             → 3 floats
# rot_0..3               → 4 floats
# Total: 3 + 3 + 3 + 45 + 1 + 3 + 4 = 62 floats = 248 bytes

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Convert PLY file to be Unreal Engine compatible.")
    parser.add_argument("input_file", help="Input PLY file")
    parser.add_argument("output_file", help="Output PLY file")
    args = parser.parse_args()

    input_path = Path(args.input_file)
    if not input_path.is_file():
        print(f"Error: Input file not found at {args.input_file}")
        sys.exit(1)

    expected_floats_per_vertex = 62
    dummy_normal = (0.0, 0.0, 1.0)

    # Step 1: Read original PLY header and extract vertex count
    with open(args.input_file, 'rb') as f:
        header = []
        while True:
            line = f.readline()
            header.append(line)
            if line.strip() == b'end_header':
                break

        # Get vertex count
        vertex_count = 0
        for line in header:
            if line.startswith(b'element vertex'):
                vertex_count = int(line.strip().split()[-1])
                break

        binary_data = f.read()

    # Step 2: Determine actual float count per vertex in original
    original_floats_per_vertex = len(binary_data) // (vertex_count * 4)
    if len(binary_data) != vertex_count * original_floats_per_vertex * 4:
        raise ValueError("File size doesn't match expected float count per vertex.")

    # Step 3: Parse original binary data as list of float tuples
    all_vertices = struct.unpack('<' + 'f' * (vertex_count * original_floats_per_vertex), binary_data)

    # Step 4: Rebuild fixed vertex data
    fixed_binary_data = bytearray()
    for i in range(vertex_count):
        v = all_vertices[i * original_floats_per_vertex:(i + 1) * original_floats_per_vertex]
        
        if len(v) < 54:
            raise ValueError(f"Vertex {i} has insufficient data (expected 54 floats).")

        # Use existing values
        x, y, z = v[0:3]
        f_dc = v[3:6]
        f_rest = v[6:51]  # up to f_rest_44
        opacity = v[51]
        scale = v[52:55]
        rot = v[55:59]

        # Fix rest padding if needed
        if len(f_rest) < 45:
            f_rest += (0.0,) * (45 - len(f_rest))

        full_vertex = (
            x, y, z,
            *dummy_normal,
            *f_dc,
            *f_rest,
            opacity,
            *scale,
            *rot
        )

        fixed_binary_data += struct.pack('<' + 'f' * expected_floats_per_vertex, *full_vertex)

    # Step 5: Build new PLY header
    new_header = f"""ply
    format binary_little_endian 1.0
    element vertex {vertex_count}
    property float x
    property float y
    property float z
    property float nx
    property float ny
    property float nz
    property float f_dc_0
    property float f_dc_1
    property float f_dc_2
    """ + '\n'.join([f'property float f_rest_{i}' for i in range(45)]) + """
    property float opacity
    property float scale_0
    property float scale_1
    property float scale_2
    property float rot_0
    property float rot_1
    property float rot_2
    property float rot_3
    end_header
    """

    # Step 6: Write final file
    with open(args.output_file, 'wb') as f:
        f.write(new_header.encode('utf-8'))
        f.write(fixed_binary_data)

    print(f"✅ Done! Unreal-compatible PLY written to: {args.output_file}")
