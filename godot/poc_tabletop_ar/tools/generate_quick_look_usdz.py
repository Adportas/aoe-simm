#!/usr/bin/env python3
"""Build the lightweight, table-scale USDZ used by Apple AR Quick Look.

The generator deliberately uses only Python's standard library plus Apple's
``usdzip``/``usdchecker`` command-line tools.  It turns the same baked terrain
fields used by Godot into a 40 x 72 cm miniature with simple vegetation and
rocks, so the web preview can offer real AR surface anchoring on iOS without
shipping the much larger runtime scene to Quick Look.
"""

from __future__ import annotations

import argparse
import array
import binascii
import math
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


SOURCE_WIDTH = 576
SOURCE_HEIGHT = 1024
GRID_WIDTH = 97
GRID_HEIGHT = 173
MODEL_WIDTH_M = 0.40
MODEL_LENGTH_M = 0.72
MODEL_SCALE = 0.001
SEA_LEVEL_M = 0.75
SURFACE_Y_M = 0.0082

LAYER_COLORS = (
	(89, 103, 82),   # wet sand
	(177, 166, 117), # dry sand
	(93, 82, 56),    # soil
	(72, 113, 48),   # green grass
	(126, 118, 65),  # dry grass
	(111, 112, 103), # rock
	(82, 76, 44),    # litter
	(139, 136, 119), # pebbles
)


@dataclass
class DecodedPng:
	width: int
	height: int
	channels: int
	pixels: bytes

	def sample(self, x: int, y: int) -> tuple[int, ...]:
		x = min(max(x, 0), self.width - 1)
		y = min(max(y, 0), self.height - 1)
		start = (y * self.width + x) * self.channels
		return tuple(self.pixels[start : start + self.channels])


@dataclass
class MeshData:
	points: list[tuple[float, float, float]] = field(default_factory=list)
	faces: list[list[int]] = field(default_factory=list)

	def add_point(self, point: tuple[float, float, float]) -> int:
		self.points.append(point)
		return len(self.points) - 1

	def add_face(self, indices: Sequence[int]) -> None:
		self.faces.append(list(indices))

	def extent(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
		minimum = tuple(min(point[axis] for point in self.points) for axis in range(3))
		maximum = tuple(max(point[axis] for point in self.points) for axis in range(3))
		return minimum, maximum


def _paeth(a: int, b: int, c: int) -> int:
	p = a + b - c
	pa = abs(p - a)
	pb = abs(p - b)
	pc = abs(p - c)
	if pa <= pb and pa <= pc:
		return a
	if pb <= pc:
		return b
	return c


def read_png(path: Path) -> DecodedPng:
	data = path.read_bytes()
	if data[:8] != b"\x89PNG\r\n\x1a\n":
		raise ValueError(f"{path} is not a PNG file")
	position = 8
	idat = bytearray()
	width = height = bit_depth = color_type = interlace = -1
	while position < len(data):
		length = struct.unpack(">I", data[position : position + 4])[0]
		chunk_type = data[position + 4 : position + 8]
		payload = data[position + 8 : position + 8 + length]
		position += length + 12
		if chunk_type == b"IHDR":
			width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
				">IIBBBBB", payload
			)
			if compression != 0 or filtering != 0:
				raise ValueError(f"unsupported PNG compression/filter method in {path}")
		elif chunk_type == b"IDAT":
			idat.extend(payload)
		elif chunk_type == b"IEND":
			break
	if bit_depth != 8 or interlace != 0 or color_type not in (0, 2, 6):
		raise ValueError(
			f"{path} must be a non-interlaced 8-bit grayscale, RGB, or RGBA PNG"
		)
	channels = {0: 1, 2: 3, 6: 4}[color_type]
	stride = width * channels
	raw = zlib.decompress(bytes(idat))
	expected = height * (stride + 1)
	if len(raw) != expected:
		raise ValueError(f"unexpected decoded PNG size for {path}: {len(raw)} != {expected}")
	decoded = bytearray(height * stride)
	previous = bytearray(stride)
	offset = 0
	for row_index in range(height):
		filter_type = raw[offset]
		offset += 1
		scanline = bytearray(raw[offset : offset + stride])
		offset += stride
		for index in range(stride):
			left = scanline[index - channels] if index >= channels else 0
			above = previous[index]
			upper_left = previous[index - channels] if index >= channels else 0
			if filter_type == 1:
				scanline[index] = (scanline[index] + left) & 0xFF
			elif filter_type == 2:
				scanline[index] = (scanline[index] + above) & 0xFF
			elif filter_type == 3:
				scanline[index] = (scanline[index] + ((left + above) >> 1)) & 0xFF
			elif filter_type == 4:
				scanline[index] = (
					scanline[index] + _paeth(left, above, upper_left)
				) & 0xFF
			elif filter_type != 0:
				raise ValueError(f"unsupported PNG filter {filter_type} in {path}")
		start = row_index * stride
		decoded[start : start + stride] = scanline
		previous = scanline
	return DecodedPng(width, height, channels, bytes(decoded))


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
	return (
		struct.pack(">I", len(payload))
		+ kind
		+ payload
		+ struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
	)


