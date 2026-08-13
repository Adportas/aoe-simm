# Tabletop AR POC

Prueba técnica para colocar un diorama interactivo sobre una mesa de
**1,00 × 1,80 m**, usando Godot 4 y ARKit en iPhone/iPad con LiDAR.

## Escalas elegidas

- Terreno: **1:400**. La mesa representa **720 × 400 m virtuales**
  (largo × ancho).
- Personajes: **1:180**. Un humano de 1,80 m se ve de **10 mm**.
- Simulación: `1 unidad Godot = 1 metro virtual`.

La navegación y la altura del terreno siempre permanecen en metros virtuales.
El `DioramaRoot` reduce todo a `1/400`; el modelo visual del personaje recibe
adicionalmente `400/180 = 2,222…`. El pivote de sus pies no cambia, por lo que
puede seguir el mapa de alturas sin mezclar escalas físicas y lógicas.

## Lo que ya funciona

- Simulador de una mesa de 1,00 × 1,80 m.
- Isla de 720 × 400 m horneada a 0,69 m/texel: SDF euclídeo, heightmap
  erosionado, batimetría, cabos rocosos, bahías y una cordillera de cuatro
  cumbres que alcanza 60 m.
- Ocho capas de terreno gobernadas por splats: arena mojada y seca, suelo,
  pasto verde y seco, roca, hojarasca y guijarros. Costa, agua, navegación y
  materiales consumen el mismo SDF/heightmap. Normal topográfica y AO de
  horizonte a resolución completa conservan las cárcavas sin aumentar la
  malla. Tres `Texture2DArray` 1K aportan albedo, normal y
  `R=altura/G=roughness/B=AO`; el canal de altura resuelve transiciones sin
  fundido jabonoso y la arena se oscurece/pule junto al nivel del mar.
- Bioma tropical optimizado mediante `MultiMesh`: 25.060 instancias en doce
  estratos visuales (tres palmeras, dos árboles de copa, tres rocas, dos
  arbustos y dos pastos). La colocación usa campos de densidad y hash espacial,
  con variaciones deterministas de edad, proporción, color e inclinación, más
  viento GPU por instancia. Las rocas usan `StandardMaterial3D` PBR triplanar
  y varían yaw, pitch y roll; el follaje usa una LUT verde→amarillo→pardo,
  doblado cúbico y ráfagas espaciales. Las tres palmeras emplean copas de
  28/32/34 frond cards con atlas RGBA 2K de ocho variantes, normal tangente,
  máscara de rugosidad/translucidez, alpha-clip y `BACKLIGHT` de doble cara.
  Los arbustos densos/abiertos usan seis cards curvas de proporción corregida
  (cinco laterales y una tapa cenital) y otro atlas 2K de ocho ramas; los dos
  árboles de copa reutilizan esas mallas a escala arbórea.
- Océano extendido sin borde de diorama, oleaje Gerstner, refracción,
  absorción por profundidad, cáusticas y espuma gobernada por el espesor real
  de la columna de agua.
- Cielo procedural, luz solar suave, tonemapping ACES y perspectiva
  atmosférica; la mesa física queda oculta durante la presentación.
- Selección de destino mediante clic/toque.
- Guardia fronterizo estilizado de nivel héroe generado en Blender: geometría
  detallada, materiales PBR con albedo y normales, rig de 18 huesos y
  animaciones `Idle`, `Walk` y `Attack`.
- Aldeano fotorealista generado con TRELLIS 2 desde las referencias alpha:
  LOD0 de 72.000 triángulos, PBR 2K, rig de 18 huesos, cápsula de selección y
  animaciones `Idle`, `Walk` y `Attack`. `Walk` usa ocho fases
  contacto/descenso/paso/elevación, rodillas articuladas, contrapeso de brazos,
  transferencia de peso y estabilización sutil de torso y cabeza. Es el
  personaje activo por defecto.
- Trayecto del aldeano desde el cabo izquierdo de la isla hasta el primer
  afloramiento rocoso del eje central, donde se detiene a unos seis metros.
- Corrección explícita Blender/glTF `+Z` → Godot `-Z`: el rostro y el cuerpo
  miran en la misma dirección en que se desplaza la unidad.
