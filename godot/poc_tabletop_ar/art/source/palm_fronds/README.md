# Atlas de frondas de palmera

`frond_atlas_chroma_v1.png` es la generación original sobre fondo cromático.
`frond_atlas_alpha_raw_v1.png` es la extracción RGBA conservada como fuente.
Godot consume únicamente los mapas 2K producidos en
`assets/environment/island_biome/textures/palms/`.

La imagen fue creada con el generador integrado de OpenAI el 12 de agosto de
2026 y después se eliminó el fondo con `remove_chroma_key.py` del skill
`imagegen` (`--auto-key border --soft-matte --despill`). Prompt de producción:

> Use case: stylized-concept. Asset type: production game texture atlas for
> palm-frond cards. Create exactly eight isolated photorealistic tropical palm
> fronds on a perfectly uniform solid #ff00ff chroma-key background: two broad
> fan-palm fronds, three date-palm fronds, three long coconut-palm fronds.
> Arrange them in a strict 2-column by 4-row grid, one complete non-overlapping
> frond centered per equal cell. Orthographic top-down botanical cutouts. Every
> stem base points down and every tip points up. Natural green variation; one
> yellow-green and one subtly brown-tipped specimen. Crisp thin leaflets,
> visible rachis, minor asymmetry and small tears, even neutral illumination,
> generous padding. The background must be pure flat #ff00ff everywhere with
> no shadow, gradient, texture, floor, reflection, or halo. No magenta in the
> plants. No trunks, coconuts, extra leaves, labels, grid lines, text,
> watermark, overlap, cropping, blur, depth of field, or scenic background.

Regeneración determinista desde la fuente RGBA:

```sh
./tools/build_palm_frond_atlas.sh
```

El resultado conserva el orden de celdas 2 x 4, dilata el color debajo del
alfa para evitar bordes oscuros en mipmaps y deriva normal y máscara de hoja.
