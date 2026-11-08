# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

bl_info = {
    "name": "three.js format",
    "author": "mrdoob, kikko, alteredq, remoe, pxf, n3tfr34k, crobi",
    "version": (1, 6, 0),
    "blender": (2, 92, 0),
    "location": "File > Import-Export",
    "description": "Import-Export three.js meshes",
    "warning": "",
    "wiki_url": "https://github.com/mrdoob/three.js/tree/master/utils/exporters/blender",
    "tracker_url": "https://github.com/mrdoob/three.js/issues",
    "category": "Import-Export"}

# Support "Reload Scripts"
if "bpy" in locals():
    import importlib
    if "import_threejs" in locals():
        importlib.reload(import_threejs)
    if "export_threejs" in locals():
        importlib.reload(export_threejs)

import os
import json

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import import_threejs
from . import export_threejs

# ################################################################
# Custom property definitions (registered in register())
# ################################################################

THREE_material_types = [("Basic", "Basic", "Basic"), ("Phong", "Phong", "Phong"), ("Lambert", "Lambert", "Lambert")]

THREE_blending_types = [("NoBlending", "NoBlending", "NoBlending"),
                        ("NormalBlending", "NormalBlending", "NormalBlending"),
                        ("AdditiveBlending", "AdditiveBlending", "AdditiveBlending"),
                        ("SubtractiveBlending", "SubtractiveBlending", "SubtractiveBlending"),
                        ("MultiplyBlending", "MultiplyBlending", "MultiplyBlending"),
                        ("AdditiveAlphaBlending", "AdditiveAlphaBlending", "AdditiveAlphaBlending")]


def register_properties():
    bpy.types.Object.THREE_castShadow = BoolProperty()
    bpy.types.Object.THREE_receiveShadow = BoolProperty()
    bpy.types.Object.THREE_doubleSided = BoolProperty()
    bpy.types.Object.THREE_exportGeometry = BoolProperty(default=True)
    bpy.types.Object.THREE_visible = BoolProperty(default=True)

    bpy.types.Material.THREE_useVertexColors = BoolProperty()
    bpy.types.Material.THREE_depthWrite = BoolProperty(default=True)
    bpy.types.Material.THREE_depthTest = BoolProperty(default=True)
    bpy.types.Material.THREE_materialType = EnumProperty(
        name="Material type", description="Material type",
        items=THREE_material_types, default="Lambert")
    bpy.types.Material.THREE_blendingType = EnumProperty(
        name="Blending type", description="Blending type",
        items=THREE_blending_types, default="NormalBlending")


def unregister_properties():
    for name in ("THREE_castShadow", "THREE_receiveShadow", "THREE_doubleSided",
                 "THREE_exportGeometry", "THREE_visible"):
        delattr(bpy.types.Object, name)
    for name in ("THREE_useVertexColors", "THREE_depthWrite", "THREE_depthTest",
                 "THREE_materialType", "THREE_blendingType"):
        delattr(bpy.types.Material, name)


class OBJECT_PT_hello(bpy.types.Panel):

    bl_label = "THREE"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def draw(self, context):
        layout = self.layout
        obj = context.object

        layout.label(text="Selected object: " + obj.name)
        layout.prop(obj, "THREE_exportGeometry", text="Export geometry")
        layout.prop(obj, "THREE_castShadow", text="Casts shadow")
        layout.prop(obj, "THREE_receiveShadow", text="Receives shadow")
        layout.prop(obj, "THREE_doubleSided", text="Double sided")
        layout.prop(obj, "THREE_visible", text="Visible")


class MATERIAL_PT_hello(bpy.types.Panel):

    bl_label = "THREE"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"

    @classmethod
    def poll(cls, context):
        return context.material is not None

    def draw(self, context):
        layout = self.layout
        mat = context.material

        layout.label(text="Selected material: " + mat.name)
        layout.prop(mat, "THREE_materialType", text="Material type")
        layout.prop(mat, "THREE_blendingType", text="Blending type")
        layout.prop(mat, "THREE_useVertexColors", text="Use vertex colors")
        layout.prop(mat, "THREE_depthWrite", text="Enable depth writing")
        layout.prop(mat, "THREE_depthTest", text="Enable depth testing")