- Plano de escena fijo para ver el viaje completo sobre un terreno inmóvil,
  con un refuerzo visual del aldeano para que su marcha se lea con nitidez en
  1080p y composición de izquierda a derecha; las vistas general, cenital y
  AR conservan la escala física 1:180.
- Muestreo continuo del mapa de alturas: la unidad no depende de colisiones ni
  del LiDAR para saber dónde están sus pies.
- Calibración mediante cuatro esquinas, incluso si la mesa está rotada.
- Adaptador ARKit: sesión, planos horizontales, malla LiDAR, pose de cámara y
  raycast desde la cruz central.
- Conversión de cámara ARKit Y/CbCr a RGB con diagnóstico del tiempo de copia.

## Probar ahora en el Mac

```sh
cd godot/poc_tabletop_ar
godot --path .
```

La escena arranca con el aldeano caminando desde el extremo izquierdo hacia
las primeras rocas del centro. Al llegar se detiene; `Repetir paseo` lo
devuelve al cabo para iniciar el trayecto otra vez. Al hacer clic sobre el
terreno se fija un destino manual. `Cámara` recorre las vistas de plano fijo,
general y cenital. También puedes crear un destino aleatorio o mostrar la
cuadrícula.

Pruebas automáticas:

```sh
tools/run_tests.sh
```

## Vista web rápida

La vista web ejecuta el mismo paseo, cámaras y controles del simulador sin
compilar ni firmar la aplicación iOS. ARKit y LiDAR permanecen desactivados en
el navegador. Para mantener una carga razonable, el feature `web_preview`
reduce el bioma de 25.060 a unas 7.000 instancias, baja la teselación del
océano y desactiva MSAA; la build nativa conserva la calidad completa.

Con las plantillas Web de Godot 4.7.1 instaladas:

```sh
tools/export_web_preview.sh
python3 -m http.server 8060 --directory exports/web-preview
```

Abrir `http://localhost:8060`. El exportador usa
`export_presets.web.example` temporalmente y restaura cualquier
`export_presets.cfg` existente, por lo que no pisa la configuración iOS.

El panel del visor incluye **Alejar**, **Acercar** y giro de 15° en ambos
sentidos alrededor del eje vertical central de la isla. También se puede usar
la rueda del mouse o las teclas `+`/`−` para zoom, `Q`/`E` para girar,
arrastrar con el botón derecho para un giro continuo y `R` para restaurar el
encuadre. En pantallas táctiles, un arrastre horizontal gira la vista; un toque
corto sigue marcando el destino del aldeano.

Para validar con una plantilla descargada fuera de la instalación de Godot:

```sh
GODOT_WEB_TEMPLATE_RELEASE=/ruta/web_nothreads_release.zip \
  tools/export_web_preview.sh
```

El workflow `.github/workflows/godot-web-preview.yml` repite la exportación
con `barichello/godot-ci:4.7.1` y publica el resultado mediante GitHub Pages
cuando cambia este proyecto en `main`. En el repositorio remoto solo hay que
seleccionar **Settings → Pages → Source: GitHub Actions** una vez.

El preset es deliberadamente single-thread y no empaqueta GDExtensions,
binarios Apple, fuentes `.blend`, herramientas, pruebas ni previews de
autoría. Sí conserva los mapas float32 `.bin` requeridos en runtime.

## Regenerar la isla tropical

Los assets del bioma, las 24 capas PBR 1K y los campos del mundo se generan de
forma determinista con NumPy y Blender:

```sh
tools/generate_island_biome.sh
```

El comando produce los GLB bajo `assets/environment/island_biome/`, sus
fuentes `.blend`, ocho capas en el orden `wet_sand`, `dry_sand`, `soil`,
`grass_green`, `grass_dry`, `rock`, `litter`, `pebbles`, y los campos
métricos `island_sdf_f32.bin` e `island_height_f32.bin`. Godot construye en
runtime los tres arrays desde `textures/layers/`; los PNG individuales
permiten reemplazar un set sin tocar escenas ni shader. El runtime lee los
campos métricos como RF float32 también desde un PCK; los EXR equivalentes
quedan como fuentes de autoría. Los demás mapas contienen splats, detalle y
densidad ecológica, incluida la normal topográfica y la oclusión de horizonte.
El preset de exportación debe conservar el filtro
`assets/environment/island_biome/world/*.bin`, ya incluido en
`export_presets.ios.example`.
También actualiza las láminas de revisión en `previews/island_biome/`. Las
referencias conservadas son
`art/references/island_biome/foto_1.jpg` para materiales y
`island_720x400_target.jpg` para silueta y composición.

