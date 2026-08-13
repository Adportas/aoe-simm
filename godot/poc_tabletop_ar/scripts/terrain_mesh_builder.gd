class_name TerrainMeshBuilder
extends RefCounted

## Un vértice cada 2,08 m: tres texels del heightmap horneado. Conserva los
## espolones y barrancos sin enviar el millón de triángulos del campo fuente.
const WIDTH_SEGMENTS := 192
const LENGTH_SEGMENTS := 346


static func build() -> ArrayMesh:
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var tangents := PackedFloat32Array()
	var uvs := PackedVector2Array()
	var uv2s := PackedVector2Array()
	var colors := PackedColorArray()
	var indices := PackedInt32Array()

	for z_index in range(LENGTH_SEGMENTS + 1):
		var v := float(z_index) / float(LENGTH_SEGMENTS)
		var z := lerpf(-TerrainProfile.HALF_LENGTH_M, TerrainProfile.HALF_LENGTH_M, v)
		for x_index in range(WIDTH_SEGMENTS + 1):
			var u := float(x_index) / float(WIDTH_SEGMENTS)
			var x := lerpf(-TerrainProfile.HALF_WIDTH_M, TerrainProfile.HALF_WIDTH_M, u)
			var point_xz := Vector2(x, z)
			var height := TerrainProfile.height_at(point_xz)
			var normal := TerrainProfile.normal_at(point_xz)
			var tangent := Vector3.RIGHT.slide(normal).normalized()
			vertices.append(Vector3(x, height, z))
			normals.append(normal)
			tangents.append_array(PackedFloat32Array([
				tangent.x, tangent.y, tangent.z, -1.0,
			]))
			uvs.append(Vector2(u, v))
			uv2s.append(Vector2(TerrainProfile.coast_distance_at(point_xz), 0.0))
			colors.append(_color_for_height(height))

	var row_size := WIDTH_SEGMENTS + 1
	for z_index in range(LENGTH_SEGMENTS):
		for x_index in range(WIDTH_SEGMENTS):
			var top_left := z_index * row_size + x_index
			var top_right := top_left + 1
			var bottom_left := top_left + row_size
			var bottom_right := bottom_left + 1
			# Godot usa sentido horario para el frente. Este orden deja la cara
			# visible apuntando hacia arriba, donde están la cámara y las unidades.
			indices.append_array(PackedInt32Array([
				top_left, top_right, bottom_left,
				top_right, bottom_right, bottom_left,
			]))

	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TANGENT] = tangents
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_TEX_UV2] = uv2s
	arrays[Mesh.ARRAY_COLOR] = colors
	arrays[Mesh.ARRAY_INDEX] = indices

	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh


static func _color_for_height(height_m: float) -> Color:
	var low := Color("687355")
	var high := Color("9a8c65")
	return low.lerp(high, clampf((height_m - 5.0) / 60.0, 0.0, 1.0))
