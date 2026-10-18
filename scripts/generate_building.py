#!/usr/bin/env python3
"""Generate a clay-style NYC setback tower as glTF, plus night color textures.

Day color maps are referenced by the glTF. Night maps share the same UVs and
are swapped at runtime by material name, the same way pengzhe.ng does it.
"""

import json
import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEX = ROOT / "textures"
MODEL = ROOT / "models"

REPEAT = 10497
CLAMP = 33071
LINEAR = 9729
LINEAR_MIPMAP = 9987


def write_png(path, width, height, pixels):
    raw = bytearray()
    row = width * 3
    for y in range(height):
        raw.append(0)
        raw.extend(pixels[y * row : (y + 1) * row])
    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def hash2(ix, iy, seed):
    n = (ix * 374761393 + iy * 668265263 + seed * 1440662683) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    return (n & 0xFFFF) / 65535.0


def noise(x, y, period, seed):
    x %= period
    y %= period
    x0 = int(x)
    y0 = int(y)
    fx = x - x0
    fy = y - y0
    sx = fx * fx * (3 - 2 * fx)
    sy = fy * fy * (3 - 2 * fy)

    def h(ix, iy):
        return hash2(ix % period, iy % period, seed)

    a = h(x0, y0)
    b = h(x0 + 1, y0)
    c = h(x0, y0 + 1)
    d = h(x0 + 1, y0 + 1)
    return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def clamp_byte(v):
    return max(0, min(255, int(v)))


def shade(rgb, scale, bias=(0, 0, 0)):
    return tuple(clamp_byte(rgb[i] * scale + bias[i]) for i in range(3))


