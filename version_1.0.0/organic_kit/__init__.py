# SPDX-FileCopyrightText: 2026 Ricardo Lugaresi
# SPDX-License-Identifier: GPL-3.0-or-later

bl_info = {'name': 'Organic Kit', 'author': 'Ricardo Lugaresi', 'version': (1, 0, 0),
           'blender': (4, 2, 0), 'location': 'Vista 3D > N > Organic Kit',
           'description': 'Figuras orgánicas con código o con un clic: chibis anime, criaturas, pelo, ojos y '
                          'herramientas de escultor (fundir, alisar, simetría). Pensado también para agentes por MCP',
           'category': 'Object'}

import bpy

from . import common, kit, recipes

HAIR_ITEMS = [('SPIKY', 'Puntas', 'Mechones de punta, estilo shonen'), ('SOFT', 'Suave', 'Mechones que caen'),
              ('BANGS', 'Flequillo', 'Con flequillo delante'), ('NONE', 'Sin pelo', '')]
EAR_ITEMS = [('NONE', 'Normales', ''), ('CAT', 'Gato', ''), ('ELF', 'Elfo', ''), ('ROUND', 'Oso', '')]


class OrganicProps(bpy.types.PropertyGroup):
    height: bpy.props.FloatProperty(name='Alto (mm)', default=80, min=20, max=400, precision=0)
    hair: bpy.props.EnumProperty(name='Pelo', items=HAIR_ITEMS, default='SPIKY')
    ears: bpy.props.EnumProperty(name='Orejas', items=EAR_ITEMS, default='NONE')
    tail: bpy.props.BoolProperty(name='Cola', default=False)
    chubby: bpy.props.FloatProperty(name='Rellenito', default=1.0, min=0.7, max=1.5, precision=2)
    hair_color: bpy.props.FloatVectorProperty(name='Color del pelo', subtype='COLOR', size=4, min=0, max=1,
                                              default=kit.PALETTE['pelo'])
    iris_color: bpy.props.FloatVectorProperty(name='Color de ojos', subtype='COLOR', size=4, min=0, max=1,
                                              default=kit.PALETTE['iris'])
    seed: bpy.props.IntProperty(name='Variante de pelo', default=1, min=1, max=999)
    smooth_iter: bpy.props.IntProperty(name='Pasadas', default=5, min=1, max=50)
    inflate_mm: bpy.props.FloatProperty(name='mm', default=0.5, min=-5, max=5, precision=2)
    done: bpy.props.StringProperty(default='')


def _meshes(context):
    return [o for o in context.selected_objects if o.type == 'MESH']


def _wrap(op, fn):
    try:
        return fn()
    except common.AddonError as exc:
        op.report({'ERROR'}, str(exc))
        return None


class OBJECT_OT_organic_chibi(bpy.types.Operator):
    """Crea un personaje chibi por piezas de color (cuerpo, pelo, ojos)"""
    bl_idname = 'object.organic_chibi'; bl_label = 'Crear chibi'; bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return common.poll_object_mode(cls, context)

    def execute(self, context):
        p = context.scene.organic_props
        parts = _wrap(self, lambda: recipes.chibi('Chibi', p.height, p.hair, p.ears, p.tail, p.chubby,
                                                  hair_color=tuple(p.hair_color), iris_color=tuple(p.iris_color),
                                                  seed=p.seed))
        if parts is None:
            return {'CANCELLED'}
        for o in context.selected_objects:
            o.select_set(False)
        for o in parts.values():
            o.select_set(True)
        context.view_layer.objects.active = parts['cuerpo']
        p.done = f'Chibi de {p.height:.0f} mm en {len(parts)} piezas de color'
        self.report({'INFO'}, p.done)
        return {'FINISHED'}


