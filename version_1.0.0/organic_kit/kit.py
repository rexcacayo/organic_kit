# SPDX-FileCopyrightText: 2026 Ricardo Lugaresi
# SPDX-License-Identifier: GPL-3.0-or-later

"""Herramientas de «escultor» para construir figuras orgánicas con código (agente por MCP o a mano).

Todo en milímetros, en modo Objeto, Z hacia arriba, la figura mira hacia -Y (de frente en la vista
Frontal de Blender). Cada función crea un objeto malla nuevo y lo devuelve.

Piezas de construcción:
    skin_body   esqueleto de palitos con grosores → cuerpo, brazos, patas, colas (modificador Skin)
    blobs       formas tipo plastilina que se funden (metabolas): cabezas, mejillas, barrigas, manos
    tube        tubo por puntos con grosor variable: colas, cuernos, tentáculos, mechones
    hair_spikes mechones de pelo anime repartidos por la cabeza
    eyes        ojos anime (blanco, iris y brillo como piezas separadas, para imprimir en colores)
    ears        orejas de gato, elfo o redondas
Operaciones:
    mirror_x, fuse (todo en un sólido), smooth, inflate, union, carve, colorize, place_on_floor
    look (encuadra la vista), snapshot (PNG de varias vistas, aunque Blender esté minimizado),
    report (medidas y si cada pieza está cerrada)
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import common

TIP = 0.5        # radio mínimo de las puntas (mm): más fino no sale al imprimir con boquilla 0,4
PALETTE = {'piel': (1.0, 0.82, 0.70, 1), 'pelo': (0.35, 0.22, 0.55, 1), 'blanco': (0.95, 0.95, 0.95, 1),
           'iris': (0.15, 0.45, 0.85, 1), 'negro': (0.05, 0.05, 0.05, 1), 'ropa': (0.85, 0.25, 0.25, 1),
           'rosa': (1.0, 0.55, 0.65, 1), 'verde': (0.3, 0.7, 0.35, 1), 'amarillo': (1.0, 0.85, 0.2, 1)}


# --------------------------------------------------------------------------- utilidades
def _collection(name='Organic Kit'):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
    scene_root = bpy.context.scene.collection
    if col.name not in {c.name for c in scene_root.children_recursive}:
        scene_root.children.link(col)          # siempre visible en la escena actual (si no, no se evalúa)
    return col


def _link(obj, col=None):
    (col or _collection()).objects.link(obj)
    obj[common.UNIT_PROP] = 'MM'
    obj['organic_kit'] = True
    return obj


def _mesh_object(name, me, col=None):
    return _link(bpy.data.objects.new(name, me), col)


def _evaluated_copy(obj, name):
    """Malla con los modificadores aplicados (sin bpy.ops)."""
    graph = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(graph), depsgraph=graph)
    me.name = name
    me.transform(obj.matrix_world)
    return me


def _replace(obj, me):
    old = obj.data
    obj.data = me
    obj.matrix_world = Matrix.Identity(4)
    if old.users == 0 and isinstance(old, bpy.types.Mesh):
        bpy.data.meshes.remove(old)
    return obj


def _remove(objs):
    for o in list(objs):
        if o is None or o.name not in bpy.data.objects:
            continue
        data = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if data is not None and data.users == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.MetaBall):
                bpy.data.metaballs.remove(data)
            elif isinstance(data, bpy.types.Curve):
                bpy.data.curves.remove(data)


def _arrays(obj):
    me = obj.data
    V = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', V)
    E = np.empty(len(me.edges) * 2, np.int64); me.edges.foreach_get('vertices', E)
    return V.reshape(-1, 3), E.reshape(-1, 2)


def _set_co(obj, V):
    obj.data.vertices.foreach_set('co', V.astype(np.float32).ravel())
    obj.data.update()


# --------------------------------------------------------------------------- piezas
def skin_body(name, joints, bones, radii, subdiv=2, col=None):
    """Cuerpo desde un esqueleto.
    joints: {'cadera': (x, y, z), ...} en mm · bones: [('cadera', 'pecho'), ...]
    radii: {'cadera': 9 o (rx, ry)} grosor en cada articulación (por defecto 3 mm)."""
    names = list(joints)
    idx = {n: i for i, n in enumerate(names)}
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(joints[n]) for n in names], [(idx[a], idx[b]) for a, b in bones], [])
    me.update()
    tmp = bpy.data.objects.new(name + '_esqueleto', me)
    bpy.context.scene.collection.objects.link(tmp)
    try:
        skin = tmp.modifiers.new('Skin', 'SKIN')
        skin.use_smooth_shade = True
        sv = me.skin_vertices[0].data
        for n, i in idx.items():
            r = radii.get(n, 3.0)
            sv[i].radius = (r, r) if isinstance(r, (int, float)) else tuple(r)
            sv[i].use_root = (i == 0)
        if subdiv:
            sub = tmp.modifiers.new('Sub', 'SUBSURF')
            sub.levels = subdiv
            sub.render_levels = subdiv
        bpy.context.view_layer.update()
        out = _evaluated_copy(tmp, name)
    finally:
        _remove([tmp])
    return _mesh_object(name, out, col)


def blobs(name, elements, resolution=None, threshold=0.6, col=None):
    """Metabolas que se funden. elements: lista de dicts
    {'at': (x,y,z), 'r': radio, 'scale': (sx,sy,sz), 'rot': (rx,ry,rz) grados, 'type': 'BALL'|'ELLIPSOID'|'CAPSULE',
     'negative': False, 'stiffness': 2.0}"""
    mb = bpy.data.metaballs.new(name)
    rmin = min(e.get('r', 5.0) * min(e.get('scale', (1, 1, 1))) for e in elements)   # radio visible
    mb.resolution = resolution or max(0.12, rmin / 6.0)
    mb.render_resolution = mb.resolution
    mb.threshold = threshold
    for e in elements:
        el = mb.elements.new(type=e.get('type', 'BALL'))
        el.co = Vector(e['at'])
        el.stiffness = e.get('stiffness', 2.0)
        # 'r' es el radio que se ve: el campo de la metabola llega más lejos que su superficie
        visible = math.sqrt(max(1e-6, 1.0 - (threshold / el.stiffness) ** (1.0 / 3.0)))
        el.radius = e.get('r', 5.0) / visible
        el.use_negative = e.get('negative', False)
        sx, sy, sz = e.get('scale', (1, 1, 1))
        if el.type in {'ELLIPSOID', 'CAPSULE', 'CUBE', 'PLANE'}:
            el.size_x, el.size_y, el.size_z = sx, sy, sz          # proporciones (relativas al radio)
        rx, ry, rz = (math.radians(a) for a in e.get('rot', (0, 0, 0)))
        from mathutils import Euler
        el.rotation = Euler((rx, ry, rz)).to_quaternion()
    tmp = bpy.data.objects.new(name + '_meta', mb)
    bpy.context.scene.collection.objects.link(tmp)
    try:
        bpy.context.view_layer.update()
        out = _evaluated_copy(tmp, name)
    finally:
        _remove([tmp])
    if not len(out.polygons):
        bpy.data.meshes.remove(out)
        raise common.AddonError(f'{name}: las metabolas no han dado forma (radios muy pequeños o umbral alto).')
    return _mesh_object(name, out, col)


def tube(name, points, radii, sides=16, smooth=True, caps=True, col=None):
    """Tubo que pasa por los puntos con grosor (radio en mm) en cada uno."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_mode = 'ROUND'
    cu.bevel_depth = 1.0
    cu.bevel_resolution = max(2, sides // 4)
    cu.use_fill_caps = caps
    cu.resolution_u = 8 if smooth else 1
    sp = cu.splines.new('NURBS' if smooth else 'POLY')
    sp.points.add(len(points) - 1)
    for p, co, r in zip(sp.points, points, radii):
        p.co = (*co, 1.0)
        p.radius = r
    if smooth:
        sp.use_endpoint_u = True
        sp.order_u = min(4, len(points))
    tmp = bpy.data.objects.new(name + '_curva', cu)
    bpy.context.scene.collection.objects.link(tmp)
    try:
        bpy.context.view_layer.update()
        out = _evaluated_copy(tmp, name)
    finally:
        _remove([tmp])
    return _mesh_object(name, out, col)


def _fib_dirs(n, z_min=0.0, back_bias=0.0, seed=0):
    """Direcciones repartidas por la parte de arriba de una esfera (Fibonacci)."""
    out = []
    golden = math.pi * (3 - math.sqrt(5))
    rng = np.random.default_rng(seed)
    k = 0
    while len(out) < n and k < n * 20:
        i = k + 0.5
        z = 1 - 2 * i / (n * 3)
        r = math.sqrt(max(0.0, 1 - z * z))
        a = golden * k
        d = Vector((math.cos(a) * r, math.sin(a) * r, z))
        k += 1
        if d.z < z_min or (d.y < -0.35 and d.z < 0.55):     # deja la cara libre (la figura mira a -Y)
            continue
        d.y += back_bias
        d += Vector(rng.normal(0, 0.05, 3))
        out.append(d.normalized())
    return out


def hair_spikes(name, head_center, head_radius, count=14, length=None, thickness=None, droop=0.6,
                style='SPIKY', seed=1, col=None):
    """Mechones anime: conos curvados que salen de la cabeza y caen hacia abajo/atrás.
    style: 'SPIKY' (puntas hacia fuera), 'SOFT' (caen pegados), 'BANGS' (flequillo delante incluido)."""
    c = Vector(head_center)
    R = head_radius
    L = length or R * 1.1
    T = thickness or R * 0.32
    parts = []
    dirs = _fib_dirs(count, z_min=-0.1 if style != 'SOFT' else -0.3, back_bias=0.15, seed=seed)
    for i, d in enumerate(dirs):
        root = c + d * (R * 0.75)
        out_dir = d.copy()
        grav = Vector((0, 0.15, -1.0)) * (droop if style != 'SPIKY' else droop * 0.5)
        p1 = root + out_dir * (L * 0.45) + grav * (L * 0.15)
        p2 = p1 + (out_dir * 0.6 + grav).normalized() * (L * 0.4)
        p3 = p2 + (out_dir * 0.4 + grav * 1.3).normalized() * (L * 0.3)
        pts = [root, p1, p2, p3]
        parts.append(tube(f'{name}_{i}', [tuple(p) for p in pts], [T, T * 0.8, T * 0.45, TIP], sides=12))
    if style == 'BANGS':
        for j, x in enumerate((-0.45, 0.0, 0.45)):
            root = c + Vector((x * R, -0.55 * R, 0.75 * R))
            tip = c + Vector((x * R * 1.15, -1.02 * R, 0.05 * R))
            mid = (root + tip) / 2 + Vector((0, -0.35 * R, 0.1 * R))
            parts.append(tube(f'{name}_flequillo_{j}', [tuple(root), tuple(mid), tuple(tip)],
                              [T * 0.9, T * 0.6, TIP], sides=12))
    return join(parts, name, col)


def eyes(name, face_center, eye_height, spacing, size=None, depth=None, iris=0.62, col=None):
    """Ojos anime en la cara (que mira a -Y): blanco, iris y brillo, cada uno pieza aparte.
    face_center: punto de la superficie de la cara entre los ojos. Devuelve [blancos, iris, brillos]."""
    s = size or spacing * 0.42
    dpt = depth or s * 0.35
    whites, irises, shines = [], [], []
    for side in (-1, 1):
        cx = Vector(face_center) + Vector((side * spacing / 2, 0, 0))
        cx.z = Vector(face_center).z + (eye_height - Vector(face_center).z)
        w = blobs(f'{name}_blanco_{side}', [{'at': tuple(cx), 'r': s, 'type': 'ELLIPSOID', 'scale': (0.8, 0.35, 1.15)}], col=col)
        ir = blobs(f'{name}_iris_{side}', [{'at': tuple(cx + Vector((0, -dpt * 0.55, -s * 0.08))), 'r': s * iris,
                                            'type': 'ELLIPSOID', 'scale': (0.75, 0.3, 0.95)}], col=col)
        sh = blobs(f'{name}_brillo_{side}', [{'at': tuple(cx + Vector((side * -s * 0.18, -dpt * 0.75, s * 0.28))),
                                              'r': s * 0.2, 'type': 'BALL'}], col=col)
        whites.append(w); irises.append(ir); shines.append(sh)
    W = join(whites, f'{name}_blancos', col); colorize(W, 'blanco')
    I = join(irises, f'{name}_iris', col); colorize(I, 'iris')
    S = join(shines, f'{name}_brillos', col); colorize(S, 'blanco')
    return [W, I, S]


def ears(name, head_center, head_radius, kind='CAT', col=None):
    c = Vector(head_center); R = head_radius
    parts = []
    for side in (-1, 1):
        base = c + Vector((side * R * 0.55, 0.05 * R, R * 0.72))
        if kind == 'CAT':
            tip = base + Vector((side * R * 0.25, 0.05 * R, R * 0.65))
            parts.append(tube(f'{name}_{side}', [tuple(base), tuple((base + tip) / 2), tuple(tip)],
                              [R * 0.3, R * 0.2, TIP], sides=4, smooth=False))
        elif kind == 'ELF':
            b2 = c + Vector((side * R * 0.95, 0.1 * R, R * 0.1))
            tip = b2 + Vector((side * R * 0.7, 0.2 * R, R * 0.35))
            parts.append(tube(f'{name}_{side}', [tuple(b2), tuple(tip)], [R * 0.18, TIP], sides=8, smooth=False))
        else:   # ROUND (oso, ratón)
            parts.append(blobs(f'{name}_{side}', [{'at': tuple(base + Vector((side * R * 0.1, 0, R * 0.2))),
                                                   'r': R * 0.32, 'type': 'ELLIPSOID', 'scale': (1, 0.45, 1)}]))
    return join(parts, name, col)


# --------------------------------------------------------------------------- operaciones
def join(objs, name, col=None):
    """Une mallas en un solo objeto (sin fundirlas: siguen siendo cáscaras separadas)."""
    objs = [o for o in objs if o is not None]
    bm = bmesh.new()
    try:
        for o in objs:
            me = o.data.copy()
            me.transform(o.matrix_world)
            bm.from_mesh(me)
            bpy.data.meshes.remove(me)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
    finally:
        bm.free()
    mats = [s.material for o in objs for s in o.material_slots if s.material]
    _remove(objs)
    out = _mesh_object(name, me, col)
    if mats:
        out.data.materials.append(mats[0])
    return out


def mirror_x(obj, keep_center=True):
    """Simetría izquierda/derecha respecto a X=0 (mitad +X copiada a -X y unida)."""
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.transform(obj.matrix_world)
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        res = bmesh.ops.duplicate(bm, geom=geom)
        new_verts = [g for g in res['geom'] if isinstance(g, bmesh.types.BMVert)]
        bmesh.ops.scale(bm, vec=(-1, 1, 1), verts=new_verts)
        bmesh.ops.reverse_faces(bm, faces=[g for g in res['geom'] if isinstance(g, bmesh.types.BMFace)])
        me = bpy.data.meshes.new(obj.name)
        bm.to_mesh(me)
    finally:
        bm.free()
    return _replace(obj, me)


def fuse(objs, name, voxel=None, smooth_iter=2, col=None):
    """Funde varias piezas en UN sólido cerrado (vóxeles). voxel en mm (auto: tamaño / 220)."""
    objs = [o for o in (objs if isinstance(objs, (list, tuple)) else [objs]) if o is not None]
    mats = [s.material for o in objs for s in o.material_slots if s.material]
    j = join(objs, name + '_tmp', col)
    if voxel is None:
        voxel = max(0.15, max(j.dimensions) / 220.0)
    mod = j.modifiers.new('Fundir', 'REMESH')
    mod.mode = 'VOXEL'
    mod.voxel_size = voxel
    mod.adaptivity = 0.0
    bpy.context.view_layer.update()
    me = _evaluated_copy(j, name)
    _remove([j])
    out = _mesh_object(name, me, col)
    if mats:
        out.data.materials.append(mats[0])
    if smooth_iter:
        smooth(out, smooth_iter, 0.5)
    return out


def smooth(obj, iterations=5, factor=0.5):
    """Alisado que no encoge (Taubin)."""
    V, E = _arrays(obj)
    n = len(V)
    deg = np.maximum(np.bincount(E.ravel(), minlength=n), 1).astype(float)[:, None]
    for _ in range(iterations):
        for lam in (factor, -factor * 1.04):
            acc = np.zeros_like(V)
            np.add.at(acc, E[:, 0], V[E[:, 1]])
            np.add.at(acc, E[:, 1], V[E[:, 0]])
            V = V + lam * (acc / deg - V)
    _set_co(obj, V)
    return obj


def inflate(obj, mm):
    """Engorda (o adelgaza con negativo) por las normales."""
    me = obj.data
    N = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('normal', N)
    V, _E = _arrays(obj)
    _set_co(obj, V + N.reshape(-1, 3) * mm)
    return obj


def _volume(me, matrix=None):
    bm = bmesh.new()
    try:
        bm.from_mesh(me)
        if matrix is not None:
            bm.transform(matrix)
        closed = bool(bm.faces) and all(e.is_manifold for e in bm.edges)
        return abs(bm.calc_volume(signed=True)), closed
    finally:
        bm.free()


def _bool(obj, other, op):
    """Booleana comprobada: si el resultado no tiene sentido (cerrado y con un volumen lógico),
    se prueba el otro solver y, si tampoco, la pieza se queda como estaba."""
    solvers = [s for s in ('MANIFOLD', 'EXACT') if s in bpy.types.BooleanModifier.bl_rna.properties['solver'].enum_items.keys()]
    v_obj, _c = _volume(obj.data, obj.matrix_world)
    v_oth, _c = _volume(other.data, other.matrix_world)
    for solver in solvers:
        mod = obj.modifiers.new('ok_bool', 'BOOLEAN')
        mod.operation = op
        mod.solver = solver
        mod.object = other
        try:
            bpy.context.view_layer.update()
            graph = bpy.context.evaluated_depsgraph_get()
            me = bpy.data.meshes.new_from_object(obj.evaluated_get(graph), depsgraph=graph)
        finally:
            obj.modifiers.remove(mod)
        me.transform(obj.matrix_world)
        v, closed = _volume(me)
        tol = 0.02 * max(v_obj, 1e-9) + 1e-6
        if op == 'DIFFERENCE':
            ok = closed and v_obj - v_oth - tol <= v <= v_obj + tol and v > 0
        elif op == 'UNION':
            ok = closed and max(v_obj, v_oth) - tol <= v <= v_obj + v_oth + tol
        else:
            ok = closed and 0 < v <= min(v_obj, v_oth) + tol
        if ok and len(me.polygons):
            _replace(obj, me)
            return obj
        bpy.data.meshes.remove(me)
    raise common.AddonError(f'La booleana ({op}) no dio un sólido válido con {obj.name}: se deja como estaba.')


def union(obj, other, delete_other=True):
    _bool(obj, other, 'UNION')
    if delete_other:
        _remove([other])
    return obj


def carve(obj, cutter, delete_cutter=True):
    """Resta (boca, orificios, cuencas)."""
    _bool(obj, cutter, 'DIFFERENCE')
    if delete_cutter:
        _remove([cutter])
    return obj


def colorize(obj, color='piel', name=None):
    """Material de color (nombre de PALETTE o RGBA). Sirve para separar por colores al imprimir."""
    rgba = PALETTE.get(color, color) if isinstance(color, str) else color
    mname = name or (color if isinstance(color, str) else 'color_%02x%02x%02x' % tuple(int(c * 255) for c in rgba[:3]))
    mat = bpy.data.materials.get(mname) or bpy.data.materials.new(mname)
    mat.diffuse_color = rgba
    if getattr(mat, 'use_nodes', False) and mat.node_tree:
        bsdf = mat.node_tree.nodes.get('Principled BSDF')
        if bsdf:
            bsdf.inputs['Base Color'].default_value = rgba
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return obj


def place_on_floor(objs):
    """Baja todo junto hasta Z=0 (la figura queda de pie en la cama)."""
    objs = objs if isinstance(objs, (list, tuple)) else [objs]
    zmin = min((o.matrix_world @ Vector(c)).z for o in objs for c in o.bound_box)
    for o in objs:
        o.location.z -= zmin
    return objs


def look(view='FRONT', objs=None):
    """Encuadra la Vista 3D (para hacer una captura): FRONT, BACK, LEFT, RIGHT, TOP, ISO."""
    rots = {'FRONT': (90, 0, 0), 'BACK': (90, 0, 180), 'RIGHT': (90, 0, 90), 'LEFT': (90, 0, -90),
            'TOP': (0, 0, 0), 'ISO': (65, 0, 35)}
    from mathutils import Euler
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            r3d = area.spaces.active.region_3d
            objs_ = objs or [o for o in bpy.context.scene.objects if o.type == 'MESH' and o.visible_get()]
            if objs_:
                pts = [o.matrix_world @ Vector(c) for o in objs_ for c in o.bound_box]
                lo = Vector([min(p[i] for p in pts) for i in range(3)])
                hi = Vector([max(p[i] for p in pts) for i in range(3)])
                r3d.view_location = (lo + hi) / 2
                r3d.view_distance = (hi - lo).length * 1.2
            r3d.view_rotation = Euler([math.radians(a) for a in rots[view]]).to_quaternion()
            r3d.view_perspective = 'ORTHO' if view != 'ISO' else 'PERSP'
            area.spaces.active.shading.type = 'SOLID'
            area.spaces.active.shading.color_type = 'MATERIAL'
            return True
    return False


def report(objs=None):
    """Medidas del conjunto y estado de cada pieza (cerrada o no)."""
    objs = objs or [o for o in bpy.context.scene.objects if o.type == 'MESH' and o.visible_get()]
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    size = [max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3)]
    parts = []
    for o in objs:
        bm = bmesh.new(); bm.from_mesh(o.data)
        closed = bool(bm.faces) and all(e.is_manifold for e in bm.edges)
        parts.append({'name': o.name, 'faces': len(o.data.polygons), 'closed': closed,
                      'color': o.material_slots[0].material.name if o.material_slots and o.material_slots[0].material else None})
        bm.free()
    return {'size_mm': [round(s, 1) for s in size], 'parts': parts}


