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

"""
Blender exporter for Three.js (ASCII JSON format). Blender 2.92+.

TODO
    - binary format
"""

import bpy
import bmesh
import mathutils

import shutil
import os
import os.path
import math
import operator
import random

# #####################################################
# Configuration
# #####################################################

DEFAULTS = {
"bgcolor" : [0, 0, 0],
"bgalpha" : 1.0,

"position" : [0, 0, 0],
"rotation" : [0, 0, 0],
"scale"    : [1, 1, 1],

"camera"  :
    {
        "name" : "default_camera",
        "type" : "PerspectiveCamera",
        "near" : 1,
        "far"  : 10000,
        "fov"  : 60,
        "aspect": 1.333,
        "position" : [0, 0, 10],
        "target"   : [0, 0, 0]
    },

"light" :
 {
    "name"       : "default_light",
    "type"       : "DirectionalLight",
    "direction"  : [0, 1, 1],
    "color"      : [1, 1, 1],
    "intensity"  : 0.8
 }
}

ROTATE_X_PI2 = mathutils.Quaternion((1.0, 0.0, 0.0), math.radians(-90.0)).to_matrix().to_4x4()

# default colors for debugging (each material gets one distinct color):
# white, red, green, blue, yellow, cyan, magenta
COLORS = [0xeeeeee, 0xee0000, 0x00ee00, 0x0000ee, 0xeeee00, 0x00eeee, 0xee00ee]

# skinning
MAX_INFLUENCES = 2

# Blender 2.8+ lights use Watts (point default: 1000 W), three.js uses ~1.0
LIGHT_POWER_SCALE = 0.001

ALIGN_MODES = {"None": 0, "Center": 1, "Bottom": 2, "Top": 3}

TEXTURE_SLOTS = ('diffuse', 'light', 'normal', 'specular', 'bump')

# #####################################################
# Templates - scene
# #####################################################

TEMPLATE_SCENE_ASCII = """\
{

"metadata" :
{
	"formatVersion" : 3.2,
	"type"          : "scene",
	"sourceFile"    : "%(fname)s",
	"generatedBy"   : "Blender 2.9 Exporter",
	"objects"       : %(nobjects)s,
	"geometries"    : %(ngeometries)s,
	"materials"     : %(nmaterials)s,
	"textures"      : %(ntextures)s
},

"urlBaseType" : %(basetype)s,

%(sections)s

"transform" :
{
	"position"  : %(position)s,
	"rotation"  : %(rotation)s,
	"scale"     : %(scale)s
},

"defaults" :
{
	"bgcolor" : %(bgcolor)s,
	"bgalpha" : %(bgalpha)f,
	"camera"  : %(defcamera)s
}

}
"""

TEMPLATE_SECTION = """
"%s" :
{
%s
},
"""

TEMPLATE_OBJECT = """\
	%(object_id)s : {
		"geometry"  : %(geometry_id)s,
		"groups"    : [ %(group_id)s ],
		"material"  : %(material_id)s,
		"position"  : %(position)s,
		"rotation"  : %(rotation)s,
		"quaternion": %(quaternion)s,
		"scale"     : %(scale)s,
		"visible"       : %(visible)s,
		"castShadow"    : %(castShadow)s,
		"receiveShadow" : %(receiveShadow)s,
		"doubleSided"   : %(doubleSided)s
	}"""

TEMPLATE_EMPTY = """\
	%(object_id)s : {
		"groups"    : [ %(group_id)s ],
		"position"  : %(position)s,
		"rotation"  : %(rotation)s,
		"quaternion": %(quaternion)s,
		"scale"     : %(scale)s
	}"""

TEMPLATE_GEOMETRY_LINK = """\
	%(geometry_id)s : {
		"type" : "ascii",
		"url"  : %(model_file)s
	}"""

TEMPLATE_GEOMETRY_EMBED = """\
	%(geometry_id)s : {
		"type" : "embedded",
		"id"  : %(embed_id)s
	}"""

TEMPLATE_TEXTURE = """\
	%(texture_id)s : {
		"url": %(texture_file)s%(extras)s
	}"""

TEMPLATE_MATERIAL_SCENE = """\
	%(material_id)s : {
		"type": %(type)s,
		"parameters": { %(parameters)s }
	}"""

TEMPLATE_CAMERA_PERSPECTIVE = """\
	%(camera_id)s : {
		"type"  : "PerspectiveCamera",
		"fov"   : %(fov)f,
		"aspect": %(aspect)f,
		"near"  : %(near)f,
		"far"   : %(far)f,
		"position": %(position)s,
		"target"  : %(target)s
	}"""

TEMPLATE_CAMERA_ORTHO = """\
	%(camera_id)s : {
		"type"  : "OrthographicCamera",
		"left"  : %(left)f,
		"right" : %(right)f,
		"top"   : %(top)f,
		"bottom": %(bottom)f,
		"near"  : %(near)f,
		"far"   : %(far)f,
		"position": %(position)s,
		"target"  : %(target)s
	}"""

TEMPLATE_LIGHT_POINT = """\
	%(light_id)s : {
		"type"       : "PointLight",
		"position"   : %(position)s,
		"rotation"   : %(rotation)s,
		"color"      : %(color)d,
		"distance"   : %(distance).3f,
		"intensity"  : %(intensity).3f
	}"""

TEMPLATE_LIGHT_SUN = """\
	%(light_id)s : {
		"type"       : "AmbientLight",
		"position"   : %(position)s,
		"rotation"   : %(rotation)s,
		"color"      : %(color)d,
		"distance"   : %(distance).3f,
		"intensity"  : %(intensity).3f
	}"""

TEMPLATE_LIGHT_SPOT = """\
	%(light_id)s : {
		"type"       : "SpotLight",
		"position"   : %(position)s,
		"rotation"   : %(rotation)s,
		"color"      : %(color)d,
		"distance"   : %(distance).3f,
		"intensity"  : %(intensity).3f,
		"use_shadow" : %(use_shadow)d,
		"angle"      : %(angle).3f
	}"""

TEMPLATE_LIGHT_AREA = """\
	%(light_id)s : {
		"type"       : "AreaLight",
		"position"   : %(position)s,
		"rotation"   : %(rotation)s,
		"color"      : %(color)d,
		"distance"   : %(distance).3f,
		"intensity"  : %(intensity).3f,
		"gamma"      : %(gamma).3f,
		"shape"      : "%(shape)s",
		"size"       : %(size).3f,
		"size_y"     : %(size_y).3f
	}"""


TEMPLATE_VEC4 = '[ %g, %g, %g, %g ]'
TEMPLATE_VEC3 = '[ %g, %g, %g ]'
TEMPLATE_VEC2 = '[ %g, %g ]'
TEMPLATE_STRING = '"%s"'
TEMPLATE_HEX = "0x%06x"

# #####################################################
# Templates - model
# #####################################################

TEMPLATE_FILE_ASCII = """\
{

	"metadata" :
	{
		"formatVersion" : 3.1,
		"generatedBy"   : "Blender 2.9 Exporter",
		"vertices"      : %(nvertex)d,
		"faces"         : %(nface)d,
		"normals"       : %(nnormal)d,
		"colors"        : %(ncolor)d,
		"uvs"           : [%(nuvs)s],
		"materials"     : %(nmaterial)d,
		"morphTargets"  : %(nmorphTarget)d,
		"bones"         : %(nbone)d
	},

%(model)s

}
"""

TEMPLATE_MODEL_ASCII = """\
	"scale" : %(scale)f,

	"materials" : [%(materials)s],

	"vertices" : [%(vertices)s],

	"morphTargets" : [%(morphTargets)s],

	"normals" : [%(normals)s],

	"colors" : [%(colors)s],

	"uvs" : [%(uvs)s],

	"faces" : [%(faces)s],

	"bones" : [%(bones)s],

	"skinIndices" : [%(indices)s],

	"skinWeights" : [%(weights)s],

  "animations" : [%(animations)s]
"""

TEMPLATE_VERTEX = "%g,%g,%g"
TEMPLATE_VERTEX_TRUNCATE = "%d,%d,%d"

TEMPLATE_N = "%g,%g,%g"
TEMPLATE_UV = "%g,%g"
TEMPLATE_C = "%d"