def write_rgb_png(path: Path, width: int, height: int, pixels: bytes) -> None:
	if len(pixels) != width * height * 3:
		raise ValueError("RGB pixel buffer has the wrong size")
	rows = bytearray()
	stride = width * 3
	for row in range(height):
		rows.append(0)
		start = row * stride
		rows.extend(pixels[start : start + stride])
	png = bytearray(b"\x89PNG\r\n\x1a\n")
	png.extend(_png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))
	png.extend(_png_chunk(b"IDAT", zlib.compress(bytes(rows), level=9)))
	png.extend(_png_chunk(b"IEND", b""))
	path.write_bytes(bytes(png))


def read_float_field(path: Path) -> array.array:
	values = array.array("f")
	with path.open("rb") as source:
		values.fromfile(source, SOURCE_WIDTH * SOURCE_HEIGHT)
	if sys.byteorder != "little":
		values.byteswap()
	if len(values) != SOURCE_WIDTH * SOURCE_HEIGHT:
		raise ValueError(f"unexpected float field size in {path}")
	return values


def field_value(values: Sequence[float], x: int, y: int) -> float:
	x = min(max(x, 0), SOURCE_WIDTH - 1)
	y = min(max(y, 0), SOURCE_HEIGHT - 1)
	return float(values[y * SOURCE_WIDTH + x])


def terrain_normal(height: Sequence[float], x: int, y: int) -> tuple[float, float, float]:
	dx_m = MODEL_WIDTH_M / (SOURCE_WIDTH - 1) / MODEL_SCALE
	dz_m = MODEL_LENGTH_M / (SOURCE_HEIGHT - 1) / MODEL_SCALE
	dh_dx = (
		field_value(height, x + 1, y) - field_value(height, x - 1, y)
	) / (2.0 * dx_m)
	dh_dz = (
		field_value(height, x, y + 1) - field_value(height, x, y - 1)
	) / (2.0 * dz_m)
	nx, ny, nz = -dh_dx, 1.0, -dh_dz
	length = math.sqrt(nx * nx + ny * ny + nz * nz)
	return nx / length, ny / length, nz / length


