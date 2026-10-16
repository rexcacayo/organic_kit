# SPDX-FileCopyrightText: 2026 Ricardo Lugaresi
# SPDX-License-Identifier: GPL-3.0-or-later

"""Figuras como proyecto: un alcance y cada pieza en su propio hilo de trabajo.

Carpeta del proyecto (por defecto D:\\Lugaresi3D\\02-Trabajos\\Figuras\\<proyecto>):
    proyecto.json      alcance, proporciones (anclajes comunes) y estado de cada pieza
    alcance.md         lo mismo para leer, con la frase para abrir el hilo de cada pieza
    guia.blend         guía de proporciones (anclajes y volúmenes de referencia)
    piezas/<pieza>/vNN.blend + vNN.png   versiones de cada pieza (nunca se pisan)
    ensamblaje/        figura montada, capturas y STL por color

Un hilo de pieza solo carga la guía y las otras piezas como referencia (en alambre, sin poder
tocarlas): trabaja su pieza, la guarda como versión nueva y marca su estado. El hilo final ensambla.
"""
import datetime
import json
import os
import re
from pathlib import Path

import bpy
from mathutils import Vector

from . import common, kit

DEFAULT_ROOT = r'D:\Lugaresi3D\02-Trabajos\Figuras'
STATES = ('pendiente', 'en curso', 'lista')


def slug(name):
    s = re.sub(r'[^a-z0-9]+', '-', name.lower().translate(str.maketrans('áéíóúñü', 'aeiounu'))).strip('-')
    return s or 'figura'


def folder(name, root=None):
    return Path(root or os.environ.get('ORGANIC_ROOT') or DEFAULT_ROOT) / slug(name)


def load(name, root=None):
    p = folder(name, root) / 'proyecto.json'
    if not p.is_file():
        raise common.AddonError(f'No existe el proyecto «{name}» en {p.parent}.')
    return json.loads(p.read_text(encoding='utf-8'))


def _save(pj, root=None):
    f = folder(pj['nombre'], root)
    (f / 'proyecto.json').write_text(json.dumps(pj, ensure_ascii=False, indent=2), encoding='utf-8')
    (f / 'alcance.md').write_text(_alcance_md(pj), encoding='utf-8')


def _alcance_md(pj):
    a = pj['alcance']
    lines = [f"# {pj['nombre']}", '', f"Creado: {pj['creado']}", '', '## Alcance', '']
    for k, v in a.items():
        lines.append(f'- **{k}**: {v}')
    lines += ['', '## Proporciones', '', f"- alto: {pj['proporciones']['alto_mm']} mm · "
              f"cabezas de alto: {pj['proporciones']['cabezas']} · radio de cabeza: {pj['proporciones']['R']:.1f} mm", '']
    lines += ['## Piezas (un hilo cada una)', '', '| pieza | color | estado | versión | notas |', '|---|---|---|---|---|']
    for p in pj['piezas']:
        lines.append(f"| {p['id']} | {p['color']} | {p['estado']} | {p['version'] or '—'} | {p.get('notas', '')} |")
    lines += ['', '### Para abrir cada hilo', '']
    for p in pj['piezas']:
        lines.append(f"- «Escultor: proyecto {pj['nombre']}, pieza {p['id']}» — {p.get('encargo', '')}")
    lines.append(f"- «Escultor: proyecto {pj['nombre']}, ensamblar» — montar, revisar y dejar imprimible")
    return '\n'.join(lines) + '\n'


def anchors_for(height, heads):
    """Anclajes comunes (mm, figura mirando a -Y, de pie en Z=0) para que las piezas encajen
    aunque se hagan en hilos distintos."""
    H = float(height)
    R = H / heads / 2.0
    hc = H - R
    torso_top = H - 2 * R
    return R, {
        'cabeza_centro': (0, 0, hc), 'cara': (0, -0.9 * R, hc - 0.12 * R), 'cuello': (0, 0, torso_top + 0.03 * H),
        'pecho': (0, 0, torso_top - 0.12 * H * 2.4 / heads), 'pelvis': (0, 0, 0.30 * H if heads < 4 else 0.48 * H),
        'hombro_d': (0.11 * H * 2.4 / heads + 0.0, 0, torso_top - 0.02 * H), 'hombro_i': (-(0.11 * H * 2.4 / heads), 0, torso_top - 0.02 * H),
        'cadera_d': (0.055 * H, 0, 0.27 * H if heads < 4 else 0.46 * H), 'cadera_i': (-0.055 * H, 0, 0.27 * H if heads < 4 else 0.46 * H),
        'pie_d': (0.07 * H, -0.02 * H, 0.0), 'pie_i': (-0.07 * H, -0.02 * H, 0.0),
    }