# #####################################################
# Utils
# #####################################################

def veckey3(x,y,z):
    return round(x, 6), round(y, 6), round(z, 6)

def veckey3d(v):
    return veckey3(v.x, v.y, v.z)

def veckey2d(v):
    return round(v[0], 6), round(v[1], 6)

def to_srgb(c):
    """Blender 2.8+ stores colors linear; three.js expects what the color picker shows (sRGB)."""
    c = max(0.0, min(1.0, c))
    if c <= 0.0031308:
        return 12.92 * c
    return 1.055 * (c ** (1.0 / 2.4)) - 0.055

def srgb_color(rgb):
    return [to_srgb(rgb[0]), to_srgb(rgb[1]), to_srgb(rgb[2])]

def rgb2int(rgb):
    return (int(rgb[0] * 255) << 16) + (int(rgb[1] * 255) << 8) + int(rgb[2] * 255)

def hexcolor(c):
    return rgb2int(srgb_color(c))

def get_normal_indices(poly, normals, mesh):
    mv = mesh.vertices
    return [normals[veckey3d(mv[i].normal)] for i in poly.vertices]

def get_uv_indices(poly, uvs, mesh, layer_index):
    uv_layer = mesh.uv_layers[layer_index].data
    return [uvs[veckey2d(uv_layer[li].uv)] for li in poly.loop_indices]

def get_color_indices(poly, colors, mesh):
    color_layer = mesh.vertex_colors.active.data
    return [colors[hexcolor(color_layer[li].color)] for li in poly.loop_indices]

def mesh_use_flags(mesh, option_colors, option_uv_coords):
    use_colors = bool(option_colors and mesh.vertex_colors.active)
    use_uvs = bool(option_uv_coords and mesh.uv_layers.active)
    return use_colors, use_uvs

def set_frame(scene, frame):
    whole = int(math.floor(frame))
    scene.frame_set(whole, subframe=frame - whole)

# #####################################################
# Utils - files
# #####################################################

def write_file(fname, content):
    out = open(fname, "w", encoding="utf-8")
    out.write(content)
    out.close()

def ensure_folder_exist(foldername):
    """Create folder (with whole path) if it doesn't exist yet."""

    if foldername and not os.access(foldername, os.R_OK|os.W_OK|os.X_OK):
        os.makedirs(foldername)

def ensure_extension(filepath, extension):
    if not filepath.lower().endswith(extension):
        filepath += extension
    return filepath

def generate_mesh_filename(meshname, filepath):
    normpath = os.path.normpath(filepath)
    path, ext = os.path.splitext(normpath)
    return "%s.%s%s" % (path, meshname, ext)


# #####################################################
# Utils - alignment
# #####################################################

def bbox(vertices):
    """Compute bounding box of vertex array.
    """

    if len(vertices)>0:
        minx = maxx = vertices[0].co.x
        miny = maxy = vertices[0].co.y
        minz = maxz = vertices[0].co.z

        for v in vertices[1:]:
            if v.co.x < minx:
                minx = v.co.x
            elif v.co.x > maxx:
                maxx = v.co.x

            if v.co.y < miny:
                miny = v.co.y
            elif v.co.y > maxy:
                maxy = v.co.y

            if v.co.z < minz:
                minz = v.co.z
            elif v.co.z > maxz:
                maxz = v.co.z

        return { 'x':[minx,maxx], 'y':[miny,maxy], 'z':[minz,maxz] }

    else:
        return { 'x':[0,0], 'y':[0,0], 'z':[0,0] }

def translate(vertices, t):
    """Translate array of vertices by vector t.
    """

    for i in range(len(vertices)):
        vertices[i].co.x += t[0]
        vertices[i].co.y += t[1]
        vertices[i].co.z += t[2]

def center(vertices):
    """Center model (middle of bounding box).
    """

    bb = bbox(vertices)

    cx = bb['x'][0] + (bb['x'][1] - bb['x'][0])/2.0
    cy = bb['y'][0] + (bb['y'][1] - bb['y'][0])/2.0
    cz = bb['z'][0] + (bb['z'][1] - bb['z'][0])/2.0

    translate(vertices, [-cx,-cy,-cz])

    return [-cx,-cy,-cz]

def top(vertices):
    """Align top of the model with the floor (Y-axis) and center it around X and Z.
    """

    bb = bbox(vertices)

    cx = bb['x'][0] + (bb['x'][1] - bb['x'][0])/2.0
    cy = bb['y'][1]
    cz = bb['z'][0] + (bb['z'][1] - bb['z'][0])/2.0

    translate(vertices, [-cx,-cy,-cz])

    return [-cx,-cy,-cz]

def bottom(vertices):
    """Align bottom of the model with the floor (Y-axis) and center it around X and Z.
    """

    bb = bbox(vertices)

    cx = bb['x'][0] + (bb['x'][1] - bb['x'][0])/2.0
    cy = bb['y'][0]
    cz = bb['z'][0] + (bb['z'][1] - bb['z'][0])/2.0

    translate(vertices, [-cx,-cy,-cz])

    return [-cx,-cy,-cz]

# #####################################################
# Elements rendering
# #####################################################

def generate_vertices(vertices, option_vertices_truncate, option_vertices):
    if not option_vertices:
        return ""

    return ",".join(generate_vertex(v, option_vertices_truncate) for v in vertices)

def generate_vertex(v, option_vertices_truncate):
    if not option_vertices_truncate:
        return TEMPLATE_VERTEX % (v.co.x, v.co.y, v.co.z)
    else:
        return TEMPLATE_VERTEX_TRUNCATE % (v.co.x, v.co.y, v.co.z)

def generate_normal(n):
    return TEMPLATE_N % (n[0], n[1], n[2])

def generate_vertex_color(c):
    return TEMPLATE_C % c

def generate_uv(uv):
    return TEMPLATE_UV % (uv[0], uv[1])

# #####################################################
# Model exporter - faces
# #####################################################

def setBit(value, position, on):
    if on:
        mask = 1 << position
        return (value | mask)
    else:
        mask = ~(1 << position)
        return (value & mask)

def generate_faces(normals, uv_layers, colors, meshes, option_normals, option_colors, option_uv_coords, option_materials, option_faces):

    if not option_faces:
        return "", 0

    vertex_offset = 0
    material_offset = 0

    chunks = []
    for mesh, object in meshes:

        mesh_colors, mesh_uvs = mesh_use_flags(mesh, option_colors, option_uv_coords)

        for poly in mesh.polygons:
            face = generate_face(poly, normals, uv_layers, colors, mesh, option_normals, mesh_colors, mesh_uvs, option_materials, vertex_offset, material_offset)
            chunks.append(face)

        vertex_offset += len(mesh.vertices)
        material_offset += max(1, len(mesh.materials))

    return ",".join(chunks), len(chunks)

def generate_face(poly, normals, uv_layers, colors, mesh, option_normals, option_colors, option_uv_coords, option_materials, vertex_offset, material_offset):
    nVertices = len(poly.vertices)      # 3 or 4, n-gons are triangulated in extract_meshes
    isTriangle = (nVertices == 3)

    hasMaterial = option_materials

    hasFaceUvs = False # not supported in Blender
    hasFaceVertexUvs = option_uv_coords

    hasFaceNormals = False # don't export any face normals (as they are computed in engine)
    hasFaceVertexNormals = option_normals

    hasFaceColors = False       # not supported in Blender
    hasFaceVertexColors = option_colors

    faceType = 0
    faceType = setBit(faceType, 0, not isTriangle)
    faceType = setBit(faceType, 1, hasMaterial)
    faceType = setBit(faceType, 2, hasFaceUvs)
    faceType = setBit(faceType, 3, hasFaceVertexUvs)
    faceType = setBit(faceType, 4, hasFaceNormals)
    faceType = setBit(faceType, 5, hasFaceVertexNormals)
    faceType = setBit(faceType, 6, hasFaceColors)
    faceType = setBit(faceType, 7, hasFaceVertexColors)

    faceData = []

    # order is important, must match order in JSONLoader

    # face type
    # vertex indices
    # material index
    # face uvs index
    # face vertex uvs indices
    # face color index
    # face vertex colors indices

    faceData.append(faceType)

    for i in range(nVertices):
        faceData.append(poly.vertices[i] + vertex_offset)

    if hasMaterial:
        material_index = min(poly.material_index, max(0, len(mesh.materials) - 1))
        faceData.append(material_index + material_offset)

    if hasFaceVertexUvs:
        for layer_index, uvs in enumerate(uv_layers):
            if layer_index < len(mesh.uv_layers):
                faceData.extend(get_uv_indices(poly, uvs, mesh, layer_index))

    if hasFaceVertexNormals:
        faceData.extend(get_normal_indices(poly, normals, mesh))

    if hasFaceVertexColors:
        faceData.extend(get_color_indices(poly, colors, mesh))

    return ",".join( map(str, faceData) )


