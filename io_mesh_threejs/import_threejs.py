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
Blender importer for Three.js (ASCII JSON format). Blender 2.92+.
"""

import os
import time
import json
import bpy
from bpy_extras.image_utils import load_image

# #####################################################
# Utils
# #####################################################

def srgb_to_linear(c):
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4

def hexToTuple(hexColor):
    r = ((hexColor >> 16) & 0xff) / 255.0
    g = ((hexColor >> 8) & 0xff) / 255.0
    b = (hexColor & 0xff) / 255.0
    return (r, g, b)

def isBitSet(value, position):
    return value & (1 << position)

def splitArray(data, chunkSize):
    result = []
    chunk = []
    for i in range(len(data)):
        if i > 0 and i % chunkSize == 0:
            result.append(chunk)
            chunk = []
        chunk.append(data[i])
    result.append(chunk)
    return result

def extract_json_string(text):
    marker_begin = "var model ="
    marker_end = "postMessage"

    start = text.find(marker_begin) + len(marker_begin)
    end = text.find(marker_end)
    end = text.rfind("}", start, end)
    return text[start:end + 1].strip()

def get_name(filepath):
    return os.path.splitext(os.path.basename(filepath))[0]

def get_path(filepath):
    return os.path.dirname(filepath)

# #####################################################
# Materials
# #####################################################

def create_materials(data, modelpath):
    materials = []
    materials_data = data.get("materials", [])

    for i, m in enumerate(materials_data):

        name = m.get("DbgName", "material_%d" % i)

        colorDiffuse = m.get("colorDiffuse", None)
        colorSpecular = m.get("colorSpecular", None)
        alpha = m.get("transparency", 1.0)
        specular_hardness = m.get("specularCoef", 0)

        mapDiffuse = m.get("mapDiffuse", None)

        material = bpy.data.materials.new(name)
        material.THREE_useVertexColors = bool(m.get("vertexColors", False))

        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)

        if bsdf is not None:

            if colorDiffuse:
                rgb = [srgb_to_linear(c) for c in colorDiffuse[:3]]
                bsdf.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
                material.diffuse_color = (rgb[0], rgb[1], rgb[2], 1.0)

            if colorSpecular:
                bsdf.inputs["Specular"].default_value = min(1.0, max(colorSpecular[:3]))

            if specular_hardness:
                # inverse of the exporter's roughness -> shininess mapping
                bsdf.inputs["Roughness"].default_value = min(1.0, (2.0 / (specular_hardness + 2.0)) ** 0.25)

            if alpha < 1.0:
                bsdf.inputs["Alpha"].default_value = alpha
                material.blend_method = 'BLEND'

            if mapDiffuse:
                image = load_image(mapDiffuse, modelpath)
                if image:
                    tex = nodes.new('ShaderNodeTexImage')
                    tex.image = image
                    tex.location = (bsdf.location.x - 350, bsdf.location.y)
                    links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
                    if alpha < 1.0:
                        links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])

        materials.append(material)

    return materials

# #####################################################
# Mesh
# #####################################################

def create_mesh_object(name, vertices, materials, face_data, flipYZ, recalculate_normals):

    faces         = face_data["faces"]
    vertexNormals = face_data["vertexNormals"]
    vertexColors  = face_data["vertexColors"]
    vertexUVs     = face_data["vertexUVs"]
    faceMaterials = face_data["materials"]
    faceColors    = face_data["faceColors"]

    me = bpy.data.meshes.new(name)
    me.from_pydata(vertices, [], faces)
    me.update(calc_edges=True)

    polygons = me.polygons

    # Normals

    if face_data["hasVertexNormals"]:

        print("setting vertex normals")

        for fi in range(len(faces)):
            if vertexNormals[fi]:
                polygons[fi].use_smooth = True

        if not recalculate_normals:

            custom = [(0.0, 0.0, 0.0)] * len(vertices)

            for fi, face in enumerate(faces):
                if vertexNormals[fi]:
                    for j, vi in enumerate(face):
                        x, y, z = vertexNormals[fi][j]
                        if flipYZ:
                            y, z = -z, y
                        custom[vi] = (x, y, z)

            me.use_auto_smooth = True
            me.normals_split_custom_set_from_vertices(custom)

    # Vertex colors

    if face_data["hasVertexColors"] or face_data["hasFaceColors"]:

        print("setting vertex colors")

        layer = me.vertex_colors.new(name="vertex_color_layer_0")

        for fi, poly in enumerate(polygons):

            if vertexColors[fi]:
                colors = vertexColors[fi]
            elif faceColors[fi]:
                colors = [faceColors[fi]] * len(poly.loop_indices)
            else:
                continue

            for k, li in enumerate(poly.loop_indices):
                if k < len(colors):
                    r, g, b = [srgb_to_linear(c) for c in colors[k]]
                    layer.data[li].color = (r, g, b, 1.0)

    # UVs

    if face_data["hasVertexUVs"]:

        print("setting vertex uvs")

        for layer_index, layer in enumerate(vertexUVs):

            uv_layer = me.uv_layers.new(name="uv_layer_%d" % layer_index)

            for fi, poly in enumerate(polygons):

                if layer[fi]:
                    for k, li in enumerate(poly.loop_indices):
                        if k < len(layer[fi]):
                            u, v = layer[fi][k]
                            uv_layer.data[li].uv = (u, v)

    # Materials

    if face_data["hasMaterials"]:

        print("setting materials")

        for m in materials:
            me.materials.append(m)

        for fi, poly in enumerate(polygons):
            if 0 <= faceMaterials[fi] < len(materials):
                poly.material_index = faceMaterials[fi]

    # Create object and link it into the active collection

    ob = bpy.data.objects.new(name, me)

    context = bpy.context
    context.collection.objects.link(ob)
    ob.location = context.scene.cursor.location

    ob.select_set(True)
    context.view_layer.objects.active = ob

# #####################################################
# Faces
# #####################################################

def extract_faces(data):

    result = {
    "faces"         : [],
    "materials"     : [],
    "faceUVs"       : [],
    "vertexUVs"     : [],
    "faceNormals"   : [],
    "vertexNormals" : [],
    "faceColors"    : [],
    "vertexColors"  : [],

    "hasVertexNormals"  : False,
    "hasVertexUVs"      : False,
    "hasVertexColors"   : False,
    "hasFaceColors"     : False,
    "hasMaterials"      : False
    }

    faces = data.get("faces", [])
    normals = data.get("normals", [])
    colors = data.get("colors", [])
    uvs = data.get("uvs", [])

    offset = 0
    zLength = len(faces)

    # disregard empty arrays

    nUvLayers = 0

    for layer in uvs:
        if len(layer) > 0:
            nUvLayers += 1
            result["faceUVs"].append([])
            result["vertexUVs"].append([])

    while offset < zLength:

        type = faces[offset]
        offset += 1

        isQuad              = isBitSet(type, 0)
        hasMaterial         = isBitSet(type, 1)
        hasFaceUv           = isBitSet(type, 2)
        hasFaceVertexUv     = isBitSet(type, 3)
        hasFaceNormal       = isBitSet(type, 4)
        hasFaceVertexNormal = isBitSet(type, 5)
        hasFaceColor        = isBitSet(type, 6)
        hasFaceVertexColor  = isBitSet(type, 7)

        result["hasVertexUVs"] = result["hasVertexUVs"] or hasFaceVertexUv
        result["hasVertexNormals"] = result["hasVertexNormals"] or hasFaceVertexNormal
        result["hasVertexColors"] = result["hasVertexColors"] or hasFaceVertexColor
        result["hasFaceColors"] = result["hasFaceColors"] or hasFaceColor
        result["hasMaterials"] = result["hasMaterials"] or hasMaterial

        # vertices

        nVertices = 4 if isQuad else 3

        face = faces[offset:offset + nVertices]
        offset += nVertices

        result["faces"].append(face)

        # material

        if hasMaterial:
            materialIndex = faces[offset]
            offset += 1
        else:
            materialIndex = -1

        result["materials"].append(materialIndex)

        # uvs

        for i in range(nUvLayers):

            faceUv = None
            vertexUvs = None

            if hasFaceUv:
                uvLayer = uvs[i]
                uvIndex = faces[offset]
                offset += 1
                faceUv = [uvLayer[uvIndex * 2], uvLayer[uvIndex * 2 + 1]]

            result["faceUVs"][i].append(faceUv)

            if hasFaceVertexUv:
                uvLayer = uvs[i]
                vertexUvs = []

                for j in range(nVertices):
                    uvIndex = faces[offset]
                    offset += 1
                    vertexUvs.append([uvLayer[uvIndex * 2], uvLayer[uvIndex * 2 + 1]])

            result["vertexUVs"][i].append(vertexUvs)

        # normals

        if hasFaceNormal:
            normalIndex = faces[offset] * 3
            offset += 1
            faceNormal = [normals[normalIndex], normals[normalIndex + 1], normals[normalIndex + 2]]
        else:
            faceNormal = None

        result["faceNormals"].append(faceNormal)

        if hasFaceVertexNormal:
            vertexNormals = []

            for j in range(nVertices):
                normalIndex = faces[offset] * 3
                offset += 1
                vertexNormals.append([normals[normalIndex], normals[normalIndex + 1], normals[normalIndex + 2]])
        else:
            vertexNormals = None

        result["vertexNormals"].append(vertexNormals)

        # colors

        if hasFaceColor:
            colorIndex = faces[offset]
            offset += 1
            faceColor = hexToTuple(colors[colorIndex])
        else:
            faceColor = None

        result["faceColors"].append(faceColor)

        if hasFaceVertexColor:
            vertexColors = []

            for j in range(nVertices):
                colorIndex = faces[offset]
                offset += 1
                vertexColors.append(hexToTuple(colors[colorIndex]))
        else:
            vertexColors = None

        result["vertexColors"].append(vertexColors)

    return result

# #####################################################
# Parser
# #####################################################

def load(operator, context, filepath, option_flip_yz=True, recalculate_normals=True, option_worker=False, **kwargs):

    print('\nimporting %r' % filepath)

    time_main = time.time()

    print("\tparsing JSON file...")

    time_sub = time.time()

    with open(filepath, 'r', encoding='utf-8') as file:
        rawcontent = file.read()

    if option_worker:
        json_string = extract_json_string(rawcontent)
    else:
        json_string = rawcontent
    data = json.loads(json_string)

    time_new = time.time()
    print('parsing %.4f sec' % (time_new - time_sub))

    # flip YZ

    vertices = splitArray(data["vertices"], 3)

    if option_flip_yz:
        vertices[:] = [(v[0], -v[2], v[1]) for v in vertices]

    # extract faces

    face_data = extract_faces(data)

    # deselect all

    for ob in list(context.selected_objects):
        ob.select_set(False)

    nfaces = len(face_data["faces"])
    nvertices = len(vertices)
    nnormals = len(data.get("normals", [])) // 3
    ncolors = len(data.get("colors", []))
    nuvs = sum(len(layer) // 2 for layer in data.get("uvs", []))
    nmaterials = len(data.get("materials", []))

    print('\tbuilding geometry...\n\tfaces:%i, vertices:%i, vertex normals: %i, vertex uvs: %i, vertex colors: %i, materials: %i ...' % (
        nfaces, nvertices, nnormals, nuvs, ncolors, nmaterials))

    # Create materials

    materials = create_materials(data, get_path(filepath))

    # Create new obj

    create_mesh_object(get_name(filepath), vertices, materials, face_data, option_flip_yz, recalculate_normals)

    context.view_layer.update()

    print('finished importing: %r in %.4f sec.' % (filepath, (time.time() - time_main)))
    return {'FINISHED'}