def build_albedo(
	height: Sequence[float],
	sdf: Sequence[float],
	splat_a: DecodedPng,
	splat_b: DecodedPng,
	ao: DecodedPng,
) -> tuple[int, int, bytes]:
	width = SOURCE_WIDTH // 2
	height_px = SOURCE_HEIGHT // 2
	pixels = bytearray(width * height_px * 3)
	sun = (-0.42, 0.82, -0.39)
	sun_length = math.sqrt(sum(value * value for value in sun))
	sun = tuple(value / sun_length for value in sun)
	for output_y in range(height_px):
		source_y = min(output_y * 2 + 1, SOURCE_HEIGHT - 1)
		for output_x in range(width):
			source_x = min(output_x * 2 + 1, SOURCE_WIDTH - 1)
			distance = field_value(sdf, source_x, source_y)
			if distance < 0.0:
				depth = min(1.0, -distance / 80.0)
				wave = 0.5 + 0.5 * math.sin(source_x * 0.14 + source_y * 0.055)
				color = (
					int(31 - depth * 12 + wave * 3),
					int(105 - depth * 34 + wave * 5),
					int(120 - depth * 27 + wave * 6),
				)
			else:
				weights = splat_a.sample(source_x, source_y) + splat_b.sample(source_x, source_y)
				weight_total = max(sum(weights), 1)
				base = [
					sum(LAYER_COLORS[index][channel] * weights[index] for index in range(8))
					/ weight_total
					for channel in range(3)
				]
				normal = terrain_normal(height, source_x, source_y)
				light = max(0.0, sum(normal[index] * sun[index] for index in range(3)))
				ao_value = ao.sample(source_x, source_y)[0] / 255.0
				shade = (0.50 + 0.53 * light) * (0.72 + 0.28 * ao_value)
				if distance < 4.0:
					shore = max(0.0, min(1.0, distance / 4.0))
					base = [186 * (1.0 - shore) + value * shore for value in base]
				color = tuple(max(0, min(255, int(value * shade))) for value in base)
			start = (output_y * width + output_x) * 3
			pixels[start : start + 3] = bytes(color)
	return width, height_px, bytes(pixels)


def build_thumbnail(
	texture_width: int,
	texture_height: int,
	texture_pixels: bytes,
	size: int = 192,
) -> bytes:
	canvas = bytearray(size * size * 3)
	for y in range(size):
		for x in range(size):
			gradient = int(19 + 18 * y / max(size - 1, 1))
			start = (y * size + x) * 3
			canvas[start : start + 3] = bytes((8, gradient, gradient + 13))
	margin = 15
	fit_height = size - margin * 2
	fit_width = max(1, round(fit_height * texture_width / texture_height))
	left = (size - fit_width) // 2
	for y in range(fit_height):
		source_y = min(texture_height - 1, int(y * texture_height / fit_height))
		for x in range(fit_width):
			source_x = min(texture_width - 1, int(x * texture_width / fit_width))
			source = (source_y * texture_width + source_x) * 3
			target = ((margin + y) * size + left + x) * 3
			canvas[target : target + 3] = texture_pixels[source : source + 3]
	return bytes(canvas)


def build_terrain(height: Sequence[float]) -> tuple[MeshData, list[tuple[float, float, float]], list[tuple[float, float]]]:
	mesh = MeshData()
	normals: list[tuple[float, float, float]] = []
	uvs: list[tuple[float, float]] = []
	for row in range(GRID_HEIGHT):
		v = row / (GRID_HEIGHT - 1)
		source_y = round(v * (SOURCE_HEIGHT - 1))
		z = (v - 0.5) * MODEL_LENGTH_M
		for column in range(GRID_WIDTH):
			u = column / (GRID_WIDTH - 1)
			source_x = round(u * (SOURCE_WIDTH - 1))
			x = (u - 0.5) * MODEL_WIDTH_M
			y = SURFACE_Y_M + max(
				0.0,
				field_value(height, source_x, source_y) - SEA_LEVEL_M,
			) * MODEL_SCALE
			mesh.add_point((x, y, z))
			normals.append(terrain_normal(height, source_x, source_y))
			uvs.append((u, 1.0 - v))
	for row in range(GRID_HEIGHT - 1):
		for column in range(GRID_WIDTH - 1):
			a = row * GRID_WIDTH + column
			mesh.add_face((a, a + GRID_WIDTH, a + GRID_WIDTH + 1, a + 1))
	return mesh, normals, uvs