def create(name, alcance, piezas, height=80.0, heads=2.4, root=None):
    """Crea el proyecto. piezas: lista de dicts {'id', 'color', 'encargo'} (o solo ids).
    alcance: dict libre (personaje, estilo, pose, referencia, colores, impresion…)."""
    f = folder(name, root)
    if (f / 'proyecto.json').exists():
        raise common.AddonError(f'Ya existe el proyecto «{name}». Ábrelo con project.load o usa otro nombre.')
    (f / 'piezas').mkdir(parents=True, exist_ok=True)
    (f / 'ensamblaje').mkdir(exist_ok=True)
    R, anchors = anchors_for(height, heads)
    items = []
    for p in piezas:
        p = {'id': p} if isinstance(p, str) else dict(p)
        p['id'] = slug(p['id'])
        p.setdefault('color', 'piel'); p.setdefault('encargo', '')
        p.update({'estado': 'pendiente', 'version': None, 'notas': ''})
        items.append(p)
    pj = {'nombre': name, 'creado': datetime.date.today().isoformat(), 'alcance': dict(alcance),
          'proporciones': {'alto_mm': height, 'cabezas': heads, 'R': R, 'anclajes': anchors}, 'piezas': items}
    _save(pj, root)
    _write_guide(pj, root)
    return pj


def _write_guide(pj, root=None):
    """guia.blend: un empty por anclaje y volúmenes simples (cabeza, torso) como referencia."""
    f = folder(pj['nombre'], root)
    R = pj['proporciones']['R']; A = pj['proporciones']['anclajes']
    objs = []
    for k, co in A.items():
        e = bpy.data.objects.new(f'ancla_{k}', None)
        e.empty_display_type = 'SPHERE'; e.empty_display_size = max(1.0, R * 0.08)
        e.location = co
        objs.append(e)
    head = kit.blobs('guia_cabeza', [{'at': A['cabeza_centro'], 'r': R}])
    torso = kit.tube('guia_torso', [A['pelvis'], A['pecho'], A['cuello']], [R * 0.6, R * 0.55, R * 0.25])
    objs += [head, torso]
    for o in (head, torso):
        o.display_type = 'WIRE'
    bpy.data.libraries.write(str(f / 'guia.blend'), set(objs), fake_user=True)
    kit._remove([head, torso])
    for e in objs[:-2]:
        bpy.data.objects.remove(e)


def _piece(pj, pid):
    pid = slug(pid)
    for p in pj['piezas']:
        if p['id'] == pid:
            return p
    raise common.AddonError(f'El proyecto no tiene la pieza «{pid}». Piezas: {", ".join(p["id"] for p in pj["piezas"])}.')


def _append(path):
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.objects = list(src.objects)
    return [o for o in dst.objects if o is not None]


def open_piece(name, pid, root=None):
    """Escena nueva para trabajar UNA pieza: guía + últimas versiones de las demás en alambre (referencia)."""
    pj = load(name, root)
    p = _piece(pj, pid)
    f = folder(name, root)
    sc = bpy.data.scenes.new(f"{pj['nombre']} · {p['id']}")
    if bpy.context.window:
        bpy.context.window.scene = sc
    ref = bpy.data.collections.new('Referencia (no tocar)')
    sc.collection.children.link(ref)
    work = bpy.data.collections.new(f"Pieza {p['id']}")
    sc.collection.children.link(work)
    for o in _append(f / 'guia.blend'):
        ref.objects.link(o)
        if o.type == 'MESH':
            o.display_type = 'WIRE'; o.hide_select = True; o.hide_render = True
    for other in pj['piezas']:
        if other['version'] is None:
            continue
        objs = _append(f / 'piezas' / other['id'] / f"{other['version']}.blend")
        for o in objs:
            if other['id'] == p['id']:
                work.objects.link(o)          # se sigue desde la última versión de esta pieza
            else:
                o.display_type = 'WIRE'; o.hide_select = True; o.hide_render = True
                ref.objects.link(o)
    if p['estado'] == 'pendiente':
        p['estado'] = 'en curso'
        _save(pj, root)
    return {'scene': sc.name, 'pieza': p, 'anclajes': pj['proporciones']['anclajes'], 'R': pj['proporciones']['R'],
            'alcance': pj['alcance'], 'seguir_desde': p['version']}