# #####################################################
# Model exporter - normals
# #####################################################

def extract_vertex_normals(mesh, normals, count):
    for poly in mesh.polygons:
        for v in poly.vertices:

            key = veckey3d(mesh.vertices[v].normal)

            if key not in normals:
                normals[key] = count
                count += 1

    return count

def generate_normals(normals, option_normals):
    if not option_normals:
        return ""

    chunks = []
    for key, index in sorted(normals.items(), key = operator.itemgetter(1)):
        chunks.append(key)

    return ",".join(generate_normal(n) for n in chunks)

# #####################################################
# Model exporter - vertex colors
# #####################################################

def extract_vertex_colors(mesh, colors, count):
    color_layer = mesh.vertex_colors.active.data

    for poly in mesh.polygons:
        for li in poly.loop_indices:
            key = hexcolor(color_layer[li].color)
            if key not in colors:
                colors[key] = count
                count += 1

    return count

def generate_vertex_colors(colors, option_colors):
    if not option_colors:
        return ""

    chunks = []
    for key, index in sorted(colors.items(), key=operator.itemgetter(1)):
        chunks.append(key)

    return ",".join(generate_vertex_color(c) for c in chunks)

# #####################################################
# Model exporter - UVs
# #####################################################

def extract_uvs(mesh, uv_layers, counts):
    for index, layer in enumerate(mesh.uv_layers):

        if len(uv_layers) <= index:
            uvs = {}
            count = 0
            uv_layers.append(uvs)
            counts.append(count)
        else:
            uvs = uv_layers[index]
            count = counts[index]

        uv_data = layer.data

        for poly in mesh.polygons:
            for li in poly.loop_indices:

                key = veckey2d(uv_data[li].uv)
                if key not in uvs:
                    uvs[key] = count
                    count += 1

        counts[index] = count

    return counts

def generate_uvs(uv_layers, option_uv_coords):
    if not option_uv_coords:
        return "[]"

    layers = []
    for uvs in uv_layers:
        chunks = []
        for key, index in sorted(uvs.items(), key=operator.itemgetter(1)):
            chunks.append(key)
        layer = ",".join(generate_uv(n) for n in chunks)
        layers.append(layer)

    return ",".join("[%s]" % n for n in layers)

# ##############################################################################
# Model exporter - armature
# (only the first armature will exported)
# ##############################################################################
def get_armature():
    if len(bpy.data.armatures) == 0:
        print("Warning: no armatures in the scene")
        return None, None

    armature = bpy.data.armatures[0]

    for object in bpy.data.objects:
        if object.type == 'ARMATURE':
            return armature, object

    print("Warning: no node of type 'ARMATURE' in the scene")
    return None, None

# ##############################################################################
# Model exporter - bones
# (only the first armature will exported)
# ##############################################################################

def generate_bones(meshes, option_bones, flipyz):

    if not option_bones:
        return "", 0

    armature, armature_object = get_armature()
    if armature_object is None:
        return "", 0

    hierarchy = []
    armature_matrix = armature_object.matrix_world
    pose_bones = armature_object.pose.bones
    bone_indices = dict((pb.name, i) for i, pb in enumerate(pose_bones))

    TEMPLATE_BONE = '{"parent":%d,"name":"%s","pos":[%g,%g,%g],"rotq":[%g,%g,%g,%g],"scl":[%g,%g,%g]}'

    for pose_bone in pose_bones:
        armature_bone = pose_bone.bone

        if armature_bone.parent is None:
            bone_matrix = armature_matrix @ armature_bone.matrix_local
            bone_index = -1
        else:
            parent_matrix = armature_matrix @ armature_bone.parent.matrix_local
            bone_matrix = armature_matrix @ armature_bone.matrix_local
            bone_matrix = parent_matrix.inverted() @ bone_matrix
            bone_index = bone_indices.get(armature_bone.parent.name, 0)

        pos, rot, scl = bone_matrix.decompose()

        if flipyz:
            joint = TEMPLATE_BONE % (bone_index, armature_bone.name, pos.x, pos.z, -pos.y, rot.x, rot.z, -rot.y, rot.w, scl.x, scl.z, scl.y)
        else:
            joint = TEMPLATE_BONE % (bone_index, armature_bone.name, pos.x, pos.y,  pos.z, rot.x, rot.y,  rot.z, rot.w, scl.x, scl.y, scl.z)
        hierarchy.append(joint)

    bones_string = ",".join(hierarchy)

    return bones_string, len(pose_bones)


# ##############################################################################
# Model exporter - skin indices and weights
# ##############################################################################

def generate_indices_and_weights(meshes, option_skinning):

    if not option_skinning or len(bpy.data.armatures) == 0:
        return "", ""

    armature, armature_object = get_armature()
    if armature_object is None:
        return "", ""

    bone_lookup = dict((pb.name, j) for j, pb in enumerate(armature_object.pose.bones))

    indices = []
    weights = []

    for mesh, object in meshes:

        group_names = [g.name for g in object.vertex_groups]

        for vertex in mesh.vertices:

            # sort bones by influence

            bone_array = [(g.group, g.weight) for g in vertex.groups]
            bone_array.sort(key = operator.itemgetter(1), reverse=True)

            # select first N bones

            for i in range(MAX_INFLUENCES):

                j = None
                weight = 0

                if i < len(bone_array):
                    index, weight = bone_array[i]
                    if index < len(group_names):
                        j = bone_lookup.get(group_names[index])

                if j is not None:
                    indices.append('%d' % j)
                    weights.append('%g' % weight)
                else:
                    indices.append('0')
                    weights.append('0')

    return ",".join(indices), ",".join(weights)


# ##############################################################################
# Model exporter - skeletal animation
# (all actions are exported, one animation per action)
# ##############################################################################

def generate_animation(option_animation_skeletal, option_frame_step, flipyz, option_frame_index_as_time, index):

    if not option_animation_skeletal or len(bpy.data.actions) == 0:
        return ""

    armature, armature_object = get_armature()
    if armature_object is None or armature is None:
        return ""

    action = bpy.data.actions[index]
    scene = bpy.context.scene

    # temporarily assign the action to the armature so the pose follows it

    if armature_object.animation_data is None:
        armature_object.animation_data_create()
    anim_data = armature_object.animation_data
    previous_action = anim_data.action
    anim_data.action = action
    original_frame = scene.frame_current

    fps = scene.render.fps

    start_frame = action.frame_range[0]
    end_frame = action.frame_range[1]

    frame_length = end_frame - start_frame

    used_frames = int(frame_length / option_frame_step) + 1

    TEMPLATE_KEYFRAME_FULL  = '{"time":%g,"pos":[%g,%g,%g],"rot":[%g,%g,%g,%g],"scl":[%g,%g,%g]}'

    bone_names = [pb.name for pb in armature_object.pose.bones]
    keys = [[] for name in bone_names]

    # Process all frames
    for frame_i in range(0, used_frames):

        # Compute the index of the current frame (snap the last index to the end)
        frame = start_frame + frame_i * option_frame_step
        if frame_i == used_frames-1:
            frame = end_frame

        # Compute the time of the frame
        if option_frame_index_as_time:
            time = frame - start_frame
        else:
            time = (frame - start_frame) / fps

        # Let blender compute the pose bone transformations
        set_frame(scene, frame)

        eval_object = armature_object.evaluated_get(bpy.context.evaluated_depsgraph_get())
        armature_matrix = eval_object.matrix_world

        for bone_index, pose_bone in enumerate(eval_object.pose.bones):

            if pose_bone.parent is None:
                bone_matrix = armature_matrix @ pose_bone.matrix
            else:
                parent_matrix = armature_matrix @ pose_bone.parent.matrix
                bone_matrix = armature_matrix @ pose_bone.matrix
                bone_matrix = parent_matrix.inverted() @ bone_matrix
            pos, rot, scl = bone_matrix.decompose()

            if flipyz:
                px, py, pz = pos.x, pos.z, -pos.y
                rx, ry, rz, rw = rot.x, rot.z, -rot.y, rot.w
                sx, sy, sz = scl.x, scl.z, scl.y
            else:
                px, py, pz = pos.x, pos.y, pos.z
                rx, ry, rz, rw = rot.x, rot.y, rot.z, rot.w
                sx, sy, sz = scl.x, scl.y, scl.z

            keys[bone_index].append(TEMPLATE_KEYFRAME_FULL % (time, px, py, pz, rx, ry, rz, rw, sx, sy, sz))

    # Gather data
    parents = []
    for bone_index in range(len(bone_names)):
        keys_string = ",".join(keys[bone_index])
        parent_index = bone_index - 1 # this property is not used by three.js
        parents.append('{"parent":%d,"keys":[%s]}' % (parent_index, keys_string))
    hierarchy_string = ",".join(parents)

    if option_frame_index_as_time:
        length = frame_length
    else:
        length = frame_length / fps

    animation_string = '"name":"%s","fps":%d,"length":%g,"hierarchy":[%s]' % (action.name, fps, length, hierarchy_string)

    # restore state
    anim_data.action = previous_action
    set_frame(scene, original_frame)

    return animation_string