class OBJECT_OT_organic_fuse(bpy.types.Operator):
    """Funde las mallas seleccionadas en un solo sólido cerrado"""
    bl_idname = 'object.organic_fuse'; bl_label = 'Fundir en un sólido'; bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return common.poll_object_mode(cls, context) and len(_meshes(context)) >= 1

    def execute(self, context):
        objs = _meshes(context)
        out = _wrap(self, lambda: kit.fuse(objs, objs[0].name + '_fundido'))
        if out is None:
            return {'CANCELLED'}
        out.select_set(True); context.view_layer.objects.active = out
        return {'FINISHED'}


class OBJECT_OT_organic_smooth(bpy.types.Operator):
    """Alisa sin encoger"""
    bl_idname = 'object.organic_smooth'; bl_label = 'Alisar'; bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return common.poll_object_mode(cls, context) and bool(_meshes(context))

    def execute(self, context):
        for o in _meshes(context):
            kit.smooth(o, context.scene.organic_props.smooth_iter)
        return {'FINISHED'}


class OBJECT_OT_organic_inflate(bpy.types.Operator):
    """Engorda (o adelgaza con valores negativos)"""
    bl_idname = 'object.organic_inflate'; bl_label = 'Engordar'; bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return common.poll_object_mode(cls, context) and bool(_meshes(context))

    def execute(self, context):
        for o in _meshes(context):
            kit.inflate(o, context.scene.organic_props.inflate_mm)
        return {'FINISHED'}


class OBJECT_OT_organic_mirror(bpy.types.Operator):
    """Copia la mitad derecha a la izquierda (simetría en X)"""
    bl_idname = 'object.organic_mirror'; bl_label = 'Simetría X'; bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return common.poll_object_mode(cls, context) and bool(_meshes(context))

    def execute(self, context):
        for o in _meshes(context):
            kit.mirror_x(o)
        return {'FINISHED'}


class OBJECT_OT_organic_floor(bpy.types.Operator):
    """Baja las piezas seleccionadas juntas hasta la cama (Z = 0)"""
    bl_idname = 'object.organic_floor'; bl_label = 'Al suelo'; bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return common.poll_object_mode(cls, context) and bool(_meshes(context))

    def execute(self, context):
        kit.place_on_floor(_meshes(context))
        return {'FINISHED'}


class VIEW3D_PT_organic(bpy.types.Panel):
    bl_label = 'Organic Kit'; bl_idname = 'VIEW3D_PT_organic'; bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'; bl_category = 'Organic Kit'

    def draw(self, context):
        layout = self.layout; p = context.scene.organic_props
        layout.use_property_split = True; layout.use_property_decorate = False
        if common.draw_mode_warning(layout, context):
            return
        box = layout.box()
        box.label(text='Personaje chibi', icon='OUTLINER_OB_ARMATURE')
        for k in ('height', 'hair', 'ears', 'tail', 'chubby', 'hair_color', 'iris_color', 'seed'):
            box.prop(p, k)
        col = box.column(); col.scale_y = 1.5
        col.operator('object.organic_chibi', icon='USER')
        if p.done:
            box.label(text=p.done)
        box = layout.box()
        box.label(text='Escultor (piezas seleccionadas)', icon='SCULPTMODE_HLT')
        box.operator('object.organic_fuse', icon='META_BALL')
        row = box.row(align=True)
        row.operator('object.organic_smooth', icon='MOD_SMOOTH'); row.prop(p, 'smooth_iter', text='')
        row = box.row(align=True)
        row.operator('object.organic_inflate', icon='MOD_CAST'); row.prop(p, 'inflate_mm', text='')
        row = box.row(align=True)
        row.operator('object.organic_mirror', icon='MOD_MIRROR'); row.operator('object.organic_floor', icon='TRIA_DOWN_BAR')
        layout.label(text='Agente: import organic_kit.kit as ok', icon='CONSOLE')


classes = (OrganicProps, OBJECT_OT_organic_chibi, OBJECT_OT_organic_fuse, OBJECT_OT_organic_smooth,
           OBJECT_OT_organic_inflate, OBJECT_OT_organic_mirror, OBJECT_OT_organic_floor, VIEW3D_PT_organic)


def register():
    common.register_classes(classes, 'organic_props', OrganicProps)


def unregister():
    common.unregister_classes(classes, 'organic_props')