Los atlas fuente se conservan bajo `art/source/palm_fronds/` y
`art/source/shrub_foliage/`; el build los reempaca a 2K, dilata RGB bajo alfa
para proteger mipmaps y deriva normal y máscara con
`tools/build_palm_frond_atlas.sh` y `tools/build_shrub_atlas.sh`. Blender usa
esos atlas para las vistas de autoría, pero los GLB solo embeben placeholders
de 4 px: Godot enlaza una única copia compartida por familia y nombre de
material, activa alpha-clip, `BACKLIGHT` y viento únicamente en frondas/hojas,
y mantiene rígidos troncos, tallos y frutos.

Para renderizar nuevamente las vistas integradas del juego:

```sh
godot --path . --script res://tools/capture_island_biome.gd
```

## Regenerar el personaje con Blender

El guardia y sus artefactos se generan de manera reproducible:

```sh
tools/generate_human.sh
```

El generador está en `tools/blender/generate_frontier_guard.py`. Produce:

- `assets/units/human_base.glb`: modelo de 69.396 triángulos para Godot.
- `assets/units/source/frontier_guard.blend`: fuente editable de Blender.
- `previews/frontier_guard_hero.png`, `frontier_guard_front.png`,
  `frontier_guard_rear.png`, `frontier_guard_walk.png` y
  `frontier_guard_attack.png`: renders de revisión estática y animada.

La referencia visual está en
`art/concepts/frontier_guard_turnaround_v1.png`. El rostro anatómico procede
del paquete CC0 Human Base Meshes de Blender Foundation; su origen y checksum
están documentados en `art/source/README.md`. El GLB conserva una altura base
de 1,82 m; nunca debe exportarse ya reducido a 1:180.

## Regenerar el aldeano TRELLIS 2

El master 1024/4K permanece fuera del runtime y el pase reproducible de Blender
produce la versión optimizada:

```sh
tools/generate_villager.sh
```

Salidas principales:

- `assets/units/villager_trellis.glb`: LOD0 skinned de 72.000 triángulos.
- `scenes/units/villager_asset.tscn`: escena reutilizable con cápsula.
- `assets/units/source/villager_trellis.blend`: fuente editable con master,
  malla de juego, rig y acciones.
- `assets/units/textures/villager_trellis/`: BaseColor y metallic/roughness
  4K/2K, normal tangente 2K y ambient occlusion 2K.
- `previews/villager_trellis/`: frente, espalda, hero, marcha y ataque.

El proyecto de trazabilidad de 3D Gen Studio se llama
`Aldeano AoE - TRELLIS 2 - Asset de juego - 2026-08-11`. Conserva las
referencias, la comparación de semillas, el master y el asset final; su bundle
exportado está en
`../../artifacts/villager-3dgen-20260811/studio_export/`.

El playbook completo para repetir el proceso, incluyendo la comparación con
Hunyuan, el barrido de semillas, el binding mediante proxy voxel y los gates de
calidad, está en [`docs/VILLAGER_3D_PIPELINE.md`](../../docs/VILLAGER_3D_PIPELINE.md).

### Marcha del aldeano