def generate_all_animations(option_animation_skeletal, option_frame_step, flipyz, option_frame_index_as_time):
    animations = []
    if option_animation_skeletal:
        for index in range(0, len(bpy.data.actions)):
            animation = generate_animation(option_animation_skeletal, option_frame_step, flipyz, option_frame_index_as_time, index)
            if animation:
                animations.append("{" + animation + "}")
    return ", \n".join(animations)

# #####################################################
# Model exporter - materials
# #####################################################

def generate_color(i):
    """Generate hex color corresponding to integer.

    Colors should have well defined ordering.
    First N colors are hardcoded, then colors are random
    (must seed random number  generator with deterministic value
    before getting colors).
    """

    if i < len(COLORS):
        return COLORS[i]
    else:
        return int(0xffffff * random.random())

def generate_mtl(materials):
    """Generate dummy materials.
    """

    mtl = {}
    for m in materials:
        index = materials[m]
        mtl[m] = {
            "DbgName": m,
            "DbgIndex": index,
            "DbgColor": generate_color(index),
            "vertexColors" : False
        }
    return mtl

def value2string(v):
    if type(v) == str and v[0:2] != "0x":
        return '"%s"' % v
    elif type(v) == bool:
        return str(v).lower()
    elif type(v) == list:
        return "[%s]" % (", ".join(value2string(x) for x in v))
    return str(v)

def generate_materials(mtl, materials, draw_type):
    """Generate JS array of materials objects
    """

    mtl_array = []
    for m in mtl:
        index = materials[m]

        # add debug information
        #  this index is identifier used in face definitions
        mtl[m]['DbgName'] = m
        mtl[m]['DbgIndex'] = index
        mtl[m]['DbgColor'] = generate_color(index)

        if draw_type in [ "BOUNDS", "WIRE" ]:
            mtl[m]['wireframe'] = True
            mtl[m]['DbgColor'] = 0xff0000

        mtl_raw = ",\n".join(['\t\t"%s" : %s' % (n, value2string(v)) for n,v in sorted(mtl[m].items())])
        mtl_string = "\t{\n%s\n\t}" % mtl_raw
        mtl_array.append([index, mtl_string])

    return ",\n\n".join([m for i,m in sorted(mtl_array)]), len(mtl_array)

# -----------------------------------------------------
# Material reading (node based, Principled BSDF)
# -----------------------------------------------------

def find_principled(m):
    """Principled BSDF feeding the active material output (or the first one found)."""

    if not (m.use_nodes and m.node_tree):
        return None

    nodes = m.node_tree.nodes

    for n in nodes:
        if n.type == 'OUTPUT_MATERIAL' and n.is_active_output:
            surface = n.inputs['Surface']
            if surface.is_linked and surface.links[0].from_node.type == 'BSDF_PRINCIPLED':
                return surface.links[0].from_node
            break

    for n in nodes:
        if n.type == 'BSDF_PRINCIPLED':
            return n

    return None

def get_socket(node, *names):
    for name in names:
        if name in node.inputs:
            return node.inputs[name]
    return None

def socket_image(socket):
    """Image texture node linked directly to the socket (or None)."""

    if socket is None or not socket.is_linked:
        return None

    node = socket.links[0].from_node
    if node.type == 'TEX_IMAGE' and node.image:
        return node

    return None

def get_material_info(m):
    """Read what three.js can use from a Blender 2.8+ material.

    Uses the Principled BSDF node if there is one, the viewport
    settings of the material otherwise.
    """

    textures = dict((slot, None) for slot in TEXTURE_SLOTS)

    diffuse = list(m.diffuse_color[:3])
    alpha = m.diffuse_color[3]
    specular = m.specular_intensity
    roughness = m.roughness
    emissive = [0.0, 0.0, 0.0]
    normal_factor = 1.0
    bump_scale = 1.0

    bsdf = find_principled(m)

    if bsdf is not None:

        base = get_socket(bsdf, 'Base Color')
        if base is not None:
            diffuse = list(base.default_value[:3])
            node = socket_image(base)
            if node:
                textures['diffuse'] = node
                diffuse = [1.0, 1.0, 1.0]

        a = get_socket(bsdf, 'Alpha')
        if a is not None:
            alpha = 1.0 if a.is_linked else a.default_value

        s = get_socket(bsdf, 'Specular')
        if s is not None:
            specular = s.default_value
            textures['specular'] = socket_image(s)

        r = get_socket(bsdf, 'Roughness')
        if r is not None:
            roughness = r.default_value

        e = get_socket(bsdf, 'Emission', 'Emission Color')
        if e is not None and not e.is_linked:
            strength = get_socket(bsdf, 'Emission Strength')
            k = strength.default_value if (strength is not None and not strength.is_linked) else 1.0
            emissive = [min(1.0, c * k) for c in e.default_value[:3]]

        n = get_socket(bsdf, 'Normal')
        if n is not None and n.is_linked:
            nn = n.links[0].from_node
            if nn.type == 'NORMAL_MAP':
                node = socket_image(nn.inputs['Color'])
                if node:
                    textures['normal'] = node
                    normal_factor = nn.inputs['Strength'].default_value
            elif nn.type == 'BUMP':
                node = socket_image(nn.inputs['Height'])
                if node:
                    textures['bump'] = node
                    bump_scale = nn.inputs['Strength'].default_value

    elif m.use_nodes and m.node_tree:

        for node in m.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                textures['diffuse'] = node
                diffuse = [1.0, 1.0, 1.0]
                break

    # roughness -> Phong shininess (Blender internal used hardness in [1, 511])
    r = max(0.05, min(1.0, roughness))
    shininess = max(1.0, min(511.0, 2.0 / (r ** 4) - 2.0))

    blend_method = getattr(m, "blend_method", "OPAQUE")

    return {
        "colorDiffuse"  : srgb_color(diffuse),
        "colorSpecular" : [specular, specular, specular],
        "colorEmissive" : srgb_color(emissive),
        "transparency"  : alpha,
        "specularCoef"  : shininess,
        "transparent"   : blend_method != 'OPAQUE' or alpha < 1.0,
        "textures"      : textures,
        "normalFactor"  : normal_factor,
        "bumpScale"     : bump_scale
    }