def save_piece(name, pid, objs, note='', done=False, root=None):
    """Guarda la pieza como versión nueva (vNN.blend + vNN.png con la referencia de fondo)."""
    pj = load(name, root)
    p = _piece(pj, pid)
    objs = [o for o in (objs if isinstance(objs, (list, tuple)) else [objs]) if o is not None]
    if not objs:
        raise common.AddonError('No hay nada que guardar en esta pieza.')
    d = folder(name, root) / 'piezas' / p['id']
    d.mkdir(parents=True, exist_ok=True)
    n = len(list(d.glob('v*.blend'))) + 1
    vid = f'v{n:02d}'
    for o in objs:
        o['organic_pieza'] = p['id']
        if not o.data.materials:
            kit.colorize(o, p['color'])
    bpy.data.libraries.write(str(d / f'{vid}.blend'), set(objs), fake_user=True)
    shot = kit.snapshot(str(d / f'{vid}.png'), ('FRONT', 'ISO', 'RIGHT'), objs)
    rep = kit.report(objs)
    p['version'] = vid
    p['estado'] = 'lista' if done else 'en curso'
    if note:
        p['notas'] = note
    _save(pj, root)
    return {'version': vid, 'captura': shot, 'medidas': rep}


def status(name, root=None):
    pj = load(name, root)
    return [{'id': p['id'], 'color': p['color'], 'estado': p['estado'], 'version': p['version'], 'notas': p.get('notas', '')}
            for p in pj['piezas']]


def assemble(name, export=True, root=None):
    """Monta la figura con la última versión de cada pieza, quita solapes entre colores (cada pieza
    deja hueco a las que van encima, en el orden de la lista), apoya en Z=0 y exporta STL por color."""
    pj = load(name, root)
    f = folder(name, root)
    sc = bpy.data.scenes.new(f"{pj['nombre']} · ensamblaje")
    if bpy.context.window:
        bpy.context.window.scene = sc
    col = bpy.data.collections.new('Figura'); sc.collection.children.link(col)
    missing = [p['id'] for p in pj['piezas'] if p['version'] is None]
    pieces = []
    for p in pj['piezas']:
        if p['version'] is None:
            continue
        objs = _append(f / 'piezas' / p['id'] / f"{p['version']}.blend")
        for o in objs:
            col.objects.link(o)
        merged = kit.join(objs, p['id'], col) if len(objs) > 1 else objs[0]
        pieces.append((p, merged))
    if not pieces:
        raise common.AddonError('Todavía no hay ninguna pieza guardada.')
    # solapes: lo que va antes en la lista (cuerpo) deja hueco a lo que va después (pelo, ojos, ropa)
    overlaps = []
    for i, (p, obj) in enumerate(pieces):
        for q, other in pieces[i + 1:]:
            cutter = other.copy(); cutter.data = other.data.copy(); col.objects.link(cutter)
            try:
                kit.carve(obj, cutter)
            except common.AddonError:
                kit._remove([cutter])
                overlaps.append(f"{p['id']}/{q['id']}")
    objs = [o for _p, o in pieces]
    kit.place_on_floor(objs)
    rep = kit.report(objs)
    files = []
    if export:
        out = f / 'ensamblaje'
        for p, o in pieces:
            for s in sc.objects:
                s.select_set(False)
            o.select_set(True)
            fp = out / f"{slug(pj['nombre'])}_{p['id']}_{p['color']}.stl"
            if hasattr(bpy.ops.wm, 'stl_export'):
                bpy.ops.wm.stl_export(filepath=str(fp), export_selected_objects=True, global_scale=1.0)
            else:
                bpy.ops.export_mesh.stl(filepath=str(fp), use_selection=True)
            files.append(str(fp))
        kit.snapshot(str(out / 'figura.png'), ('FRONT', 'ISO', 'ISO_BACK'), objs)
        bpy.data.libraries.write(str(out / 'figura.blend'), set(objs), fake_user=True)
    return {'medidas': rep, 'stl': files, 'faltan': missing, 'solapes_sin_quitar': overlaps,
            'captura': str(f / 'ensamblaje' / 'figura.png')}