El ciclo está adaptado de `Walk_Loop` de la Universal Animation Library de
Quaternius (CC0). Conserva sus ocho poses mecánicas y limita la flexión máxima
de rodilla a 64° para proteger la malla fusionada de TRELLIS. La fase de
elevación añade 32° de flexión de cadera para proyectar claramente la rodilla
hacia delante. Godot instala la
versión canónica al cargar el rig, sincroniza su fase con la distancia recorrida
y aplica `TwoBoneIK3D` sólo al pie que está en apoyo para seguir el relieve.
La conversión sagital está validada explícitamente para el frente `-Z` de
Godot: en contacto izquierdo ese pie queda delante, el derecho entra en swing
y el brazo derecho contrapesa. La marcha usa 3,34 m virtuales por ciclo y
3,6 m/s; esa relación reproduce la apertura completa del paso y mantiene el
pie apoyado dentro de 10 cm de su punto de contacto. Durante cada apoyo, el
tobillo queda anclado en coordenadas del terreno y la orientación global del
zapato se conserva mientras soporta peso; así la suela no barre la superficie
al cambiar el ángulo animado del pie. El IK permanece al 100 % durante la
carga. Los contactos se superponen
de forma complementaria: el pie anterior se libera entre 37,5 % y 50 % de su
ciclo local mientras el entrante recibe influencia durante su descenso final
(87,5–100 %). Su XZ sólo se captura al contacto, no mientras aún está en el
aire. Un `SkeletonModifier3D` prepara los objetivos después de
`AnimationPlayer` y antes de ambos IK, eliminando el desfase de un fotograma.
Así siempre existe un apoyo efectivo sin forzar una pierna más allá de su
alcance, evitando tanto el `foot skating` como el efecto de cinta.

Para revisar las ocho fases en primer plano:

```sh
godot --path . --script tools/capture_villager_walk_phases.gd
```

Para renderizar diez segundos de revisión cercana dentro de la isla:

```sh
tools/render_villager_walk_detail_video.sh
```

Si se necesita hornear la misma marcha dentro del GLB sin repetir decimación ni
bakes PBR:

```sh
tools/update_villager_walk.sh
```

Referencia CC0:
https://quaternius.com/packs/universalanimationlibrary.html

## Flujo de calibración en iOS

1. Mover lentamente el iPhone para que ARKit detecte el plano y la malla.
2. Permanecer en un lado de la mesa.
3. Apuntar la cruz y capturar, en orden: frente-izquierda, frente-derecha,
   fondo-derecha y fondo-izquierda.
4. La aplicación mide el rectángulo, reortogonaliza pequeños errores y bloquea
   el sistema de coordenadas.
5. Tocar el terreno para mover la unidad.

El contorno de un `ARPlaneAnchor` no se usa como medida definitiva: ARKit puede
seguir refinándolo. LiDAR aporta superficie y raycasts; las cuatro esquinas
aportan escala, origen y orientación controlados.

## Estado de preparación iOS

Ya quedó preparado en el Mac:

1. Godot **4.7.1** y sus plantillas oficiales de exportación iOS.
2. Blender **5.2.0 LTS** y el personaje GLB generado.
3. Godot Apple Plugins con ARKit y su runtime Swift.
4. Compresión móvil ETC2/ASTC, cámara y descripción de privacidad.
5. Exportación de prueba de los archivos Xcode completada; el proyecto generado
   enlazó `GodotApplePluginsARKit.xcframework` y `SwiftGodotRuntime.xcframework`.

Queda pendiente para compilar, firmar e instalar en el iPhone/iPad:

1. Instalar Xcode completo, abrirlo una vez y aceptar su licencia.
2. Apuntar `xcode-select` a `/Applications/Xcode.app/Contents/Developer`.
3. Añadir la cuenta Apple Developer a Xcode y crear una identidad Apple
   Development.
4. Copiar `export_presets.ios.example` a `export_presets.cfg` y reemplazar
   el Team ID de 10 caracteres y el bundle identifier.

Godot exige Xcode, plantillas de exportación, Team ID y bundle identifier para
la compilación iOS. La guía oficial está en
https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_ios.html.

El complemento instalado es Godot Apple Plugins, revisión
`3781b9c19eaf69b2387eacecf4b6f88fc8d07e65`, y requiere iOS 17 o posterior.
Puede reinstalarse con:

```sh
tools/install_apple_plugins.sh
```

## Riesgo que medirá el primer dispositivo

La versión inicial copia los planos de cámara desde `ARFrame` a dos texturas de
Godot, limitada a 20 actualizaciones por segundo. La interfaz muestra el costo
en milisegundos. Si consume demasiado tiempo o memoria, el siguiente hito será
reemplazarla por un puente Metal/CVMetalTextureCache de copia cero.