def extract_materials(mesh, scene, option_colors, option_copy_textures, filepath):

    materials = {}
    for m in mesh.materials:
        if m:
            materials[m.name] = {}
            material = materials[m.name]

            info = get_material_info(m)
            textures = info['textures']

            material['colorDiffuse'] = info['colorDiffuse']
            material['colorSpecular'] = info['colorSpecular']
            material['colorAmbient'] = list(info['colorDiffuse'])
            material['colorEmissive'] = info['colorEmissive']
            material['transparency'] = info['transparency']
            material["specularCoef"] = info['specularCoef']

            for slot in TEXTURE_SLOTS:
                handle_texture(slot, textures, material, filepath, option_copy_textures)

            if textures['normal'] and info['normalFactor'] != 1.0:
                material['mapNormalFactor'] = info['normalFactor']

            if textures['bump'] and info['bumpScale'] != 1.0:
                material['mapBumpScale'] = info['bumpScale']

            material["vertexColors"] = m.THREE_useVertexColors and option_colors

            if textures['normal']:
                material['shading'] = "Phong"
            else:
                material['shading'] = m.THREE_materialType

            material['blending'] = m.THREE_blendingType
            material['depthWrite'] = m.THREE_depthWrite
            material['depthTest'] = m.THREE_depthTest
            material['transparent'] = info['transparent']

    return materials

def generate_materials_string(mesh, scene, option_colors, draw_type, option_copy_textures, filepath, offset):

    random.seed(42) # to get well defined color order for debug materials

    materials = {}
    if mesh.materials:
        for i, m in enumerate(mesh.materials):
            mat_id = i + offset
            if m:
                materials[m.name] = mat_id
            else:
                materials["undefined_dummy_%0d" % mat_id] = mat_id


    if not materials:
        materials = { 'default': offset }

    # default dummy materials

    mtl = generate_mtl(materials)

    # extract real materials from the mesh

    mtl.update(extract_materials(mesh, scene, option_colors, option_copy_textures, filepath))

    return generate_materials(mtl, materials, draw_type)

def handle_texture(id, textures, material, filepath, option_copy_textures):

    node = textures[id]

    if node is None:
        return

    texName = 'map%s'     % id.capitalize()
    wrapName = 'map%sWrap' % id.capitalize()

    image = node.image
    fname = extract_texture_filename(image)
    material[texName] = fname

    if option_copy_textures:
        save_image(image, fname, filepath)

    if node.extension == "REPEAT":
        material[wrapName] = ["repeat", "repeat"]


# #####################################################
# ASCII model generator
# #####################################################

def generate_ascii_model(meshes, morphs,
                         scene,
                         option_vertices,
                         option_vertices_truncate,
                         option_faces,
                         option_normals,
                         option_uv_coords,
                         option_materials,
                         option_colors,
                         option_bones,
                         option_skinning,
                         align_model,
                         flipyz,
                         option_scale,
                         option_copy_textures,
                         filepath,
                         option_animation_morph,
                         option_animation_skeletal,
                         option_frame_index_as_time,
                         option_frame_step):

    vertices = []

    nnormal = 0
    normals = {}

    ncolor = 0
    colors = {}

    nuvs = []
    uv_layers = []

    nmaterial = 0
    materials = []

    for mesh, object in meshes:

        mesh_extract_colors, mesh_extract_uvs = mesh_use_flags(mesh, option_colors, option_uv_coords)

        vertices.extend(mesh.vertices[:])

        if option_normals:
            nnormal = extract_vertex_normals(mesh, normals, nnormal)

        if mesh_extract_colors:
            ncolor = extract_vertex_colors(mesh, colors, ncolor)

        if mesh_extract_uvs:
            nuvs = extract_uvs(mesh, uv_layers, nuvs)

        if option_materials:
            mesh_materials, count = generate_materials_string(mesh, scene, mesh_extract_colors, object.display_type, option_copy_textures, filepath, nmaterial)
            nmaterial += count
            materials.append(mesh_materials)


    morphTargets_string = ""
    nmorphTarget = 0

    if option_animation_morph:
        chunks = []
        for i, morphVertices in enumerate(morphs):
            morphTarget = '{ "name": "%s_%06d", "vertices": [%s] }' % ("animation", i, morphVertices)
            chunks.append(morphTarget)

        morphTargets_string = ",\n\t".join(chunks)
        nmorphTarget = len(morphs)

    if align_model == 1:
        center(vertices)
    elif align_model == 2:
        bottom(vertices)
    elif align_model == 3:
        top(vertices)

    faces_string, nfaces = generate_faces(normals, uv_layers, colors, meshes, option_normals, option_colors, option_uv_coords, option_materials, option_faces)

    bones_string, nbone = generate_bones(meshes, option_bones, flipyz)
    indices_string, weights_string = generate_indices_and_weights(meshes, option_skinning)

    materials_string = ",\n\n".join(materials)

    model_string = TEMPLATE_MODEL_ASCII % {
    "scale" : option_scale,

    "uvs"       : generate_uvs(uv_layers, option_uv_coords),
    "normals"   : generate_normals(normals, option_normals),
    "colors"    : generate_vertex_colors(colors, option_colors),

    "materials" : materials_string,

    "vertices" : generate_vertices(vertices, option_vertices_truncate, option_vertices),

    "faces"    : faces_string,

    "morphTargets" : morphTargets_string,

    "bones"     : bones_string,
    "indices"   : indices_string,
    "weights"   : weights_string,
    "animations" : generate_all_animations(option_animation_skeletal, option_frame_step, flipyz, option_frame_index_as_time)
    }

    text = TEMPLATE_FILE_ASCII % {
    "nvertex"   : len(vertices),
    "nface"     : nfaces,
    "nuvs"      : ",".join("%d" % n for n in nuvs),
    "nnormal"   : nnormal,
    "ncolor"    : ncolor,
    "nmaterial" : nmaterial,
    "nmorphTarget": nmorphTarget,
    "nbone"     : nbone,

    "model"     : model_string
    }


    return text, model_string


# #####################################################
# Model exporter - export single mesh
# #####################################################

def triangulate_ngons(mesh):
    """three.js faces are triangles or quads: split everything bigger."""

    if not any(len(p.vertices) > 4 for p in mesh.polygons):
        return

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    bm.to_mesh(mesh)
    bm.free()

def extract_meshes(objects, scene, export_single_model, option_scale, flipyz):

    meshes = []

    depsgraph = bpy.context.evaluated_depsgraph_get()

    for object in objects:

        if object.type == "MESH" and object.THREE_exportGeometry:

            # collapse modifiers into a new mesh datablock

            # NOTE: the depsgraph must be passed explicitly, otherwise Blender
            # silently returns an EMPTY mesh when preserve_all_data_layers=True
            eval_object = object.evaluated_get(depsgraph)
            mesh = bpy.data.meshes.new_from_object(eval_object, preserve_all_data_layers=True, depsgraph=depsgraph)

            if not mesh:
                raise Exception("Error, could not get mesh data from object [%s]" % object.name)

            if len(mesh.vertices) == 0 and len(object.data.vertices) > 0:
                bpy.data.meshes.remove(mesh)
                raise Exception("Error, got an empty mesh from object [%s] (is it hidden in the viewport?)" % object.name)

            triangulate_ngons(mesh)

            if export_single_model:

                if flipyz:

                    # that's what Blender's native export_obj.py does to flip YZ

                    X_ROT = mathutils.Matrix.Rotation(-math.pi/2, 4, 'X')
                    mesh.transform(X_ROT @ object.matrix_world)

                else:
                    mesh.transform(object.matrix_world)

            mesh.transform(mathutils.Matrix.Scale(option_scale, 4))

            # vertex normals are used by the exporter, make sure they match the transformed mesh
            if hasattr(mesh, "calc_normals"):
                mesh.calc_normals()

            meshes.append([mesh, object])

    return meshes