def source_to_model(source_x: int, source_y: int, height: Sequence[float]) -> tuple[float, float, float]:
	return (
		(source_x / (SOURCE_WIDTH - 1) - 0.5) * MODEL_WIDTH_M,
		SURFACE_Y_M + max(
			0.0,
			field_value(height, source_x, source_y) - SEA_LEVEL_M,
		) * MODEL_SCALE,
		(source_y / (SOURCE_HEIGHT - 1) - 0.5) * MODEL_LENGTH_M,
	)


def choose_locations(
	rng: random.Random,
	height: Sequence[float],
	sdf: Sequence[float],
	density: DecodedPng,
	channel: int,
	count: int,
	minimum_coast_distance: float,
	minimum_pixel_spacing: float,
) -> list[tuple[int, int]]:
	locations: list[tuple[int, int]] = []
	for _attempt in range(120000):
		if len(locations) >= count:
			break
		x = rng.randrange(20, SOURCE_WIDTH - 20)
		y = rng.randrange(20, SOURCE_HEIGHT - 20)
		if field_value(sdf, x, y) < minimum_coast_distance:
			continue
		if rng.random() > density.sample(x, y)[channel] / 255.0:
			continue
		normal = terrain_normal(height, x, y)
		if normal[1] < 0.60:
			continue
		if any(
			math.hypot(x - previous_x, y - previous_y) < minimum_pixel_spacing
			for previous_x, previous_y in locations
		):
			continue
		locations.append((x, y))
	if len(locations) != count:
		raise RuntimeError(f"could only place {len(locations)} of {count} requested props")
	return locations


def add_cylinder(
	mesh: MeshData,
	center: tuple[float, float, float],
	radius: float,
	height: float,
	segments: int = 7,
) -> None:
	x, y, z = center
	bottom: list[int] = []
	top: list[int] = []
	for segment in range(segments):
		angle = math.tau * segment / segments
		dx = math.cos(angle) * radius
		dz = math.sin(angle) * radius
		bottom.append(mesh.add_point((x + dx, y, z + dz)))
		top.append(mesh.add_point((x + dx, y + height, z + dz)))
	for segment in range(segments):
		next_segment = (segment + 1) % segments
		mesh.add_face((bottom[segment], bottom[next_segment], top[next_segment], top[segment]))
	mesh.add_face(tuple(reversed(bottom)))
	mesh.add_face(top)


def add_fronds(
	mesh: MeshData,
	crown: tuple[float, float, float],
	length: float,
	rng: random.Random,
) -> None:
	x, y, z = crown
	for frond in range(7):
		angle = math.tau * frond / 7.0 + rng.uniform(-0.16, 0.16)
		direction = (math.cos(angle), math.sin(angle))
		perpendicular = (-direction[1], direction[0])
		width = length * rng.uniform(0.13, 0.19)
		tip_length = length * rng.uniform(0.82, 1.12)
		inner = mesh.add_point((x, y + 0.0005, z))
		left = mesh.add_point((
			x + direction[0] * tip_length * 0.42 + perpendicular[0] * width,
			y,
			z + direction[1] * tip_length * 0.42 + perpendicular[1] * width,
		))
		tip = mesh.add_point((
			x + direction[0] * tip_length,
			y - tip_length * 0.22,
			z + direction[1] * tip_length,
		))
		right = mesh.add_point((
			x + direction[0] * tip_length * 0.42 - perpendicular[0] * width,
			y,
			z + direction[1] * tip_length * 0.42 - perpendicular[1] * width,
		))
		mesh.add_face((inner, right, tip, left))


