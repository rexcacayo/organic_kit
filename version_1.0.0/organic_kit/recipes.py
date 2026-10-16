# SPDX-FileCopyrightText: 2026 Ricardo Lugaresi
# SPDX-License-Identifier: GPL-3.0-or-later

"""Recetas: figuras completas de partida que el agente (o tú) luego retoca.

chibi()  personaje estilo anime chibi (cabeza grande, 2,4 cabezas de alto) con pelo, ojos, orejas
         y cola opcionales. Sale por piezas de color: cuerpo (piel), pelo, blancos, iris, brillos.
"""
from mathutils import Vector

from . import kit


def chibi(name='Chibi', height=80.0, hair='SPIKY', ears='NONE', tail=False, chubby=1.0,
          hair_color='pelo', skin_color='piel', iris_color='iris', clean_overlaps=True, seed=1):
    H = float(height)
    R = H / 2.4 / 2.0                         # radio de la cabeza
    hc = Vector((0, 0, H - R))                # centro de la cabeza
    c = chubby
    neck_z = H - 2 * R + 0.03 * H
    joints = {
        'pelvis': (0, 0, 0.30 * H), 'pecho': (0, 0, 0.44 * H), 'cuello': (0, 0, neck_z),
        'hombro_d': (0.11 * H, 0, 0.46 * H), 'codo_d': (0.17 * H, 0.01 * H, 0.38 * H), 'mano_d': (0.19 * H, -0.01 * H, 0.31 * H),
        'hombro_i': (-0.11 * H, 0, 0.46 * H), 'codo_i': (-0.17 * H, 0.01 * H, 0.38 * H), 'mano_i': (-0.19 * H, -0.01 * H, 0.31 * H),
        'cadera_d': (0.055 * H, 0, 0.27 * H), 'rodilla_d': (0.065 * H, -0.005 * H, 0.15 * H), 'tobillo_d': (0.07 * H, 0, 0.05 * H),
        'cadera_i': (-0.055 * H, 0, 0.27 * H), 'rodilla_i': (-0.065 * H, -0.005 * H, 0.15 * H), 'tobillo_i': (-0.07 * H, 0, 0.05 * H),
    }
    bones = [('pelvis', 'pecho'), ('pecho', 'cuello'),
             ('pecho', 'hombro_d'), ('hombro_d', 'codo_d'), ('codo_d', 'mano_d'),
             ('pecho', 'hombro_i'), ('hombro_i', 'codo_i'), ('codo_i', 'mano_i'),
             ('pelvis', 'cadera_d'), ('cadera_d', 'rodilla_d'), ('rodilla_d', 'tobillo_d'),
             ('pelvis', 'cadera_i'), ('cadera_i', 'rodilla_i'), ('rodilla_i', 'tobillo_i')]
    radii = {'pelvis': (0.085 * H * c, 0.07 * H * c), 'pecho': (0.08 * H * c, 0.065 * H * c), 'cuello': 0.032 * H,
             'hombro_d': 0.036 * H * c, 'codo_d': 0.028 * H * c, 'mano_d': 0.026 * H,
             'hombro_i': 0.036 * H * c, 'codo_i': 0.028 * H * c, 'mano_i': 0.026 * H,
             'cadera_d': 0.045 * H * c, 'rodilla_d': 0.036 * H * c, 'tobillo_d': 0.032 * H,
             'cadera_i': 0.045 * H * c, 'rodilla_i': 0.036 * H * c, 'tobillo_i': 0.032 * H}
    body = kit.skin_body(f'{name}_esqueleto', joints, bones, radii, subdiv=2)
    head = kit.blobs(f'{name}_cabeza', [
        {'at': tuple(hc), 'r': R, 'type': 'ELLIPSOID', 'scale': (1.0, 0.95, 0.93)},
        {'at': tuple(hc + Vector((0.36 * R, -0.42 * R, -0.3 * R))), 'r': 0.5 * R},      # mofletes
        {'at': tuple(hc + Vector((-0.36 * R, -0.42 * R, -0.3 * R))), 'r': 0.5 * R},
        {'at': tuple(hc + Vector((0, -0.35 * R, -0.5 * R))), 'r': 0.5 * R},             # barbilla
    ])
    extras = kit.blobs(f'{name}_manos_pies', [
        {'at': joints['mano_d'], 'r': 0.042 * H},
        {'at': joints['mano_i'], 'r': 0.042 * H},
        {'at': (0.07 * H, -0.025 * H, 0.032 * H), 'r': 0.055 * H, 'type': 'ELLIPSOID', 'scale': (0.75, 1.3, 0.55)},
        {'at': (-0.07 * H, -0.025 * H, 0.032 * H), 'r': 0.055 * H, 'type': 'ELLIPSOID', 'scale': (0.75, 1.3, 0.55)},
    ])
    pieces = [body, head, extras]
    if ears != 'NONE':
        pieces.append(kit.ears(f'{name}_orejas', hc, R, ears))
    if tail:
        base = Vector((0, 0.07 * H, 0.30 * H))
        pieces.append(kit.tube(f'{name}_cola', [tuple(base), tuple(base + Vector((0, 0.12 * H, 0.02 * H))),
                                               tuple(base + Vector((0, 0.18 * H, 0.15 * H))),
                                               tuple(base + Vector((0, 0.14 * H, 0.26 * H)))],
                               [0.03 * H, 0.028 * H, 0.022 * H, max(kit.TIP, 0.012 * H)]))
    skin = kit.fuse(pieces, f'{name}_cuerpo')
    kit.colorize(skin, skin_color)
    parts = {'cuerpo': skin}
    # ojos (cara hacia -Y)
    eye_z = hc.z - 0.12 * R
    face = Vector((0, -0.9 * R, eye_z))
    W, I, S = kit.eyes(f'{name}_ojos', tuple(face), eye_z, spacing=0.8 * R, size=0.36 * R, depth=0.2 * R)
    kit.colorize(I, iris_color)
    parts.update({'blancos': W, 'iris': I, 'brillos': S})
    # pelo
    if hair != 'NONE':
        # casco de pelo: elipsoide algo mayor que la cabeza, con la cara y la nuca recortadas
        cap = kit.blobs(f'{name}_casco', [
            {'at': tuple(hc + Vector((0, 0.06 * R, 0.1 * R))), 'r': 1.07 * R, 'type': 'ELLIPSOID', 'scale': (1.0, 1.0, 0.97)}])
        window = kit.blobs(f'{name}_ventana', [
            {'at': tuple(hc + Vector((0, -0.95 * R, -0.3 * R))), 'r': 1.0 * R, 'type': 'ELLIPSOID', 'scale': (0.95, 1.0, 0.85)},
            {'at': tuple(hc + Vector((0, 0.2 * R, -1.25 * R))), 'r': 0.95 * R}])
        kit.carve(cap, window)
        spikes = kit.hair_spikes(f'{name}_mechones', tuple(hc), R * 1.0, count=14 if hair == 'SPIKY' else 18,
                                 length=R * (0.85 if hair == 'SPIKY' else 0.7), thickness=R * 0.3,
                                 style=hair, seed=seed)
        hair_obj = kit.fuse([cap, spikes], f'{name}_pelo', voxel=max(0.15, R / 45))
        kit.colorize(hair_obj, hair_color)
        parts['pelo'] = hair_obj
    if clean_overlaps:
        # cada color, su volumen: el cuerpo deja hueco a ojos y pelo (imprimir por colores sin solapes)
        for key in ('blancos', 'iris', 'pelo'):
            if key in parts:
                cutter = parts[key].copy(); cutter.data = parts[key].data.copy()
                kit._collection().objects.link(cutter)
                try:
                    kit.carve(parts['cuerpo'], cutter)
                except Exception:
                    kit._remove([cutter])
        for key in ('iris', 'brillos'):
            under = 'blancos' if key == 'iris' else 'iris'
            cutter = parts[key].copy(); cutter.data = parts[key].data.copy()
            kit._collection().objects.link(cutter)
            try:
                kit.carve(parts[under], cutter)
            except Exception:
                kit._remove([cutter])
    kit.place_on_floor(list(parts.values()))
    return parts