def generate_mesh_string(objects, scene,
                option_vertices,
                option_vertices_truncate,
                option_faces,
                option_normals,
                option_uv_coords,
                option_materials,
                option_colors,
                option_bones,
                option_skinning,
                align_model,
                flipyz,
                option_scale,
                export_single_model,
                option_copy_textures,
                filepath,
                option_animation_morph,
                option_animation_skeletal,
                option_frame_index_as_time,
                option_frame_step):

    meshes = extract_meshes(objects, scene, export_single_model, option_scale, flipyz)

    morphs = []

    if option_animation_morph:

        original_frame = scene.frame_current # save animation state

        scene_frames = range(scene.frame_start, scene.frame_end + 1, option_frame_step)

        for index, frame in enumerate(scene_frames):
            scene.frame_set(frame, subframe=0.0)

            anim_meshes = extract_meshes(objects, scene, export_single_model, option_scale, flipyz)

            frame_vertices = []

            for mesh, object in anim_meshes:
                frame_vertices.extend(mesh.vertices[:])

            if index == 0:
                if align_model == 1:
                    offset = center(frame_vertices)
                elif align_model == 2:
                    offset = bottom(frame_vertices)
                elif align_model == 3:
                    offset = top(frame_vertices)
                else:
                    offset = False
            else:
                if offset:
                    translate(frame_vertices, offset)

            morphVertices = generate_vertices(frame_vertices, option_vertices_truncate, option_vertices)
            morphs.append(morphVertices)

            # remove temp meshes

            for mesh, object in anim_meshes:
                bpy.data.meshes.remove(mesh)

        scene.frame_set(original_frame, subframe=0.0) # restore animation state


    text, model_string = generate_ascii_model(meshes, morphs,
                                scene,
                                option_vertices,
                                option_vertices_truncate,
                                option_faces,
                                option_normals,
                                option_uv_coords,
                                option_materials,
                                option_colors,
                                option_bones,
                                option_skinning,
                                align_model,
                                flipyz,
                                option_scale,
                                option_copy_textures,
                                filepath,
                                option_animation_morph,
                                option_animation_skeletal,
                                option_frame_index_as_time,
                                option_frame_step)

    # remove temp meshes

    for mesh, object in meshes:
        bpy.data.meshes.remove(mesh)

    return text, model_string

def export_mesh(objects,
                scene, filepath,
                option_vertices,
                option_vertices_truncate,
                option_faces,
                option_normals,
                option_uv_coords,
                option_materials,
                option_colors,
                option_bones,
                option_skinning,
                align_model,
                flipyz,
                option_scale,
                export_single_model,
                option_copy_textures,
                option_animation_morph,
                option_animation_skeletal,
                option_frame_step,
                option_frame_index_as_time):

    """Export single mesh"""

    text, model_string = generate_mesh_string(objects,
                scene,
                option_vertices,
                option_vertices_truncate,
                option_faces,
                option_normals,
                option_uv_coords,
                option_materials,
                option_colors,
                option_bones,
                option_skinning,
                align_model,
                flipyz,
                option_scale,
                export_single_model,
                option_copy_textures,
                filepath,
                option_animation_morph,
                option_animation_skeletal,
                option_frame_index_as_time,
                option_frame_step)

    write_file(filepath, text)

    print("writing", filepath, "done")


# #####################################################
# Scene exporter - render elements
# #####################################################

def generate_quat(quat):
    return TEMPLATE_VEC4 % (quat.x, quat.y, quat.z, quat.w)

def generate_vec4(vec):
    return TEMPLATE_VEC4 % (vec[0], vec[1], vec[2], vec[3])

def generate_vec3(vec, flipyz = False):
    if flipyz:
        return TEMPLATE_VEC3 % (vec[0], vec[2], vec[1])
    return TEMPLATE_VEC3 % (vec[0], vec[1], vec[2])

def generate_vec2(vec):
    return TEMPLATE_VEC2 % (vec[0], vec[1])

def generate_hex(number):
    return TEMPLATE_HEX % number

def generate_string(s):
    return TEMPLATE_STRING % s

def generate_string_list(src_list):
    return ", ".join(generate_string(item) for item in src_list)

def generate_section(label, content):
    return TEMPLATE_SECTION % (label, content)

def generate_material_id_list(materials):
    chunks = []
    for material in materials:
        chunks.append(material.name)

    return chunks

def generate_group_id_list(obj):
    chunks = []

    for group in bpy.data.collections:
        if obj.name in group.objects:
            chunks.append(group.name)

    return chunks

def generate_bool_property(property):
    if property:
        return "true"
    return "false"

# #####################################################
# Scene exporter - objects
# #####################################################

def generate_objects(data):
    chunks = []

    for obj in data["objects"]:

        if obj.type == "MESH" and obj.THREE_exportGeometry:
            object_id = obj.name

            geo_name = obj.data.name

            geometry_id = "geo_%s" % geo_name

            material_ids = generate_material_id_list(obj.material_slots)
            group_ids = generate_group_id_list(obj)

            if data["flipyz"]:
                matrix_world = ROTATE_X_PI2 @ obj.matrix_world
            else:
                matrix_world = obj.matrix_world

            position, quaternion, scale = matrix_world.decompose()
            rotation = quaternion.to_euler("ZYX")

            # use empty material string for multi-material objects
            # this will trigger use of MeshFaceMaterial in SceneLoader

            material_string = '""'
            if len(material_ids) == 1:
                material_string = generate_string_list(material_ids)

            group_string = ""
            if len(group_ids) > 0:
                group_string = generate_string_list(group_ids)

            castShadow = obj.THREE_castShadow
            receiveShadow = obj.THREE_receiveShadow
            doubleSided = obj.THREE_doubleSided

            visible = obj.THREE_visible

            geometry_string = generate_string(geometry_id)

            object_string = TEMPLATE_OBJECT % {
            "object_id"   : generate_string(object_id),
            "geometry_id" : geometry_string,
            "group_id"    : group_string,
            "material_id" : material_string,

            "position"    : generate_vec3(position),
            "rotation"    : generate_vec3(rotation),
            "quaternion"  : generate_quat(quaternion),
            "scale"       : generate_vec3(scale),

            "castShadow"  : generate_bool_property(castShadow),
            "receiveShadow"  : generate_bool_property(receiveShadow),
            "doubleSided"  : generate_bool_property(doubleSided),
            "visible"      : generate_bool_property(visible)
            }
            chunks.append(object_string)

        elif obj.type == "EMPTY" or (obj.type == "MESH" and not obj.THREE_exportGeometry):

            object_id = obj.name
            group_ids = generate_group_id_list(obj)

            if data["flipyz"]:
                matrix_world = ROTATE_X_PI2 @ obj.matrix_world
            else:
                matrix_world = obj.matrix_world

            position, quaternion, scale = matrix_world.decompose()
            rotation = quaternion.to_euler("ZYX")

            group_string = ""
            if len(group_ids) > 0:
                group_string = generate_string_list(group_ids)

            object_string = TEMPLATE_EMPTY % {
            "object_id"   : generate_string(object_id),
            "group_id"    : group_string,

            "position"    : generate_vec3(position),
            "rotation"    : generate_vec3(rotation),
            "quaternion"  : generate_quat(quaternion),
            "scale"       : generate_vec3(scale)
            }
            chunks.append(object_string)

    return ",\n\n".join(chunks), len(chunks)

# #####################################################
# Scene exporter - geometries
# #####################################################

def generate_geometries(data):
    chunks = []

    geo_set = set()

    for obj in data["objects"]:
        if obj.type == "MESH" and obj.THREE_exportGeometry:

            name = obj.data.name

            if name not in geo_set:

                geometry_id = "geo_%s" % name

                if data["embed_meshes"]:

                    embed_id = "emb_%s" % name

                    geometry_string = TEMPLATE_GEOMETRY_EMBED % {
                    "geometry_id" : generate_string(geometry_id),
                    "embed_id"  : generate_string(embed_id)
                    }

                else:

                    model_filename = os.path.basename(generate_mesh_filename(name, data["filepath"]))

                    geometry_string = TEMPLATE_GEOMETRY_LINK % {
                    "geometry_id" : generate_string(geometry_id),
                    "model_file"  : generate_string(model_filename)
                    }

                chunks.append(geometry_string)

                geo_set.add(name)

    return ",\n\n".join(chunks), len(chunks)

# #####################################################
# Scene exporter - textures
# #####################################################

def extract_texture_filename(image):
    if image.filepath:
        fn = bpy.path.abspath(image.filepath, library=image.library)
        return os.path.basename(os.path.normpath(fn))

    # generated / packed image without a file
    name = image.name
    if not os.path.splitext(name)[1]:
        name += ".png"
    return name

