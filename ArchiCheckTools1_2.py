import bpy
import os
import re
import bmesh
from mathutils import Vector
from bpy.types import Operator, Panel
from bpy.props import StringProperty, FloatProperty

bl_info = {
    "name": "建筑模型检修工具1.2",
    "author": "蒲贇涛",
    "version": (1, 2),
    "blender": (4, 4, 0),
    "location": "3D视图 > 工具面板",
    "description": "https://github.com/Tomprinter/ArchiCheckTools_BlenderAddon",
    "category": "工具"
}

# ==================== 通用工具函数 ====================
def clear_scene_data(purge_orphans=True):
    """安全清空场景数据"""
    # 删除所有物体
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=True)
    
    # 清理残留数据
    for data_type in ('meshes', 'materials', 'textures', 'images'):
        data_collection = getattr(bpy.data, data_type)
        for item in data_collection:
            try:
                data_collection.remove(item)
            except ReferenceError:
                pass
    
    # 清理孤立数据
    if purge_orphans:
        for _ in range(3):
            bpy.ops.outliner.orphans_purge(do_recursive=True)

# ==================== 1. UV处理工具 ====================
class UVTOOLS_OT_BatchProcess(Operator):
    bl_idname = "uvtools.batch_process"
    bl_label = "批量处理FBX文件"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        A_FOLDER = bpy.path.abspath(scene.a_folder)
        B_FOLDER = bpy.path.abspath(scene.b_folder)

        def process_single_fbx(fbx_path):
            clear_scene_data(purge_orphans=False)
            try:
                bpy.ops.import_scene.fbx(filepath=fbx_path)
                base_name = os.path.splitext(os.path.basename(fbx_path))[0]
                success_count = 0

                for obj in context.scene.objects:
                    if obj.type != 'MESH':
                        continue

                    target_indices = [
                        i for i, slot in enumerate(obj.material_slots)
                        if slot.material and slot.material.name == scene.target_material_name
                    ]

                    if not target_indices:
                        continue

                    bpy.context.view_layer.objects.active = obj
                    obj.select_set(True)
                    bpy.ops.object.mode_set(mode='EDIT')

                    bm = bmesh.from_edit_mesh(obj.data)
                    selected = 0
                    for face in bm.faces:
                        face.select = face.material_index in target_indices
                        if face.select:
                            selected += 1

                    if selected > 0:
                        z_height = obj.dimensions.z
                        bpy.ops.uv.cube_project(
                            cube_size=z_height / scene.project_scale,
                            correct_aspect=True,
                            clip_to_bounds=False,
                            scale_to_bounds=False
                        )
                        success_count += 1

                    bpy.ops.object.mode_set(mode='OBJECT')

                if success_count > 0:
                    output_path = os.path.join(B_FOLDER, f"{base_name}.fbx")
                    bpy.ops.export_scene.fbx(
                        filepath=output_path,
                        path_mode='COPY', 
                       embed_textures=True  # 新增嵌入贴图
                    )
                    return True

            except Exception as e:
                self.report({'ERROR'}, str(e))
            finally:
                clear_scene_data()
            return False

        if not os.path.isdir(A_FOLDER):
            self.report({'ERROR'}, f"无效输入路径: {A_FOLDER}")
            return {'CANCELLED'}

        os.makedirs(B_FOLDER, exist_ok=True)
        fbx_files = [f for f in os.listdir(A_FOLDER) if f.lower().endswith('.fbx')]
        
        if not fbx_files:
            self.report({'ERROR'}, "没有找到FBX文件")
            return {'CANCELLED'}

        success = 0
        for fbx in fbx_files:
            if process_single_fbx(os.path.join(A_FOLDER, fbx)):
                success += 1

        self.report({'INFO'}, f"完成! 成功处理 {success}/{len(fbx_files)} 个文件")
        return {'FINISHED'}