def add_rock(
	mesh: MeshData,
	center: tuple[float, float, float],
	scale: float,
	rng: random.Random,
) -> None:
	x, y, z = center
	sx = scale * rng.uniform(0.7, 1.35)
	sy = scale * rng.uniform(0.55, 1.0)
	sz = scale * rng.uniform(0.7, 1.4)
	points = (
		(x, y + sy, z),
		(x, y, z),
		(x + sx, y + sy * 0.28, z),
		(x - sx, y + sy * 0.28, z),
		(x, y + sy * 0.25, z + sz),
		(x, y + sy * 0.25, z - sz),
	)
	indices = [mesh.add_point(point) for point in points]
	for face in (
		(0, 2, 4), (0, 4, 3), (0, 3, 5), (0, 5, 2),
		(1, 4, 2), (1, 3, 4), (1, 5, 3), (1, 2, 5),
	):
		mesh.add_face(tuple(indices[index] for index in face))


def build_props(
	height: Sequence[float],
	sdf: Sequence[float],
	density: DecodedPng,
) -> tuple[MeshData, MeshData, MeshData]:
	rng = random.Random(20260812)
	trunks = MeshData()
	fronds = MeshData()
	rocks = MeshData()
	palms = choose_locations(rng, height, sdf, density, 0, 34, 8.0, 27.0)
	for source_x, source_y in palms:
		x, ground_y, z = source_to_model(source_x, source_y, height)
		trunk_height = rng.uniform(0.019, 0.032)
		add_cylinder(
			trunks,
			(x, ground_y + 0.0002, z),
			rng.uniform(0.0008, 0.00125),
			trunk_height,
		)
		add_fronds(
			fronds,
			(x, ground_y + trunk_height + 0.0002, z),
			rng.uniform(0.010, 0.016),
			rng,
		)
	rock_locations = choose_locations(rng, height, sdf, density, 3, 42, 3.0, 18.0)
	for source_x, source_y in rock_locations:
		center = source_to_model(source_x, source_y, height)
		add_rock(rocks, center, rng.uniform(0.0022, 0.0055), rng)
	return trunks, fronds, rocks


def _format_float(value: float) -> str:
	if abs(value) < 0.0000005:
		value = 0.0
	return f"{value:.6f}"


def _tuple_text(values: Iterable[float]) -> str:
	return "(" + ", ".join(_format_float(value) for value in values) + ")"


def write_sequence(
	output,
	indent: str,
	declaration: str,
	values: Sequence[str],
	items_per_line: int,
	metadata: str | None = None,
) -> None:
	output.write(f"{indent}{declaration} = [\n")
	for index in range(0, len(values), items_per_line):
		line = ", ".join(values[index : index + items_per_line])
		if index + items_per_line < len(values):
			line += ","
		output.write(f"{indent}\t{line}\n")
	output.write(f"{indent}]" + (f" ({metadata})" if metadata else "") + "\n")


def write_mesh(
	output,
	name: str,
	mesh: MeshData,
	material_path: str,
	normals: Sequence[tuple[float, float, float]] | None = None,
	uvs: Sequence[tuple[float, float]] | None = None,
	double_sided: bool = False,
) -> None:
	minimum, maximum = mesh.extent()
	output.write(f'''\n\tdef Mesh "{name}" (\n\t\tprepend apiSchemas = ["MaterialBindingAPI"]\n\t)\n\t{{\n''')
	write_sequence(output, "\t\t", "float3[] extent", [_tuple_text(minimum), _tuple_text(maximum)], 2)
	write_sequence(output, "\t\t", "int[] faceVertexCounts", [str(len(face)) for face in mesh.faces], 18)
	write_sequence(
		output,
		"\t\t",
		"int[] faceVertexIndices",
		[str(index) for face in mesh.faces for index in face],
		18,
	)
	if normals is not None:
		write_sequence(
			output,
			"\t\t",
			"normal3f[] normals",
			[_tuple_text(normal) for normal in normals],
			4,
			'interpolation = "vertex"',
		)
	write_sequence(output, "\t\t", "point3f[] points", [_tuple_text(point) for point in mesh.points], 4)
	if uvs is not None:
		write_sequence(
			output,
			"\t\t",
			"texCoord2f[] primvars:st",
			[_tuple_text(uv) for uv in uvs],
			6,
			'interpolation = "vertex"',
		)
	output.write(f'''\t\trel material:binding = <{material_path}>\n\t\tuniform token subdivisionScheme = "none"\n''')
	if double_sided:
		output.write("\t\tbool doubleSided = true\n")
	output.write("\t}\n")