def brick_texture(night):
    size = 256
    brick_w, brick_h = 28, 12
    mortar = 2
    pixels = bytearray(size * size * 3)
    mortar_c = (92, 78, 70) if night else (214, 196, 178)
    for y in range(size):
        row = (y // brick_h)
        phase = (brick_w // 2) if row % 2 else 0
        local_y = y % brick_h
        for x in range(size):
            xx = (x + phase) % size
            local_x = xx % brick_w
            joint = local_x < mortar or local_y < mortar or local_y >= brick_h - 1
            if joint:
                rgb = mortar_c
            else:
                n = noise(x / 3, y / 3, 64, 3)
                if night:
                    base = mix((78, 42, 36), (108, 58, 46), n)
                else:
                    base = mix((166, 78, 58), (196, 104, 74), n)
                speck = noise(x, y, 128, 9)
                rgb = shade(base, 0.92 + speck * 0.12)
            i = (y * size + x) * 3
            pixels[i : i + 3] = bytes(rgb)
    return size, size, pixels


def ashlar_texture(night, seed, light, dark):
    size = 256
    course = 32
    joint = 2
    pixels = bytearray(size * size * 3)
    joint_c = shade(dark, 0.45 if night else 0.62)
    for y in range(size):
        row = y // course
        stagger = 40 if row % 2 else 0
        local_y = y % course
        block_w = 72 if row % 3 else 54
        for x in range(size):
            xx = (x + stagger) % size
            local_x = xx % block_w
            is_joint = local_y < joint or local_x < joint
            if is_joint:
                rgb = joint_c
            else:
                n = noise((x + seed) / 4, (y + seed) / 4, 64, seed)
                base = mix(dark, light, n)
                rgb = shade(base, 0.94 + noise(x, y, 96, seed + 2) * 0.1)
            i = (y * size + x) * 3
            pixels[i : i + 3] = bytes(rgb)
    return size, size, pixels


def flat_texture(color, size=64, seed=1, variation=0.16):
    pixels = bytearray(size * size * 3)
    for y in range(size):
        for x in range(size):
            n = noise(x / 2, y / 2, size, seed)
            rgb = shade(color, 1 - variation * 0.5 + n * variation)
            i = (y * size + x) * 3
            pixels[i : i + 3] = bytes(rgb)
    return size, size, pixels


def wood_texture(night):
    size = 128
    pixels = bytearray(size * size * 3)
    for y in range(size):
        for x in range(size):
            stave = (x // 10) % 2
            grain = noise(x / 8, y, 32, 4)
            if night:
                base = (74, 52, 36) if stave else (62, 44, 32)
            else:
                base = (164, 122, 78) if stave else (146, 104, 66)
            rgb = shade(base, 0.88 + grain * 0.2)
            if x % 10 < 1:
                rgb = shade(rgb, 0.7)
            i = (y * size + x) * 3
            pixels[i : i + 3] = bytes(rgb)
    return size, size, pixels


def paint_window(pixels, width, height, col, row, cols, rows, night, kind):
    cell_w = width // cols
    cell_h = height // rows
    x0 = col * cell_w
    y0 = (rows - 1 - row) * cell_h
    for y in range(cell_h):
        for x in range(cell_w):
            u = x / cell_w
            v = y / cell_h
            muntin = abs(u - 0.5) < 0.035 or abs(v - 0.42) < 0.03
            frame = u < 0.06 or u > 0.94 or v < 0.06 or v > 0.94
            if kind == "store":
                muntin = abs(u - 0.33) < 0.02 or abs(u - 0.66) < 0.02 or abs(v - 0.72) < 0.025
            if frame or muntin:
                rgb = (28, 24, 22) if night else (46, 42, 40)
            elif not night:
                sky = 0.55 + 0.2 * (1 - v)
                if kind == "store":
                    rgb = shade((92, 112, 124), sky)
                else:
                    rgb = shade((58, 68, 78), sky)
            elif kind == "off":
                rgb = shade((32, 30, 34), 0.85 + 0.1 * v)
            elif kind == "shade" and v > 0.48:
                rgb = (42, 36, 32)
            elif kind == "dim":
                rgb = mix((120, 72, 36), (168, 104, 48), 1 - v)
            elif kind == "store":
                rgb = mix((255, 196, 120), (255, 150, 70), v)
            else:
                rgb = mix((255, 214, 150), (232, 132, 54), v * 0.85)
            i = ((y0 + y) * width + (x0 + x)) * 3
            pixels[i : i + 3] = bytes(rgb)


def glass_atlas(night):
    cols, rows = 8, 4
    width, height = 1024, 512
    pixels = bytearray(width * height * 3)
    kinds = [
        "on", "on", "dim", "shade", "off", "on", "dim", "on",
        "shade", "on", "on", "off", "dim", "on", "shade", "on",
        "on", "dim", "on", "on", "shade", "off", "on", "dim",
        "store", "store", "store", "on", "lamp", "off", "dim", "shade",
    ]
    for index, kind in enumerate(kinds):
        paint_window(pixels, width, height, index % cols, index // cols, cols, rows, night, "store" if kind == "store" else ("on" if kind == "lamp" else kind))
        if kind == "lamp":
            paint_window(pixels, width, height, index % cols, index // cols, cols, rows, night, "store" if night else "off")
    return width, height, pixels


class Prim:
    def __init__(self):
        self.positions = []
        self.normals = []
        self.uvs = []
        self.indices = []

    def add_quad(self, corners, normal, uvs):
        ax, ay, az = corners[1][0] - corners[0][0], corners[1][1] - corners[0][1], corners[1][2] - corners[0][2]
        bx, by, bz = corners[2][0] - corners[0][0], corners[2][1] - corners[0][1], corners[2][2] - corners[0][2]
        nx = ay * bz - az * by
        ny = az * bx - ax * bz
        nz = ax * by - ay * bx
        if nx * normal[0] + ny * normal[1] + nz * normal[2] < 0:
            corners = [corners[0], corners[3], corners[2], corners[1]]
            uvs = [uvs[0], uvs[3], uvs[2], uvs[1]]
        base = len(self.positions) // 3
        for corner, uv in zip(corners, uvs):
            self.positions.extend(corner)
            self.normals.extend(normal)
            self.uvs.extend(uv)
        self.indices.extend((base, base + 1, base + 2, base, base + 2, base + 3))


def add_box(prim, cx, cy, cz, sx, sy, sz, uv_scale):
    hx, hy, hz = sx / 2, sy / 2, sz / 2

    def v(x, y, z):
        return (cx + x, cy + y, cz + z)

    def uv_rect(du, dv):
        return [(0, 0), (du * uv_scale, 0), (du * uv_scale, dv * uv_scale), (0, dv * uv_scale)]

    faces = [
        ([v(-hx, -hy, hz), v(hx, -hy, hz), v(hx, hy, hz), v(-hx, hy, hz)], (0, 0, 1), uv_rect(sx, sy)),
        ([v(hx, -hy, -hz), v(-hx, -hy, -hz), v(-hx, hy, -hz), v(hx, hy, -hz)], (0, 0, -1), uv_rect(sx, sy)),
        ([v(hx, -hy, hz), v(hx, -hy, -hz), v(hx, hy, -hz), v(hx, hy, hz)], (1, 0, 0), uv_rect(sz, sy)),
        ([v(-hx, -hy, -hz), v(-hx, -hy, hz), v(-hx, hy, hz), v(-hx, hy, -hz)], (-1, 0, 0), uv_rect(sz, sy)),
        ([v(-hx, hy, hz), v(hx, hy, hz), v(hx, hy, -hz), v(-hx, hy, -hz)], (0, 1, 0), uv_rect(sx, sz)),
        ([v(-hx, -hy, -hz), v(hx, -hy, -hz), v(hx, -hy, hz), v(-hx, -hy, hz)], (0, -1, 0), uv_rect(sx, sz)),
    ]
    for corners, normal, uvs in faces:
        prim.add_quad(corners, normal, uvs)


def add_cylinder(prim, cx, cy, cz, radius, height, sides, uv_scale):
    hy = height / 2
    for i in range(sides):
        a0 = (i / sides) * math.tau
        a1 = ((i + 1) / sides) * math.tau
        x0, z0 = math.cos(a0) * radius, math.sin(a0) * radius
        x1, z1 = math.cos(a1) * radius, math.sin(a1) * radius
        n0 = (math.cos(a0), 0, math.sin(a0))
        n1 = (math.cos(a1), 0, math.sin(a1))
        # Average normal is fine for a clay tank; use the edge normal.
        normal = (math.cos((a0 + a1) / 2), 0, math.sin((a0 + a1) / 2))
        corners = [
            (cx + x0, cy - hy, cz + z0),
            (cx + x1, cy - hy, cz + z1),
            (cx + x1, cy + hy, cz + z1),
            (cx + x0, cy + hy, cz + z0),
        ]
        u0, u1 = i / sides, (i + 1) / sides
        prim.add_quad(corners, normal, [(u0, 0), (u1, 0), (u1, height * uv_scale), (u0, height * uv_scale)])
        _ = (n0, n1)
    # caps
    for top, ny in ((1, 1), (-1, -1)):
        y = cy + top * hy
        for i in range(sides):
            a0 = (i / sides) * math.tau
            a1 = ((i + 1) / sides) * math.tau
            corners_tri_as_quad = None
            c0 = (cx, y, cz)
            c1 = (cx + math.cos(a0) * radius, y, cz + math.sin(a0) * radius)
            c2 = (cx + math.cos(a1) * radius, y, cz + math.sin(a1) * radius)
            if ny < 0:
                c1, c2 = c2, c1
            base = len(prim.positions) // 3
            for corner in (c0, c1, c2):
                prim.positions.extend(corner)
                prim.normals.extend((0, ny, 0))
                prim.uvs.extend((0.5, 0.5))
            prim.indices.extend((base, base + 1, base + 2))
            _ = corners_tri_as_quad


def glass_uv(cell):
    cols, rows = 8, 4
    col = cell % cols
    row = cell // cols
    pad = 0.004
    u0 = col / cols + pad
    v0 = row / rows + pad
    u1 = (col + 1) / cols - pad
    v1 = (row + 1) / rows - pad
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


def add_glass(prim, corners, normal, cell):
    prim.add_quad(corners, normal, glass_uv(cell))


def add_window(stone, glass, origin, size, axis, outward, cell, uv_scale):
    x, y, z = origin
    w, h = size
    depth = 0.08
    border = 0.075
    glass_out = 0.02
    if axis == "z":
        zf = z + outward * depth / 2
        add_box(stone, x, y - h / 2, zf, w + border * 2, border, depth, uv_scale)
        add_box(stone, x, y + h / 2, zf, w + border * 2, border, depth, uv_scale)
        add_box(stone, x - w / 2, y, zf, border, h, depth, uv_scale)
        add_box(stone, x + w / 2, y, zf, border, h, depth, uv_scale)
        zg = z + outward * glass_out
        hw, hh = w / 2 - 0.01, h / 2 - 0.01
        if outward > 0:
            corners = [(x - hw, y - hh, zg), (x + hw, y - hh, zg), (x + hw, y + hh, zg), (x - hw, y + hh, zg)]
            normal = (0, 0, 1)
        else:
            corners = [(x + hw, y - hh, zg), (x - hw, y - hh, zg), (x - hw, y + hh, zg), (x + hw, y + hh, zg)]
            normal = (0, 0, -1)
        add_glass(glass, corners, normal, cell)
    else:
        xf = x + outward * depth / 2
        add_box(stone, xf, y - h / 2, z, depth, border, w + border * 2, uv_scale)
        add_box(stone, xf, y + h / 2, z, depth, border, w + border * 2, uv_scale)
        add_box(stone, xf, y, z - w / 2, depth, h, border, uv_scale)
        add_box(stone, xf, y, z + w / 2, depth, h, border, uv_scale)
        xg = x + outward * glass_out
        hw, hh = w / 2 - 0.01, h / 2 - 0.01
        if outward > 0:
            corners = [(xg, y - hh, z + hw), (xg, y - hh, z - hw), (xg, y + hh, z - hw), (xg, y + hh, z + hw)]
            normal = (1, 0, 0)
        else:
            corners = [(xg, y - hh, z - hw), (xg, y - hh, z + hw), (xg, y + hh, z + hw), (xg, y + hh, z - hw)]
            normal = (-1, 0, 0)
        add_glass(glass, corners, normal, cell)


def window_grid(stone, glass, face, cols, rows, cell_fn, uv_scale, margin=(0.7, 0.7), win=(1.15, 1.7)):
    axis, outward, x0, x1, y0, y1, fixed = face
    span_x = x1 - x0
    span_y = y1 - y0
    usable_x = span_x - margin[0] * 2
    usable_y = span_y - margin[1] * 2
    for row in range(rows):
        for col in range(cols):
            px = x0 + margin[0] + usable_x * (col + 0.5) / cols
            py = y0 + margin[1] + usable_y * (row + 0.5) / rows
            cell = cell_fn(col, row)
            if axis == "z":
                add_window(stone, glass, (px, py, fixed), win, "z", outward, cell, uv_scale)
            else:
                add_window(stone, glass, (fixed, py, px), (win[0], win[1]), "x", outward, cell, uv_scale)


def add_cornice(prim, y, w, d, uv_scale):
    add_box(prim, 0, y, 0, w, 0.28, d, uv_scale)
    add_box(prim, 0, y + 0.22, 0, w - 0.35, 0.18, d - 0.35, uv_scale)


def add_fire_escape(metal, x, y0, y1, z):
    floors = 5
    span = y1 - y0
    landing_w = 1.35
    for i in range(floors):
        y = y0 + span * (i + 0.15) / floors
        add_box(metal, x + 0.48, y, z, 0.9, 0.06, landing_w, 2)
        add_box(metal, x + 0.08, y + 0.45, z - landing_w / 2, 0.04, 0.9, 0.04, 2)
        add_box(metal, x + 0.9, y + 0.45, z - landing_w / 2, 0.04, 0.9, 0.04, 2)
        add_box(metal, x + 0.9, y + 0.45, z + landing_w / 2, 0.04, 0.9, 0.04, 2)
        # Ladder to the next landing, alternating sides.
        side = -1 if i % 2 else 1
        add_box(metal, x + 0.62, y + span / floors * 0.45, z + side * 0.42, 0.04, span / floors * 0.7, 0.28, 2)


def add_water_tower(metal, wood, x, y, z):
    for sx in (-0.7, 0.7):
        for sz in (-0.7, 0.7):
            add_box(metal, x + sx, y + 0.85, z + sz, 0.08, 1.7, 0.08, 2)
    add_cylinder(wood, x, y + 2.35, z, 1.05, 1.7, 12, 0.8)
    add_box(metal, x, y + 1.55, z, 2.25, 0.08, 2.25, 2)
    add_box(metal, x, y + 3.15, z, 2.3, 0.1, 2.3, 2)
    add_cylinder(metal, x, y + 3.55, z, 0.15, 0.7, 6, 1)


def build():
    prims = {name: Prim() for name in ("Podium", "Shaft", "Crown", "Glass", "Metal", "Wood", "Roof", "Plaza")}

    add_box(prims["Plaza"], 0, -0.12, 0, 28, 0.24, 22, 0.15)
    add_box(prims["Podium"], 0, 3.5, 0, 16, 7, 12, 0.55)
    add_cornice(prims["Podium"], 6.85, 16.7, 12.7, 0.55)

    add_box(prims["Shaft"], 0, 16.2, 0, 12, 18.2, 9, 0.32)
    add_cornice(prims["Shaft"], 25.15, 12.7, 9.7, 0.32)

    add_box(prims["Crown"], 0, 29.3, 0, 8, 8, 6.2, 0.28)
    add_cornice(prims["Crown"], 33.15, 8.6, 6.8, 0.28)
    add_box(prims["Crown"], 0, 35.4, 0, 4.6, 4.2, 3.6, 0.28)
    add_box(prims["Crown"], 0, 38.6, 0, 0.42, 5.4, 0.42, 0.28)
    add_box(prims["Metal"], 0, 41.15, 0, 0.7, 0.22, 0.7, 2)

    add_box(prims["Roof"], 0, 25.32, 0, 11.4, 0.12, 8.4, 0.4)
    add_box(prims["Roof"], 0, 33.32, 0, 7.4, 0.1, 5.6, 0.4)

    # Street front, +Z. Door in the middle, storefronts to either side.
    add_window(prims["Podium"], prims["Glass"], (-4.15, 2.05, 6), (3.3, 3.15), "z", 1, 24, 0.55)
    add_window(prims["Podium"], prims["Glass"], (4.15, 2.05, 6), (3.3, 3.15), "z", 1, 25, 0.55)
    add_box(prims["Metal"], 0, 1.45, 6.05, 1.7, 2.7, 0.08, 2)
    add_box(prims["Podium"], 0, 1.45, 6.02, 1.9, 2.9, 0.06, 0.55)
    add_box(prims["Metal"], 0, 3.35, 6.55, 3.4, 0.12, 1.15, 2)
    add_window(prims["Metal"], prims["Glass"], (0, 3.22, 6.7), (0.7, 0.16), "z", 1, 28, 2)

    def front_cells(col, row):
        pattern = (0, 2, 5, 1, 8, 3, 12, 4, 9, 16, 6, 10, 18, 7, 11, 13, 20, 14, 17, 21)
        return pattern[(col * 3 + row * 5) % len(pattern)]

    def side_cells(col, row):
        pattern = (4, 15, 1, 19, 6, 22, 2, 9, 27, 8, 3, 14)
        return pattern[(col + row * 2) % len(pattern)]

    def back_cells(col, row):
        return (4, 15, 23, 31, 19, 27)[(col + row) % 6]

    # Podium mezzanine.
    window_grid(
        prims["Podium"], prims["Glass"],
        ("z", 1, -8, 8, 4.55, 6.55, 6),
        6, 1, lambda c, r: (1, 8, 3, 12, 6, 2)[c], 0.55,
        margin=(0.8, 0.25), win=(1.35, 1.15),
    )
    # Shaft front and back.
    window_grid(
        prims["Shaft"], prims["Glass"],
        ("z", 1, -6, 6, 8.1, 24.4, 4.5),
        4, 5, front_cells, 0.32,
        margin=(0.85, 0.7), win=(1.45, 1.85),
    )
    window_grid(
        prims["Shaft"], prims["Glass"],
        ("z", -1, -6, 6, 8.1, 24.4, -4.5),
        4, 5, back_cells, 0.32,
        margin=(0.85, 0.7), win=(1.2, 1.6),
    )
    # Shaft sides. Right side is the one the default camera sees.
    window_grid(
        prims["Shaft"], prims["Glass"],
        ("x", 1, -4.5, 4.5, 8.1, 24.4, 6),
        3, 5, side_cells, 0.32,
        margin=(0.7, 0.7), win=(1.15, 1.7),
    )
    window_grid(
        prims["Shaft"], prims["Glass"],
        ("x", -1, -4.5, 4.5, 8.1, 24.4, -6),
        3, 5, side_cells, 0.32,
        margin=(0.7, 0.7), win=(1.15, 1.7),
    )
    # Crown.
    window_grid(
        prims["Crown"], prims["Glass"],
        ("z", 1, -4, 4, 26.3, 32.4, 3.1),
        3, 2, lambda c, r: (0, 5, 16, 2, 9, 1)[c + r * 3], 0.28,
        margin=(0.7, 0.45), win=(1.05, 1.7),
    )
    window_grid(
        prims["Crown"], prims["Glass"],
        ("x", 1, -3.1, 3.1, 26.3, 32.4, 4),
        2, 2, lambda c, r: (8, 3, 12, 6)[c + r * 2], 0.28,
        margin=(0.55, 0.45), win=(0.9, 1.55),
    )

    add_fire_escape(prims["Metal"], 6.02, 9.2, 23.2, 1.2)
    add_water_tower(prims["Metal"], prims["Wood"], 5.05, 25.45, 3.35)

    # Air conditioners sit on the sills of a few street-facing windows.
    for x, y in ((-3.86, 9.28), (-1.29, 15.25), (1.29, 18.23), (3.86, 12.26)):
        add_box(prims["Metal"], x, y, 4.78, 0.55, 0.22, 0.32, 2)

    return prims


def pad4(blob):
    return blob + b"\x00" * ((4 - len(blob) % 4) % 4)


def mesh_blob(prim):
    pos = struct.pack("<" + "f" * len(prim.positions), *prim.positions)
    nrm = struct.pack("<" + "f" * len(prim.normals), *prim.normals)
    uv = struct.pack("<" + "f" * len(prim.uvs), *prim.uvs)
    idx = struct.pack("<" + "I" * len(prim.indices), *prim.indices)
    return pad4(pos), pad4(nrm), pad4(uv), pad4(idx)


def bounds(values, stride):
    mins, maxs = [math.inf] * stride, [-math.inf] * stride
    for i in range(0, len(values), stride):
        for k in range(stride):
            mins[k] = min(mins[k], values[i + k])
            maxs[k] = max(maxs[k], values[i + k])
    return mins, maxs


def main():
    TEX.mkdir(parents=True, exist_ok=True)
    MODEL.mkdir(parents=True, exist_ok=True)

    images = {
        "Podium": (brick_texture(False), brick_texture(True)),
        "Shaft": (
            ashlar_texture(False, 2, (214, 204, 186), (186, 174, 156)),
            ashlar_texture(True, 2, (118, 112, 104), (78, 74, 68)),
        ),
        "Crown": (
            ashlar_texture(False, 5, (228, 220, 206), (196, 186, 170)),
            ashlar_texture(True, 5, (132, 126, 116), (86, 82, 76)),
        ),
        "Glass": (glass_atlas(False), glass_atlas(True)),
        "Metal": (flat_texture((92, 84, 74), seed=2), flat_texture((58, 54, 50), seed=2)),
        "Wood": (wood_texture(False), wood_texture(True)),
        "Roof": (flat_texture((62, 66, 62), seed=6), flat_texture((28, 32, 30), seed=6)),
        "Plaza": (
            flat_texture((206, 198, 186), seed=8, variation=0.04),
            flat_texture((48, 46, 44), seed=8, variation=0.04),
        ),
    }
    for name, (day, night) in images.items():
        write_png(TEX / f"{name.lower()}-day.png", *day)
        write_png(TEX / f"{name.lower()}-night.png", *night)

    prims = build()
    names = [name for name, prim in prims.items() if prim.indices]
    blob = b""
    views = []
    accessors = []
    primitives = []

    def push_view(data, target=None):
        nonlocal blob
        offset = len(blob)
        blob += data
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target:
            view["target"] = target
        views.append(view)
        return len(views) - 1

    for name in names:
        prim = prims[name]
        pos_b, nrm_b, uv_b, idx_b = mesh_blob(prim)
        pos_view = push_view(pos_b, 34962)
        nrm_view = push_view(nrm_b, 34962)
        uv_view = push_view(uv_b, 34962)
        idx_view = push_view(idx_b, 34963)
        pmin, pmax = bounds(prim.positions, 3)
        nmin, nmax = bounds(prim.normals, 3)
        umin, umax = bounds(prim.uvs, 2)
        accessors.extend([
            {"bufferView": pos_view, "componentType": 5126, "count": len(prim.positions) // 3, "type": "VEC3", "min": pmin, "max": pmax},
            {"bufferView": nrm_view, "componentType": 5126, "count": len(prim.normals) // 3, "type": "VEC3", "min": nmin, "max": nmax},
            {"bufferView": uv_view, "componentType": 5126, "count": len(prim.uvs) // 2, "type": "VEC2", "min": umin, "max": umax},
            {"bufferView": idx_view, "componentType": 5125, "count": len(prim.indices), "type": "SCALAR"},
        ])
        base = len(accessors) - 4
        primitives.append({
            "attributes": {"POSITION": base, "NORMAL": base + 1, "TEXCOORD_0": base + 2},
            "indices": base + 3,
            "material": names.index(name),
        })
        print(f"{name:8} triangles {len(prim.indices) // 3}")

    gltf_images = []
    textures = []
    materials = []
    for index, name in enumerate(names):
        gltf_images.append({"uri": f"../textures/{name.lower()}-day.png", "mimeType": "image/png"})
        textures.append({"sampler": 1 if name == "Glass" else 0, "source": index})
        material = {
            "name": name,
            "pbrMetallicRoughness": {
                "baseColorTexture": {"index": index},
                "metallicFactor": 0.55 if name == "Metal" else 0,
                "roughnessFactor": {"Glass": 0.45, "Metal": 0.42, "Wood": 0.72, "Roof": 0.9, "Plaza": 0.95}.get(name, 0.92),
            },
            "doubleSided": name == "Glass",
        }
        if name == "Glass":
            material["extensions"] = {"KHR_materials_unlit": {}}
        materials.append(material)

    gltf = {
        "asset": {"version": "2.0", "generator": "nyc-building"},
        "extensionsUsed": ["KHR_materials_unlit"],
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "LispenardTower", "mesh": 0}],
        "meshes": [{"name": "LispenardTower", "primitives": primitives}],
        "materials": materials,
        "textures": textures,
        "images": gltf_images,
        "samplers": [
            {"magFilter": LINEAR, "minFilter": LINEAR_MIPMAP, "wrapS": REPEAT, "wrapT": REPEAT},
            {"magFilter": LINEAR, "minFilter": LINEAR_MIPMAP, "wrapS": CLAMP, "wrapT": CLAMP},
        ],
        "buffers": [{"uri": "lispenard.bin", "byteLength": len(blob)}],
        "bufferViews": views,
        "accessors": accessors,
    }
    (MODEL / "lispenard.gltf").write_text(json.dumps(gltf, indent=2))
    (MODEL / "lispenard.bin").write_bytes(blob)
    print(f"buffer {len(blob)} bytes")


if __name__ == "__main__":
    main()