def save_image(img, name, fpath):
    dst_dir = os.path.dirname(fpath)
    dst_path = os.path.join(dst_dir, name)

    ensure_folder_exist(dst_dir)

    src_path = bpy.path.abspath(img.filepath, library=img.library) if img.filepath else ""

    if img.packed_file or not os.path.isfile(src_path):
        img.save_render(dst_path)
    elif os.path.abspath(src_path) != os.path.abspath(dst_path):
        shutil.copy(src_path, dst_path)

def used_materials():
    def material_is_used(mat):
        if mat.is_grease_pencil:
            return False
        minimum_users = 1
        if mat.use_fake_user:
            minimum_users = 2 #we must ignore the "fake user" in this case
        return mat.users >= minimum_users

    return [m for m in bpy.data.materials if material_is_used(m)]

def generate_textures_scene(data):
    chunks = []
    seen = set()

    for m in used_materials():

        textures = get_material_info(m)['textures']

        for slot in TEXTURE_SLOTS:

            node = textures[slot]
            if node is None:
                continue

            img = node.image
            if img.name in seen:
                continue
            seen.add(img.name)

            texture_id = img.name
            texture_file = extract_texture_filename(img)

            if data["copy_textures"]:
                save_image(img, texture_file, data["filepath"])

            extras = ""

            if node.extension == "REPEAT":
                extras += ',\n        "wrap": ["repeat", "repeat"]'

            texture_string = TEMPLATE_TEXTURE % {
            "texture_id"   : generate_string(texture_id),
            "texture_file" : generate_string(texture_file),
            "extras"       : extras
            }
            chunks.append(texture_string)

    return ",\n\n".join(chunks), len(chunks)

# #####################################################
# Scene exporter - materials
# #####################################################

def extract_material_data(m, option_colors):

    info = get_material_info(m)
    textures = info['textures']

    material = { 'name': m.name }

    material['colorDiffuse'] = info['colorDiffuse']
    material['colorSpecular'] = info['colorSpecular']
    material['colorAmbient'] = list(info['colorDiffuse'])
    material['colorEmissive'] = info['colorEmissive']
    material['transparency'] = info['transparency']
    material["specularCoef"] = info['specularCoef']

    material["vertexColors"] = m.THREE_useVertexColors and option_colors

    material['mapDiffuse'] = textures['diffuse'].image.name if textures['diffuse'] else ""
    material['mapLight'] = textures['light'].image.name if textures['light'] else ""
    material['mapSpecular'] = textures['specular'].image.name if textures['specular'] else ""
    material['mapNormal'] = textures['normal'].image.name if textures['normal'] else ""
    material['mapBump'] = textures['bump'].image.name if textures['bump'] else ""

    material['mapNormalFactor'] = info['normalFactor']
    material['mapBumpScale'] = info['bumpScale']

    material['shading'] = m.THREE_materialType
    material['blending'] = m.THREE_blendingType
    material['depthWrite'] = m.THREE_depthWrite
    material['depthTest'] = m.THREE_depthTest
    material['transparent'] = info['transparent']

    return material

def generate_material_string(material):

    material_id = material["name"]

    # default to Lambert

    shading = material.get("shading", "Lambert")

    # normal and bump mapped materials must use Phong
    # to get all required parameters for normal shader

    if material['mapNormal'] or material['mapBump']:
        shading = "Phong"

    type_map = {
    "Lambert"   : "MeshLambertMaterial",
    "Phong"     : "MeshPhongMaterial"
    }

    material_type = type_map.get(shading, "MeshBasicMaterial")

    parameters = '"color": %d' % rgb2int(material["colorDiffuse"])
    parameters += ', "ambient": %d' % rgb2int(material["colorAmbient"])
    parameters += ', "emissive": %d' % rgb2int(material["colorEmissive"])
    parameters += ', "opacity": %.2g' % material["transparency"]

    if shading == "Phong":
        parameters += ', "specular": %d' % rgb2int(material["colorSpecular"])
        parameters += ', "shininess": %g' % material["specularCoef"]

    colorMap = material['mapDiffuse']
    lightMap = material['mapLight']
    specularMap = material['mapSpecular']
    normalMap = material['mapNormal']
    bumpMap = material['mapBump']
    normalMapFactor = material['mapNormalFactor']
    bumpMapScale = material['mapBumpScale']

    if colorMap:
        parameters += ', "map": %s' % generate_string(colorMap)
    if lightMap:
        parameters += ', "lightMap": %s' % generate_string(lightMap)
    if specularMap:
        parameters += ', "specularMap": %s' % generate_string(specularMap)
    if normalMap:
        parameters += ', "normalMap": %s' % generate_string(normalMap)
    if bumpMap:
        parameters += ', "bumpMap": %s' % generate_string(bumpMap)

    if normalMap and normalMapFactor != 1.0:
        parameters += ', "normalMapFactor": %g' % normalMapFactor

    if bumpMap and bumpMapScale != 1.0:
        parameters += ', "bumpMapScale": %g' % bumpMapScale

    if material['vertexColors']:
        parameters += ', "vertexColors": "vertex"'

    if material['transparent']:
        parameters += ', "transparent": true'

    parameters += ', "blending": "%s"' % material['blending']

    if not material['depthWrite']:
        parameters += ', "depthWrite": false'

    if not material['depthTest']:
        parameters += ', "depthTest": false'


    material_string = TEMPLATE_MATERIAL_SCENE % {
    "material_id" : generate_string(material_id),
    "type"        : generate_string(material_type),
    "parameters"  : parameters
    }

    return material_string

def generate_materials_scene(data):
    chunks = []

    for m in used_materials():
        material = extract_material_data(m, data["use_colors"])
        material_string = generate_material_string(material)
        chunks.append(material_string)

    return ",\n\n".join(chunks), len(chunks)

# #####################################################
# Scene exporter - cameras
# #####################################################

def generate_cameras(data):
    chunks = []

    if data["use_cameras"]:

        view_layer_objects = bpy.context.view_layer.objects
        cams = [ob for ob in bpy.data.objects if ob.type == 'CAMERA']

        if not cams:
            camera = DEFAULTS["camera"]

            camera_string = TEMPLATE_CAMERA_PERSPECTIVE % {
            "camera_id" : generate_string(camera["name"]),
            "fov"       : camera["fov"],
            "aspect"    : camera["aspect"],
            "near"      : camera["near"],
            "far"       : camera["far"],
            "position"  : generate_vec3(camera["position"]),
            "target"    : generate_vec3(camera["target"])
            }

            chunks.append(camera_string)

        else:

            render = data["scene"].render
            aspect = render.resolution_x / float(render.resolution_y)

            for cameraobj in cams:
                camera = cameraobj.data
                position = generate_vec3([cameraobj.location[0], -cameraobj.location[1], cameraobj.location[2]], data["flipyz"])

                if camera.type == "PERSP":

                    camera_string = TEMPLATE_CAMERA_PERSPECTIVE % {
                    "camera_id" : generate_string(cameraobj.name),
                    "fov"       : math.degrees(camera.angle),
                    "aspect"    : aspect,
                    "near"      : camera.clip_start,
                    "far"       : camera.clip_end,
                    "position"  : position,
                    "target"    : generate_vec3([0, 0, 0])
                    }

                elif camera.type == "ORTHO":

                    half = camera.ortho_scale / 2.0

                    camera_string = TEMPLATE_CAMERA_ORTHO % {
                    "camera_id" : generate_string(cameraobj.name),
                    "left"      : -half,
                    "right"     : half,
                    "top"       : half / aspect,
                    "bottom"    : -half / aspect,
                    "near"      : camera.clip_start,
                    "far"       : camera.clip_end,
                    "position"  : position,
                    "target"    : generate_vec3([0, 0, 0])
                    }

                else:
                    continue

                chunks.append(camera_string)

    return ",\n\n".join(chunks), len(chunks)

# #####################################################
# Scene exporter - lights
# #####################################################