def write_material(output, name: str, color: tuple[float, float, float], roughness: float) -> None:
	path = f"/Island/Materials/{name}"
	output.write(f'''\n\t\tdef Material "{name}"\n\t\t{{\n\t\t\ttoken outputs:surface.connect = <{path}/PBR.outputs:surface>\n\n\t\t\tdef Shader "PBR"\n\t\t\t{{\n\t\t\t\tuniform token info:id = "UsdPreviewSurface"\n\t\t\t\tcolor3f inputs:diffuseColor = {_tuple_text(color)}\n\t\t\t\tfloat inputs:metallic = 0\n\t\t\t\tfloat inputs:roughness = {_format_float(roughness)}\n\t\t\t\ttoken outputs:surface\n\t\t\t}}\n\t\t}}\n''')


def write_usda(
	path: Path,
	terrain: MeshData,
	normals: Sequence[tuple[float, float, float]],
	uvs: Sequence[tuple[float, float]],
	trunks: MeshData,
	fronds: MeshData,
	rocks: MeshData,
) -> None:
	with path.open("w", encoding="utf-8", newline="\n") as output:
		output.write('''#usda 1.0\n(\n\tdefaultPrim = "Island"\n\tmetersPerUnit = 1\n\tupAxis = "Y"\n)\n\ndef Xform "Island" (\n\tkind = "component"\n)\n{\n''')
		write_mesh(
			output,
			"Terrain",
			terrain,
			"/Island/Materials/TerrainMaterial",
			normals=normals,
			uvs=uvs,
		)
		output.write('''\n\tdef Xform "OceanBase"\n\t{\n\t\tdouble3 xformOp:scale = (0.400000, 0.008000, 0.720000)\n\t\tdouble3 xformOp:translate = (0, 0.004000, 0)\n\t\tuniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]\n\n\t\tdef Cube "Water" (\n\t\t\tprepend apiSchemas = ["MaterialBindingAPI"]\n\t\t)\n\t\t{\n\t\t\tdouble size = 1\n\t\t\trel material:binding = </Island/Materials/WaterMaterial>\n\t\t}\n\t}\n''')
		write_mesh(output, "PalmTrunks", trunks, "/Island/Materials/TrunkMaterial", double_sided=True)
		write_mesh(output, "PalmFronds", fronds, "/Island/Materials/FrondMaterial", double_sided=True)
		write_mesh(output, "Rocks", rocks, "/Island/Materials/RockMaterial", double_sided=True)
		output.write('''\n\tdef Scope "Materials"\n\t{\n\t\tdef Material "TerrainMaterial"\n\t\t{\n\t\t\ttoken outputs:surface.connect = </Island/Materials/TerrainMaterial/PBR.outputs:surface>\n\n\t\t\tdef Shader "PBR"\n\t\t\t{\n\t\t\t\tuniform token info:id = "UsdPreviewSurface"\n\t\t\t\tcolor3f inputs:diffuseColor.connect = </Island/Materials/TerrainMaterial/Texture.outputs:rgb>\n\t\t\t\tfloat inputs:metallic = 0\n\t\t\t\tfloat inputs:roughness = 0.920000\n\t\t\t\ttoken outputs:surface\n\t\t\t}\n\n\t\t\tdef Shader "Texture"\n\t\t\t{\n\t\t\t\tuniform token info:id = "UsdUVTexture"\n\t\t\t\tasset inputs:file = @island_albedo.png@\n\t\t\t\tfloat2 inputs:st.connect = </Island/Materials/TerrainMaterial/Primvar.outputs:result>\n\t\t\t\ttoken inputs:sourceColorSpace = "sRGB"\n\t\t\t\tfloat3 outputs:rgb\n\t\t\t}\n\n\t\t\tdef Shader "Primvar"\n\t\t\t{\n\t\t\t\tuniform token info:id = "UsdPrimvarReader_float2"\n\t\t\t\ttoken inputs:varname = "st"\n\t\t\t\tfloat2 outputs:result\n\t\t\t}\n\t\t}\n''')
		write_material(output, "WaterMaterial", (0.055, 0.310, 0.390), 0.22)
		write_material(output, "TrunkMaterial", (0.250, 0.130, 0.055), 0.90)
		write_material(output, "FrondMaterial", (0.070, 0.290, 0.085), 0.78)
		write_material(output, "RockMaterial", (0.310, 0.320, 0.300), 0.96)
		output.write("\t}\n}\n")