# ################################################################
# Importer
# ################################################################

class ImportTHREEJS(bpy.types.Operator, ImportHelper):
    '''Load a Three.js ASCII JSON model'''

    bl_idname = "import.threejs"
    bl_label = "Import Three.js"

    filename_ext = ".js"
    filter_glob: StringProperty(default="*.js", options={'HIDDEN'})

    option_flip_yz: BoolProperty(name="Flip YZ", description="Flip YZ", default=True)
    recalculate_normals: BoolProperty(name="Recalculate normals", description="Recalculate vertex normals", default=True)
    option_worker: BoolProperty(name="Worker", description="Old format using workers", default=False)

    def execute(self, context):
        keywords = self.as_keywords(ignore=("filter_glob",))
        return import_threejs.load(self, context, **keywords)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "option_flip_yz")
        layout.prop(self, "recalculate_normals")
        layout.prop(self, "option_worker")


# ################################################################
# Exporter - settings
# ################################################################

SETTINGS_FILE_EXPORT = "threejs_settings_export.js"

SETTINGS_KEYS = {
    "option_export_scene": False,
    "option_embed_meshes": True,
    "option_url_base_html": False,
    "option_copy_textures": False,

    "option_lights": False,
    "option_cameras": False,

    "option_animation_morph": False,
    "option_animation_skeletal": False,
    "option_frame_index_as_time": False,

    "option_frame_step": 1,
    "option_all_meshes": True,

    "option_flip_yz": True,

    "option_materials": True,
    "option_normals": True,
    "option_colors": True,
    "option_uv_coords": True,
    "option_faces": True,
    "option_vertices": True,

    "option_skinning": True,
    "option_bones": True,

    "option_vertices_truncate": False,
    "option_scale": 1.0,

    "align_model": "None",
}


def get_settings_fullpath():
    return os.path.join(bpy.app.tempdir, SETTINGS_FILE_EXPORT)


def save_settings_export(properties):
    settings = dict((key, getattr(properties, key)) for key in SETTINGS_KEYS)
    try:
        with open(get_settings_fullpath(), "w") as f:
            json.dump(settings, f)
    except (IOError, OSError):
        pass


def restore_settings_export(properties):
    settings = {}
    try:
        with open(get_settings_fullpath(), "r") as f:
            settings = json.load(f)
    except (IOError, OSError, ValueError):
        pass

    for key, default in SETTINGS_KEYS.items():
        try:
            setattr(properties, key, settings.get(key, default))
        except (TypeError, ValueError):
            pass


# ################################################################
# Exporter
# ################################################################