class UVTOOLS_PT_Panel(Panel):
    bl_label = "1.对目标材质的面展UV"
    bl_idname = "VIEW3D_PT_uv_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "综合工具"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        box = layout.box()
        box.prop(scene, "a_folder", text="输入目录")
        box.prop(scene, "b_folder", text="输出目录")
        
        box = layout.box()
        box.prop(scene, "target_material_name", text="目标材质")
        box.prop(scene, "project_scale", slider=True)
        
        layout.operator("uvtools.batch_process", icon='EXPORT')

# ==================== 2. 贴图工具 ====================
class TEXTURE_OT_ConnectTextures(Operator):
    bl_idname = "texture.connect_textures"
    bl_label = "连接材质贴图"
    bl_description = "自动连接BaseColor/Metallic/Roughness/Normal贴图"

    def execute(self, context):
        def connect_textures(c_path):
            valid_ext = {'.png', '.jpg', '.jpeg', '.tga', '.tif', '.tiff'}
            for mat in bpy.data.materials:
                if not mat.use_nodes:
                    continue
                
                principled = next((n for n in mat.node_tree.nodes 
                                 if isinstance(n, bpy.types.ShaderNodeBsdfPrincipled)), None)
                if not principled:
                    continue

                # 新增BaseColor处理
                for suffix, input_name, is_normal, is_color in [
                    ('BaseColor', 'Base Color', False, True),  # 新增项
                    ('Metallic', 'Metallic', False, False),
                    ('Roughness', 'Roughness', False, False),
                    ('Normal', 'Normal', True, False)
                ]:
                    tex_path = None
                    base_name = f"{mat.name}_{suffix}"
                    
                    # 支持多种命名变体
                    naming_variants = [
                        f"{mat.name}_{suffix}",
                        f"{mat.name}_{suffix.lower()}",
                        f"{mat.name}_{suffix.upper()}"
                    ]
                    
                    # 扫描匹配文件
                    for f in os.listdir(c_path):
                        fname, fext = os.path.splitext(f)
                        if fext.lower() not in valid_ext:
                            continue
                            
                        # 检查所有可能的命名变体
                        if any(fname.startswith(variant) for variant in naming_variants):
                            tex_path = os.path.join(c_path, f)
                            break
                    
                    if tex_path:
                        # 创建纹理节点
                        tex_image = mat.node_tree.nodes.new('ShaderNodeTexImage')
                        tex_image.image = bpy.data.images.load(tex_path)
                        
                        # 设置颜色空间
                        if not is_normal:
                            if is_color:
                                tex_image.image.colorspace_settings.name = 'sRGB'
                            else:
                                tex_image.image.colorspace_settings.name = 'Non-Color'
                        else:
                            tex_image.image.colorspace_settings.name = 'Non-Color'
                        
                        # 创建NormalMap节点（仅限法线贴图）
                        if is_normal:
                            normal_node = mat.node_tree.nodes.new('ShaderNodeNormalMap')
                            mat.node_tree.links.new(
                                tex_image.outputs['Color'],
                                normal_node.inputs['Color']
                            )
                            mat.node_tree.links.new(
                                normal_node.outputs['Normal'],
                                principled.inputs[input_name]
                            )
                        else:
                            mat.node_tree.links.new(
                                tex_image.outputs['Color'],
                                principled.inputs[input_name]
                            )
                        
                        # 自动排列节点
                        offset_x = -600 if is_normal else -400
                        offset_y = 200 * (['BaseColor', 'Metallic', 'Roughness', 'Normal'].index(suffix))
                        tex_image.location = (principled.location.x + offset_x, 
                                            principled.location.y + offset_y)

        try:
            connect_textures(bpy.path.abspath(context.scene.c_path))
            self.report({'INFO'}, "贴图连接完成!")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

