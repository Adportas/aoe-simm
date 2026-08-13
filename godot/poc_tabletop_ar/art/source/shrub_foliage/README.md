# Atlas de follaje de arbustos

`shrub_atlas_chroma_v1.png` es la generación corregida sobre fondo cromático.
`shrub_atlas_alpha_raw_v1.png` es la extracción RGBA conservada como fuente.
Godot consume únicamente los mapas 2K producidos en
`assets/environment/island_biome/textures/shrubs/`.

La imagen fue creada con el generador integrado de OpenAI el 12 de agosto de
2026. La primera generación acertó las ocho ramas pero produjo un fondo verde;
una edición posterior conservó las plantas y reemplazó únicamente ese fondo
por `#ff00ff`. Después se eliminó con `remove_chroma_key.py` del skill
`imagegen` (`--auto-key border --soft-matte --despill`). Prompt final:

> Use case: background-extraction. Asset type: production game texture atlas
> edit. Replace only the entire background behind and between the eight
> existing tropical shrub sprays with one perfectly uniform solid #ff00ff
> chroma-key color. Preserve exactly the same eight plant subjects, their
> 2-column by 4-row positions, leaf shapes, branch shapes, colors, scale,
> lighting, internal gaps, sharpness, and generous separation. Do not redesign,
> add, remove, move, crop, enlarge, or overlap any plant. Every non-plant pixel
> must be exact flat #ff00ff with no green, brown, shadow, glow, halo, gradient,
> texture, floor, reflection, vignette, or lighting variation. No magenta
> inside the plants. No text, labels, grid lines, borders, watermark, blur,
> extra leaves, extra branches, flowers, fruit, pots, roots, insects, scenic
> background, cast shadows, or contact shadows.

Regeneración determinista desde la fuente RGBA:

```sh
./tools/build_shrub_atlas.sh
```

El resultado conserva el orden 2 x 4, dilata RGB debajo del alfa para mipmaps
y deriva normal tangente y máscara R=rugosidad/G=translucidez.