class ExportTHREEJS(bpy.types.Operator, ExportHelper):
    '''Export selected object / scene for Three.js (ASCII JSON format).'''

    bl_idname = "export.threejs"
    bl_label = "Export Three.js"

    filename_ext = ".js"
    filter_glob: StringProperty(default="*.js", options={'HIDDEN'})

    option_vertices: BoolProperty(name="Vertices", description="Export vertices", default=True)
    option_vertices_deltas: BoolProperty(name="Deltas", description="Delta vertices", default=False)
    option_vertices_truncate: BoolProperty(name="Truncate", description="Truncate vertices", default=False)

    option_faces: BoolProperty(name="Faces", description="Export faces", default=True)
    option_faces_deltas: BoolProperty(name="Deltas", description="Delta faces", default=False)

    option_normals: BoolProperty(name="Normals", description="Export normals", default=True)

    option_colors: BoolProperty(name="Colors", description="Export vertex colors", default=True)
    option_uv_coords: BoolProperty(name="UVs", description="Export texture coordinates", default=True)
    option_materials: BoolProperty(name="Materials", description="Export materials", default=True)

    option_skinning: BoolProperty(name="Skinning", description="Export skin data", default=True)
    option_bones: BoolProperty(name="Bones", description="Export bones", default=True)

    align_types = [("None", "None", "None"), ("Center", "Center", "Center"),
                   ("Bottom", "Bottom", "Bottom"), ("Top", "Top", "Top")]
    align_model: EnumProperty(name="Align model", description="Align model", items=align_types, default="None")

    option_scale: FloatProperty(name="Scale", description="Scale vertices", min=0.01, max=1000.0,
                                soft_min=0.01, soft_max=1000.0, default=1.0)
    option_flip_yz: BoolProperty(name="Flip YZ", description="Flip YZ", default=True)

    option_export_scene: BoolProperty(name="Scene", description="Export scene", default=False)
    option_embed_meshes: BoolProperty(name="Embed meshes", description="Embed meshes", default=True)
    option_copy_textures: BoolProperty(name="Copy textures", description="Copy textures", default=False)
    option_url_base_html: BoolProperty(name="HTML as url base", description="Use HTML as url base ", default=False)

    option_lights: BoolProperty(name="Lights", description="Export default scene lights", default=False)
    option_cameras: BoolProperty(name="Cameras", description="Export default scene cameras", default=False)

    option_animation_morph: BoolProperty(name="Morph animation", description="Export animation (morphs)", default=False)
    option_animation_skeletal: BoolProperty(name="Skeletal animation", description="Export animation (skeletal)", default=False)
    option_frame_index_as_time: BoolProperty(name="Frame index as time", description="Use (original) frame index as frame time", default=False)

    option_frame_step: IntProperty(name="Frame step", description="Animation frame step", min=1, max=1000,
                                   soft_min=1, soft_max=1000, default=1)
    option_all_meshes: BoolProperty(name="All meshes", description="All meshes (merged)", default=True)

    def invoke(self, context, event):
        restore_settings_export(self)
        return ExportHelper.invoke(self, context, event)

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        print("Selected: " + context.active_object.name)

        if not self.filepath:
            raise Exception("filename not set")

        save_settings_export(self)

        keywords = self.as_keywords(ignore=("filter_glob", "check_existing"))
        return export_threejs.save(self, context, **keywords)

    def draw(self, context):
        layout = self.layout

        layout.label(text="Geometry:")

        row = layout.row()
        row.prop(self, "option_vertices")
        row.prop(self, "option_vertices_truncate")
        layout.separator()

        layout.prop(self, "option_faces")
        layout.separator()

        layout.prop(self, "option_normals")
        layout.separator()

        row = layout.row()
        row.prop(self, "option_bones")
        row.prop(self, "option_skinning")
        layout.separator()

        layout.label(text="Materials:")

        row = layout.row()
        row.prop(self, "option_uv_coords")
        row.prop(self, "option_colors")
        layout.prop(self, "option_materials")
        layout.separator()

        layout.label(text="Settings:")

        layout.prop(self, "align_model")
        row = layout.row()
        row.prop(self, "option_flip_yz")
        row.prop(self, "option_scale")
        layout.separator()

        layout.label(text="--------- Experimental ---------")
        layout.separator()

        layout.label(text="Scene:")

        row = layout.row()
        row.prop(self, "option_export_scene")
        row.prop(self, "option_embed_meshes")

        row = layout.row()
        row.prop(self, "option_lights")
        row.prop(self, "option_cameras")
        layout.separator()

        layout.label(text="Animation:")

        layout.prop(self, "option_animation_morph")
        layout.prop(self, "option_animation_skeletal")
        layout.prop(self, "option_frame_index_as_time")
        layout.prop(self, "option_frame_step")
        layout.separator()

        layout.label(text="Settings:")

        layout.prop(self, "option_all_meshes")
        layout.prop(self, "option_copy_textures")
        layout.prop(self, "option_url_base_html")
        layout.separator()


# ################################################################
# Common
# ################################################################

def menu_func_export(self, context):
    default_path = bpy.data.filepath.replace(".blend", ".js")
    self.layout.operator(ExportTHREEJS.bl_idname, text="Three.js (.js)").filepath = default_path


def menu_func_import(self, context):
    self.layout.operator(ImportTHREEJS.bl_idname, text="Three.js (.js)")


classes = (
    OBJECT_PT_hello,
    MATERIAL_PT_hello,
    ImportTHREEJS,
    ExportTHREEJS,
)


def register():
    register_properties()
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    unregister_properties()


if __name__ == "__main__":
    register()