class TEXTURE_OT_ConnectTextures(Operator):
    bl_idname = "texture.connect_textures"
    bl_label = "连接材质贴图"
    bl_description = "自动连接Metallic/Roughness/Normal贴图"

    def execute(self, context):
        def connect_textures(c_path):
            valid_ext = {'.png', '.jpg', '.jpeg', '.tga', '.tif', '.tiff'}
            for mat in bpy.data.materials:
                if not mat.use_nodes:
                    continue
                
                principled = next((n for n in mat.node_tree.nodes 
                                 if isinstance(n, bpy.types.ShaderNodeBsdfPrincipled)), None)
                if not principled:
                    continue

                for suffix, input_name, is_normal in [
                    ('Metallic', 'Metallic', False),
                    ('Roughness', 'Roughness', False),
                    ('Normal', 'Normal', True)
                ]:
                    tex_path = None
                    base_name = f"{mat.name}_{suffix}"
                    
                    for f in os.listdir(c_path):
                        if f.startswith(base_name) and os.path.splitext(f)[1].lower() in valid_ext:
                            tex_path = os.path.join(c_path, f)
                            break
                    
                    if tex_path:
                        tex_image = mat.node_tree.nodes.new('ShaderNodeTexImage')
                        tex_image.image = bpy.data.images.load(tex_path)
                        
                        if is_normal:
                            tex_image.image.colorspace_settings.name = 'Non-Color'
                            normal_node = mat.node_tree.nodes.new('ShaderNodeNormalMap')
                            mat.node_tree.links.new(
                                tex_image.outputs['Color'],
                                normal_node.inputs['Color']
                            )
                            mat.node_tree.links.new(
                                normal_node.outputs['Normal'],
                                principled.inputs[input_name]
                            )
                        else:
                            mat.node_tree.links.new(
                                tex_image.outputs['Color'],
                                principled.inputs[input_name]
                            )

        try:
            connect_textures(bpy.path.abspath(context.scene.c_path))
            self.report({'INFO'}, "贴图连接完成!")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

class TEXTURE_PT_Panel(Panel):
    bl_label = "2贴图查找"
    bl_idname = "VIEW3D_PT_texture_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "综合工具"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        box = layout.box()
        box.label(text="贴图路径设置", icon='TEXTURE')
        box.prop(scene, "c_path", text="贴图目录")
        
        # 操作按钮列
        col = box.column(align=True)
#        col.operator("texture.import_fbx", icon='IMPORT')
        col.operator("texture.connect_textures", icon='MATERIAL')
#        col.operator("texture.clear_scene", icon='TRASH')

# ==================== 3. 材质处理工具 ====================
class MATERIAL_OT_ProcessMaterials(Operator):
    bl_idname = "material.process_materials"
    bl_label = "处理材质和法线"

    def execute(self, context):
        def process_fbx_files(a_path, b_path):
            pattern = re.compile(r"\.\d{3}$")
            os.makedirs(b_path, exist_ok=True)
            
            for fbx_name in [f for f in os.listdir(a_path) if f.lower().endswith(".fbx")]:
                clear_scene_data()
                input_path = os.path.join(a_path, fbx_name)
                output_path = os.path.join(b_path, fbx_name)
                
                bpy.ops.import_scene.fbx(filepath=input_path)
                
                # 材质处理
                for mat in list(bpy.data.materials):
                    if pattern.search(mat.name):
                        base_name = pattern.sub("", mat.name)
                        if base_mat := bpy.data.materials.get(base_name):
                            for obj in bpy.data.objects:
                                if obj.type == 'MESH':
                                    for slot in obj.material_slots:
                                        if slot.material == mat:
                                            slot.material = base_mat
                            bpy.data.materials.remove(mat)
                
                # 法线处理（兼容4.4+版本）
                for obj in context.scene.objects:
                    if obj.type == 'MESH':
                        # 处理自定义法线
                        if hasattr(obj.data, "has_custom_normals"):
                            if obj.data.has_custom_normals:
                                bpy.context.view_layer.objects.active = obj
                                bpy.ops.object.mode_set(mode='EDIT')
                                bpy.ops.mesh.customdata_custom_splitnormals_clear()
                                bpy.ops.object.mode_set(mode='OBJECT')
                        
                        # 设置自动平滑（兼容不同版本）
                        mesh = obj.data
                        if hasattr(mesh, "use_auto_smooth"):
                            # 4.3及以下版本
                            mesh.use_auto_smooth = False
                        elif hasattr(mesh, "auto_smooth_enable"):
                            # 4.4+版本
                            mesh.auto_smooth_enable = False
                        
                        # 禁用面平滑
                        for poly in mesh.polygons:
                            poly.use_smooth = False
                
                bpy.ops.export_scene.fbx(
                    filepath=output_path,
                    embed_textures=True,
                    path_mode='COPY', 
                )
                clear_scene_data()

        try:
            process_fbx_files(
                bpy.path.abspath(context.scene.a_path),
                bpy.path.abspath(context.scene.b_path)
            )
            self.report({'INFO'}, "处理完成!")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

