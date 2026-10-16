# Organic Kit 1.0.0

Complemento para Blender 4.2 a 5.x para crear **figuras orgánicas** (chibis anime, criaturas,
mascotas) con un clic o con código. Pensado también para que un agente (Claude por MCP) construya
figuras paso a paso. Todo en modo Objeto y en milímetros. Licencia GPL-3.0-or-later.

## A mano (Vista 3D → N → pestaña Organic Kit)

- **Personaje chibi**: alto, pelo (puntas, suave, flequillo o sin pelo), orejas (gato, elfo, oso),
  cola, más o menos rellenito, color de pelo y de ojos, variante de pelo. Sale por **piezas de color**
  (cuerpo, pelo, blancos de los ojos, iris y brillos) sin solaparse, listo para imprimir en colores.
- **Escultor** sobre lo seleccionado: fundir en un sólido, alisar, engordar/adelgazar, simetría X,
  bajar al suelo.

## Con código (agente)

```python
import organic_kit.kit as ok
from organic_kit import recipes

parts = recipes.chibi('Neko', 90, hair='BANGS', ears='CAT', tail=True)
body = ok.skin_body('cuerpo', {'cadera': (0, 0, 20), 'pecho': (0, 0, 35)}, [('cadera', 'pecho')], {'cadera': 8, 'pecho': 7})
head = ok.blobs('cabeza', [{'at': (0, 0, 55), 'r': 18, 'type': 'ELLIPSOID', 'scale': (1, 0.95, 0.9)}])
horn = ok.tube('cuerno', [(5, 0, 70), (8, 2, 80), (6, 6, 88)], [3, 2, 0.3])
solid = ok.fuse([body, head, horn], 'criatura')
ok.smooth(solid, 5); ok.colorize(solid, 'verde'); ok.place_on_floor(solid)
ok.snapshot(r'E:\Downloads\vista.png', ('FRONT', 'ISO', 'RIGHT')); print(ok.report())
```

Funciones: `skin_body`, `blobs`, `tube`, `hair_spikes`, `eyes`, `ears`, `join`, `mirror_x`, `fuse`,
`smooth`, `inflate`, `union`, `carve`, `colorize`, `place_on_floor`, `look`, `snapshot` (PNG de varias vistas, aunque Blender esté minimizado), `report`.
La figura mira hacia -Y (vista Frontal de Blender) y apoya en Z = 0. En `blobs`, `r` es el radio
que se ve.

Después: Print Ready (dejar listo), Hollow Fill (vaciar si es grande), MagSnap/BigPrint (partir).

## Proyectos: un alcance y cada pieza en su hilo

Para figuras con varias piezas, cada pieza se trabaja por separado (en su propio hilo de chat con el
agente) y al final se ensambla. Todo queda en `D:\Lugaresi3D\02-Trabajos\Figuras\<proyecto>\`.

```python
from organic_kit import project as pr
pr.create('Dragoncito', {'personaje': 'dragón chibi', 'colores': 'verde y amarillo', 'impresion': 'por colores'},
          [{'id': 'cuerpo', 'color': 'verde', 'encargo': 'cuerpo, cabeza, patas y cola'},
           {'id': 'alas', 'color': 'amarillo'}, {'id': 'ojos', 'color': 'blanco'}], height=80)
s = pr.open_piece('Dragoncito', 'alas')      # escena con la guía y las demás piezas en alambre
# … construir con organic_kit.kit usando s['anclajes'] y s['R'] …
pr.save_piece('Dragoncito', 'alas', [obj], note='alas cortas', done=True)   # vNN.blend + vNN.png
pr.status('Dragoncito')
pr.assemble('Dragoncito')                    # monta, quita solapes, STL por color y captura
```

- `proyecto.json` / `alcance.md`: alcance, proporciones (anclajes comunes para que todo encaje) y el
  estado de cada pieza (pendiente, en curso, lista), con la frase para abrir el hilo de cada una.
- Las versiones de cada pieza nunca se pisan (`piezas/<pieza>/v01, v02…`).
- En el ensamblaje, cada pieza deja hueco a las que van después en la lista (cuerpo → pelo → ojos…).