def generate_lights(data):
    chunks = []

    if data["use_lights"]:
        lamps = [ob for ob in data["objects"] if ob.type == 'LIGHT']

        for lamp in lamps:
            light_string = ""
            concrete_lamp = lamp.data

            distance = 0.0
            if getattr(concrete_lamp, "use_custom_distance", False):
                distance = concrete_lamp.cutoff_distance

            params = {
                "light_id"      : generate_string(concrete_lamp.name),
                "position"      : generate_vec3(lamp.location, data["flipyz"]),
                "rotation"      : generate_vec3(lamp.rotation_euler, data["flipyz"]),
                "color"         : rgb2int(srgb_color(concrete_lamp.color)),
                "distance"      : distance,
                "intensity"     : concrete_lamp.energy * LIGHT_POWER_SCALE
            }

            if concrete_lamp.type == "POINT":
                light_string = TEMPLATE_LIGHT_POINT % params
            elif concrete_lamp.type == "SUN":
                params["intensity"] = concrete_lamp.energy      # sun strength is not in Watts
                light_string = TEMPLATE_LIGHT_SUN % params
            elif concrete_lamp.type == "SPOT":
                params["use_shadow"] = concrete_lamp.use_shadow
                params["angle"] = concrete_lamp.spot_size
                light_string = TEMPLATE_LIGHT_SPOT % params
            elif concrete_lamp.type == "AREA":
                params["gamma"] = 1.0
                params["shape"] = concrete_lamp.shape
                params["size"] = concrete_lamp.size
                params["size_y"] = concrete_lamp.size_y
                light_string = TEMPLATE_LIGHT_AREA % params
            else:
                continue

            chunks.append(light_string)

    return ",\n\n".join(chunks), len(chunks)

# #####################################################
# Scene exporter - embedded meshes
# #####################################################

def generate_embeds(data):

    if data["embed_meshes"]:

        chunks = []

        for e in data["embeds"]:

            embed = '"emb_%s": {%s}' % (e, data["embeds"][e])
            chunks.append(embed)

        return ",\n\n".join(chunks)

    return ""

# #####################################################
# Scene exporter - generate ASCII scene
# #####################################################

def generate_ascii_scene(data):

    objects, nobjects = generate_objects(data)
    geometries, ngeometries = generate_geometries(data)
    textures, ntextures = generate_textures_scene(data)
    materials, nmaterials = generate_materials_scene(data)
    lights, nlights = generate_lights(data)
    cameras, ncameras = generate_cameras(data)

    embeds = generate_embeds(data)

    if nlights > 0:
        if nobjects > 0:
            objects = objects + ",\n\n" + lights
        else:
            objects = lights
        nobjects += nlights

    if ncameras > 0:
        if nobjects > 0:
            objects = objects + ",\n\n" + cameras
        else:
            objects = cameras
        nobjects += ncameras

    basetype = "relativeTo"

    if data["base_html"]:
        basetype += "HTML"
    else:
        basetype += "Scene"

    sections = [
    ["objects",    objects],
    ["geometries", geometries],
    ["textures",   textures],
    ["materials",  materials],
    ["embeds",     embeds]
    ]

    chunks = []
    for label, content in sections:
        if content:
            chunks.append(generate_section(label, content))

    sections_string = "\n".join(chunks)

    default_camera = ""
    if data["use_cameras"]:
        view_layer_objects = bpy.context.view_layer.objects
        cams = [ob for ob in bpy.data.objects
                if ob.type == 'CAMERA' and ob.name in view_layer_objects and ob.select_get()]
        if not cams:
            default_camera = "default_camera"
        else:
            default_camera = cams[0].name

    parameters = {
    "fname"     : data["source_file"],

    "sections"  : sections_string,

    "bgcolor"   : generate_vec3(DEFAULTS["bgcolor"]),
    "bgalpha"   : DEFAULTS["bgalpha"],
    "defcamera" :  generate_string(default_camera),

    "nobjects"      : nobjects,
    "ngeometries"   : ngeometries,
    "ntextures"     : ntextures,
    "basetype"      : generate_string(basetype),
    "nmaterials"    : nmaterials,

    "position"      : generate_vec3(DEFAULTS["position"]),
    "rotation"      : generate_vec3(DEFAULTS["rotation"]),
    "scale"         : generate_vec3(DEFAULTS["scale"])
    }

    text = TEMPLATE_SCENE_ASCII % parameters

    return text

def export_scene(scene, filepath, flipyz, option_colors, option_lights, option_cameras, option_embed_meshes, embeds, option_url_base_html, option_copy_textures):

    source_file = os.path.basename(bpy.data.filepath)

    # objects are contained in the view layer (including linked collections)
    objects = list(bpy.context.view_layer.objects)

    scene_text = ""
    data = {
    "scene"        : scene,
    "objects"      : objects,
    "embeds"       : embeds,
    "source_file"  : source_file,
    "filepath"     : filepath,
    "flipyz"       : flipyz,
    "use_colors"   : option_colors,
    "use_lights"   : option_lights,
    "use_cameras"  : option_cameras,
    "embed_meshes" : option_embed_meshes,
    "base_html"    : option_url_base_html,
    "copy_textures": option_copy_textures
    }
    scene_text += generate_ascii_scene(data)

    write_file(filepath, scene_text)

# #####################################################
# Main
# #####################################################

def save(operator, context, filepath = "",
         option_flip_yz = True,
         option_vertices = True,
         option_vertices_truncate = False,
         option_faces = True,
         option_normals = True,
         option_uv_coords = True,
         option_materials = True,
         option_colors = True,
         option_bones = True,
         option_skinning = True,
         align_model = 0,
         option_export_scene = False,
         option_lights = False,
         option_cameras = False,
         option_scale = 1.0,
         option_embed_meshes = True,
         option_url_base_html = False,
         option_copy_textures = False,
         option_animation_morph = False,
         option_animation_skeletal = False,
         option_frame_step = 1,
         option_all_meshes = True,
         option_frame_index_as_time = False,
         **kwargs):

    filepath = ensure_extension(filepath, '.js')

    scene = context.scene

    if isinstance(align_model, str):
        align_model = ALIGN_MODES.get(align_model, 0)

    active = context.active_object
    if active is not None and active.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    if option_all_meshes:
        sceneobjects = context.view_layer.objects
    else:
        sceneobjects = context.selected_objects

    objects = list(sceneobjects)

    if option_export_scene:

        geo_set = set()
        embeds = {}

        for object in objects:
            if object.type == "MESH" and object.THREE_exportGeometry:

                name = object.data.name

                if name not in geo_set:

                    if option_embed_meshes:

                        text, model_string = generate_mesh_string([object], scene,
                                                        option_vertices,
                                                        option_vertices_truncate,
                                                        option_faces,
                                                        option_normals,
                                                        option_uv_coords,
                                                        option_materials,
                                                        option_colors,
                                                        option_bones,
                                                        option_skinning,
                                                        False,          # align_model
                                                        option_flip_yz,
                                                        option_scale,
                                                        False,          # export_single_model
                                                        False,          # option_copy_textures
                                                        filepath,
                                                        option_animation_morph,
                                                        option_animation_skeletal,
                                                        option_frame_index_as_time,
                                                        option_frame_step)

                        embeds[object.data.name] = model_string

                    else:

                        fname = generate_mesh_filename(name, filepath)
                        export_mesh([object], scene,
                                    fname,
                                    option_vertices,
                                    option_vertices_truncate,
                                    option_faces,
                                    option_normals,
                                    option_uv_coords,
                                    option_materials,
                                    option_colors,
                                    option_bones,
                                    option_skinning,
                                    False,          # align_model
                                    option_flip_yz,
                                    option_scale,
                                    False,          # export_single_model
                                    option_copy_textures,
                                    option_animation_morph,
                                    option_animation_skeletal,
                                    option_frame_step,
                                    option_frame_index_as_time)

                    geo_set.add(name)

        export_scene(scene, filepath,
                     option_flip_yz,
                     option_colors,
                     option_lights,
                     option_cameras,
                     option_embed_meshes,
                     embeds,
                     option_url_base_html,
                     option_copy_textures)

    else:

        export_mesh(objects, scene, filepath,
                    option_vertices,
                    option_vertices_truncate,
                    option_faces,
                    option_normals,
                    option_uv_coords,
                    option_materials,
                    option_colors,
                    option_bones,
                    option_skinning,
                    align_model,
                    option_flip_yz,
                    option_scale,
                    True,            # export_single_model
                    option_copy_textures,
                    option_animation_morph,
                    option_animation_skeletal,
                    option_frame_step,
                    option_frame_index_as_time)

    return {'FINISHED'}