def build(project_path: Path, output_usdz: Path, output_preview: Path) -> None:
	world = project_path / "assets/environment/island_biome/world"
	height = read_float_field(world / "island_height_f32.bin")
	sdf = read_float_field(world / "island_sdf_f32.bin")
	splat_a = read_png(world / "island_splat_a.png")
	splat_b = read_png(world / "island_splat_b.png")
	density = read_png(world / "island_biome_density.png")
	ao = read_png(world / "island_terrain_ao.png")
	for image in (splat_a, splat_b, density, ao):
		if (image.width, image.height) != (SOURCE_WIDTH, SOURCE_HEIGHT):
			raise ValueError("all baked terrain fields must have the expected resolution")

	texture_width, texture_height, texture_pixels = build_albedo(
		height, sdf, splat_a, splat_b, ao
	)
	terrain, normals, uvs = build_terrain(height)
	trunks, fronds, rocks = build_props(height, sdf, density)

	output_usdz.parent.mkdir(parents=True, exist_ok=True)
	output_preview.parent.mkdir(parents=True, exist_ok=True)
	write_rgb_png(
		output_preview,
		192,
		192,
		build_thumbnail(texture_width, texture_height, texture_pixels),
	)
	usdzip = shutil.which("usdzip")
	if usdzip is None:
		raise RuntimeError("usdzip is required (install Apple's USD tools or Xcode tools)")
	with tempfile.TemporaryDirectory(prefix="aoe-quick-look-") as temporary_directory:
		temporary = Path(temporary_directory)
		usda = temporary / "island.usda"
		albedo = temporary / "island_albedo.png"
		package = temporary / "isla-aoe.usdz"
		write_rgb_png(albedo, texture_width, texture_height, texture_pixels)
		write_usda(usda, terrain, normals, uvs, trunks, fronds, rocks)
		for packaged_file in (usda, albedo):
			os.utime(packaged_file, (1_704_067_200, 1_704_067_200))
		subprocess.run(
			[usdzip, package.name, usda.name, albedo.name],
			cwd=temporary,
			check=True,
		)
		shutil.copyfile(package, output_usdz)

	checker = shutil.which("usdchecker")
	if checker is not None:
		subprocess.run([checker, "--arkit", str(output_usdz)], check=True)
	print(
		f"Quick Look asset: {output_usdz} "
		f"({output_usdz.stat().st_size / (1024 * 1024):.2f} MiB, "
		f"{len(terrain.points):,} terrain vertices, "
		f"{len(trunks.faces) + len(fronds.faces) + len(rocks.faces):,} prop faces)"
	)


def parse_args() -> argparse.Namespace:
	project_path = Path(__file__).resolve().parents[1]
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--project", type=Path, default=project_path)
	parser.add_argument(
		"--output",
		type=Path,
		default=project_path / "web/quicklook/isla-aoe.usdz",
	)
	parser.add_argument(
		"--preview",
		type=Path,
		default=project_path / "web/quicklook/isla-aoe-preview.png",
	)
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	build(args.project.resolve(), args.output.resolve(), args.preview.resolve())
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