class MATERIAL_PT_Panel(Panel):
    bl_label = "3.材质替换，删除自定义法向数据并改为平直着色"
    bl_idname = "VIEW3D_PT_material_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "综合工具"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        box = layout.box()
        box.prop(scene, "a_path", text="输入目录")
        box.prop(scene, "b_path", text="输出目录")
        
        box.operator("material.process_materials", icon='MODIFIER')

# ==================== 注册与属性 ====================
def register():
    # 注册所有类
    classes = (
        UVTOOLS_OT_BatchProcess,
        UVTOOLS_PT_Panel,
#        TEXTURE_OT_ImportFBX,
#        TEXTURE_OT_ClearScene,
        TEXTURE_OT_ConnectTextures,
        TEXTURE_PT_Panel,
        MATERIAL_OT_ProcessMaterials,
        MATERIAL_PT_Panel,
    )
    for cls in classes:
        bpy.utils.register_class(cls)

    # 场景属性
    scene = bpy.types.Scene
    scene.a_folder = StringProperty(
        name="输入目录",
        description="UV处理输入文件夹",
        subtype='DIR_PATH'
    )
    scene.b_folder = StringProperty(
        name="输出目录",
        description="UV处理输出文件夹",
        subtype='DIR_PATH'
    )
    scene.project_scale = FloatProperty(
        name="投射比例", 
        default=10.0, 
        min=0.1, 
        max=100.0,
        description="UV投影缩放比例"
    )
    scene.target_material_name = StringProperty(
        name="目标材质",
        default="T_Glass_Clear_White_001",
        description="需要处理的材质名称"
    )
    scene.c_path = StringProperty(
        name="贴图路径",
        default="D:/puyuntao/archi/UV_edit_Building_Assets/textures_original",
        subtype='DIR_PATH',
        description="材质贴图存储目录"
    )
    scene.a_path = StringProperty(
        name="输入路径",
        default="D:/puyuntao/archi/UV_edit_Building_Assets/UVOK",
        subtype='DIR_PATH',
        description="材质处理输入目录"
    )
    scene.b_path = StringProperty(
        name="输出路径",
        default="D:/puyuntao/archi/UV_edit_Building_Assets/output",
        subtype='DIR_PATH',
        description="材质处理输出目录"
    )

def unregister():
    # 注销所有类
    classes = (
        UVTOOLS_OT_BatchProcess,
        UVTOOLS_PT_Panel,
 #        TEXTURE_OT_ImportFBX,
 #        TEXTURE_OT_ClearScene,
        TEXTURE_OT_ConnectTextures,
        TEXTURE_PT_Panel,
        MATERIAL_OT_ProcessMaterials,
        MATERIAL_PT_Panel,
    )
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    # 删除属性
    scene = bpy.types.Scene
    del scene.a_folder
    del scene.b_folder
    del scene.project_scale
    del scene.target_material_name
    del scene.c_path
    del scene.a_path
    del scene.b_path

if __name__ == "__main__":
    register()