def snapshot(path, views=('FRONT', 'ISO'), objs=None, size=900):
    """Imagen de la figura (render Workbench, funciona aunque Blender esté minimizado). Con varias
    vistas salen una al lado de otra en el mismo PNG. Devuelve la ruta."""
    sc = bpy.context.scene
    objs = list(objs or [o for o in sc.objects if o.type == 'MESH' and o.visible_get()])
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    center, span = (lo + hi) / 2, max((hi - lo).length, 1e-6)   # vale para escenas en mm o en metros
    dirs = {'FRONT': (0, -1, 0), 'BACK': (0, 1, 0), 'RIGHT': (1, 0, 0), 'LEFT': (-1, 0, 0),
            'TOP': (0, 0, 1), 'ISO': (0.8, -1.0, 0.65), 'ISO_BACK': (-0.8, 1.0, 0.65)}
    old = (sc.render.engine, sc.camera, sc.render.resolution_x, sc.render.resolution_y, sc.render.filepath,
           sc.render.film_transparent)
    cam = bpy.data.objects.new('_ok_cam', bpy.data.cameras.new('_ok_cam'))
    sc.collection.objects.link(cam)
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = span * 1.05
    cam.data.clip_start = span * 0.01
    cam.data.clip_end = span * 10
    sc.camera = cam
    sc.render.engine = 'BLENDER_WORKBENCH'
    sh = sc.display.shading
    keep = {k: getattr(sh, k) for k in ('light', 'color_type', 'show_cavity', 'show_shadows', 'show_xray',
                                         'show_object_outline', 'background_type') if hasattr(sh, k)}
    sh.light = 'STUDIO'; sh.color_type = 'MATERIAL'; sh.show_cavity = False; sh.show_shadows = False
    if hasattr(sh, 'show_xray'):
        sh.show_xray = False
    sc.render.resolution_x = sc.render.resolution_y = size
    sc.render.film_transparent = False
    import os
    import tempfile
    tiles = []
    # solo salen en la foto las piezas pedidas (lo oculto en la vista también se renderiza si no)
    hidden = [o for o in sc.objects if o not in objs and o is not cam and not o.hide_render]
    for o in hidden:
        o.hide_render = True
    try:
        for v in views:
            d = Vector(dirs[v]).normalized()
            cam.location = center + d * span * 2
            q = (-d).to_track_quat('-Z', 'Y')
            if v == 'TOP':                       # desde arriba: delante (-Y) abajo en la imagen
                from mathutils import Euler
                q = Euler((0, 0, 0)).to_quaternion()
            cam.rotation_euler = q.to_euler()
            tmp = os.path.join(tempfile.gettempdir(), f'_ok_{v}.png')
            sc.render.filepath = tmp
            bpy.ops.render.render(write_still=True)
            tiles.append(tmp)
    finally:
        (sc.render.engine, sc.camera, sc.render.resolution_x, sc.render.resolution_y, sc.render.filepath,
         sc.render.film_transparent) = old
        for k, val in keep.items():
            try:
                setattr(sh, k, val)
            except Exception:
                pass
        for o in hidden:
            if o.name in bpy.data.objects:
                o.hide_render = False
        _remove([cam])
    imgs = [bpy.data.images.load(t) for t in tiles]
    w = sum(i.size[0] for i in imgs); h = max(i.size[1] for i in imgs)
    out = np.zeros((h, w, 4), np.float32); x = 0
    for i in imgs:
        px = np.empty(i.size[0] * i.size[1] * 4, np.float32); i.pixels.foreach_get(px)
        out[:i.size[1], x:x + i.size[0]] = px.reshape(i.size[1], i.size[0], 4); x += i.size[0]
        bpy.data.images.remove(i)
    res = bpy.data.images.new('_ok_snapshot', w, h, alpha=True)
    res.pixels.foreach_set(out.ravel())
    res.filepath_raw = path
    res.file_format = 'PNG'
    res.save()
    bpy.data.images.remove(res)
    return path
