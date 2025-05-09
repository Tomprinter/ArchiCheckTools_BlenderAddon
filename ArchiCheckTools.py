import bpy
import os
import re
import bmesh
from mathutils import Vector
from bpy.types import Operator, Panel
from bpy.props import StringProperty, FloatProperty

bl_info = {
    "name": "建筑模型检修工具1.4",
    "author": "蒲贇涛",
    "version": (1, 4),
    "blender": (4, 4, 0),
    "location": "3D视图 > 工具面板",
    "description": "https://github.com/Tomprinter/ArchiCheckTools_BlenderAddon",
    "category": "工具",
}

# ==================== 通用工具函数 ====================
def clear_scene_data(purge_orphans=True):
    """清空场景数据"""
    # 删除所有物体
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=True)
    
    # 清理残留数据
    for data_type in ('meshes', 'materials', 'textures', 'images','collections'):
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


def purge_unused_data():
    """清理所有未使用的数据块"""
#删除所有物体
#    bpy.ops.object.select_all(action='SELECT')
#    bpy.ops.object.delete(use_global=True)

    # 定义需要清理的数据类型
    data_types = [
        'materials', 'textures',
        'images', 'brushes', 'particles',
        'actions', 'fonts', 'node_groups',
        'armatures', 'curves', 'lattices',
        'metaballs', 'grease_pencils', 'cameras',
        'speakers', 'lights', 'lightprobes',
        'collections', 'worlds'
    ]

    # 遍历所有数据类型
    for data_type in data_types:
        data_collection = getattr(bpy.data, data_type)
        # 创建列表避免在遍历时修改集合
        for item in list(data_collection):
            if item.users == 0:
                try:
                    data_collection.remove(item)
                except Exception as e:
                    print(f"Error removing {data_type}: {item.name} - {str(e)}")

    # 执行Blender内置的孤立数据清理（推荐方式）
    for _ in range(3):
        bpy.ops.outliner.orphans_purge(do_recursive=True)


# ==================== 新增基础功能面板 ====================
class BASE_OT_ClearScene(Operator):
    """清空场景"""
    bl_idname = "base.clear_scene"
    bl_label = "清空场景"
    
    def execute(self, context):
        clear_scene_data()
        return {'FINISHED'}

class BASE_OT_ImportFBX(Operator):
    """导入FBX文件"""
    bl_idname = "base.import_fbx"
    bl_label = "导入FBX"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: StringProperty(subtype='FILE_PATH')
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        bpy.ops.import_scene.fbx(filepath=self.filepath)
        return {'FINISHED'}

class BASE_OT_ProtectMaterials(Operator):
    """保护所有材质贴图"""
    bl_idname = "base.protect_materials"
    bl_label = "保护材质贴图"
    
    def execute(self, context):
        # 保护材质
        for mat in bpy.data.materials:
            mat.use_fake_user = True
        # 保护贴图
        for tex in bpy.data.textures:
            tex.use_fake_user = True
        # 保护图像
        for img in bpy.data.images:
            img.use_fake_user = True
        self.report({'INFO'}, "所有材质和贴图已保护")
        return {'FINISHED'}

class BASE_OT_PurgeUnused(Operator):
    """清理未使用数据"""
    bl_idname = "base.purge_unused"
    bl_label = "清理未使用数据"
    
    def execute(self, context):
        purge_unused_data()
        return {'FINISHED'}

class BASE_PT_Panel(Panel):
    bl_label = "基础功能"
    bl_idname = "VIEW3D_PT_base_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "综合工具"


    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="场景管理", icon='WORLD')
        box.operator("base.clear_scene", icon='TRASH')
        box.operator("base.import_fbx", icon='IMPORT')
        
        box = layout.box()
        box.label(text="数据保护", icon='MATERIAL')
        box.operator("base.protect_materials", text="保护材质贴图")
        box.operator("base.purge_unused", text="清理未使用数据")


# ==================== 1. UV处理工具 ====================
class UVTOOLS_OT_BatchProcess(Operator):
    bl_idname = "uvtools.batch_process"
    bl_label = "批量处理FBX文件"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        a_folder_UV = bpy.path.abspath(scene.a_folder_UV)
        b_folder_UV = bpy.path.abspath(scene.b_folder_UV)

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
                    output_path = os.path.join(b_folder_UV, f"{base_name}.fbx")
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

        if not os.path.isdir(a_folder_UV):
            self.report({'ERROR'}, f"无效输入路径: {a_folder_UV}")
            return {'CANCELLED'}

        os.makedirs(b_folder_UV, exist_ok=True)
        fbx_files = [f for f in os.listdir(a_folder_UV) if f.lower().endswith('.fbx')]
        
        if not fbx_files:
            self.report({'ERROR'}, "没有找到FBX文件")
            return {'CANCELLED'}

        success = 0
        for fbx in fbx_files:
            if process_single_fbx(os.path.join(a_folder_UV, fbx)):
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
        box.prop(scene, "a_folder_UV", text="输入目录")
        box.prop(scene, "b_folder_UV", text="输出目录")
        
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
        scene = context.scene
        # 根据复选框状态过滤要处理的贴图类型
        texture_types = []
        if scene.connect_basecolor:
            texture_types.append(('BaseColor', 'Base Color', False, True))
        if scene.connect_metallic:
            texture_types.append(('Metallic', 'Metallic', False, False))
        if scene.connect_roughness:
            texture_types.append(('Roughness', 'Roughness', False, False)) 
        if scene.connect_normal:
            texture_types.append(('Normal', 'Normal', True, False))

        def connect_textures(c_path_TEX):
            valid_ext = {'.png', '.jpg', '.jpeg', '.tga', '.tif', '.tiff'}
            for mat in bpy.data.materials:
                if not mat.use_nodes:
                    continue
                
                principled = next((n for n in mat.node_tree.nodes 
                                 if isinstance(n, bpy.types.ShaderNodeBsdfPrincipled)), None)
                if not principled:
                    continue

                # 新增BaseColor处理
                for suffix, input_name, is_normal, is_color in texture_types:  # 使用动态列表
                    tex_path = None
                    base_name = f"{mat.name}_{suffix}"
                    
                    # 支持多种命名变体
                    naming_variants = [
                        f"{mat.name}_{suffix}",
                        f"{mat.name}_{suffix.lower()}",
                        f"{mat.name}_{suffix.upper()}"
                    ]
                    
                    # 扫描匹配文件
                    for f in os.listdir(c_path_TEX):
                        fname, fext = os.path.splitext(f)
                        if fext.lower() not in valid_ext:
                            continue
                            
                        # 检查所有可能的命名变体
                        if any(fname.startswith(variant) for variant in naming_variants):
                            tex_path = os.path.join(c_path_TEX, f)
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
            connect_textures(bpy.path.abspath(context.scene.c_path_TEX))
            self.report({'INFO'}, "贴图连接完成!")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

# ==================== 贴图断开功能 ====================
class TEXTURE_OT_DisconnectTextures(Operator):
    bl_idname = "texture.disconnect_textures"
    bl_label = "断连材质贴图"
    bl_description = "断开指定类型的贴图连接并调整法线强度"
    
    def process_single_fbx(self, input_path, output_dir, context):
        try:
            clear_scene_data(purge_orphans=False)
            # 导入FBX
            bpy.ops.import_scene.fbx(filepath=input_path)
            
            # 处理所有材质
            for mat in bpy.data.materials:
                if not mat.use_nodes:
                    continue
                
                nodes = mat.node_tree.nodes
                links = mat.node_tree.links
                principled = next((n for n in nodes if isinstance(n, bpy.types.ShaderNodeBsdfPrincipled)), None)
                if not principled:
                    continue

                # 处理各贴图类型
                if context.scene.disconnect_basecolor:
                    self.disconnect_socket(principled, 'Base Color', nodes, links)
                if context.scene.disconnect_metallic:
                    self.disconnect_socket(principled, 'Metallic', nodes, links)
                if context.scene.disconnect_roughness:
                    self.disconnect_socket(principled, 'Roughness', nodes, links)
                if context.scene.disconnect_normal:
                    self.disconnect_socket(principled, 'Normal', nodes, links)
                if context.scene.disconnect_alpha:
                    self.disconnect_socket(principled, 'Alpha', nodes, links)
                    principled.inputs['Alpha'].default_value = 1.0


            # 导出处理后的FBX
            output_path = os.path.join(output_dir, os.path.basename(input_path))
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            bpy.ops.export_scene.fbx(
                filepath=output_path,
                path_mode='COPY',
                embed_textures=True
            )
            return True
        except Exception as e:
            self.report({'ERROR'}, f"处理 {input_path} 失败: {str(e)}")
            return False
        finally:
            clear_scene_data()

    def disconnect_socket(self, principled, socket_name, nodes, links):
        """断开指定插槽的连接并清理节点"""
        socket = principled.inputs.get(socket_name)
        if not socket:
            return
        
            
        
        # 通用节点链处理
        visited_nodes = set()
        stack = []
        
        # 初始化栈
        if socket.is_linked:
            initial_node = socket.links[0].from_node
            stack.append(initial_node)

        # 深度优先遍历节点链
        while stack:
            current_node = stack.pop()
            if current_node in visited_nodes:
                continue
            visited_nodes.add(current_node)

            # 收集上游节点
            for input_socket in current_node.inputs:
                for link in input_socket.links:
                    upstream_node = link.from_node
                    if upstream_node not in visited_nodes:
                        stack.append(upstream_node)

            # 安全移除节点
            try:
                # 断开所有输出连接
                for output_socket in current_node.outputs:
                    for link in output_socket.links:
                        links.remove(link)
                
                # 移除节点
                if current_node in nodes:
                    nodes.remove(current_node)
            except Exception as e:
                print(f"移除节点时出错: {str(e)}")

        # 确保最终断开目标插槽
        while socket.links:
            links.remove(socket.links[0])

    def execute(self, context):
        input_dir = bpy.path.abspath(context.scene.d_path_TEX)
        output_dir = bpy.path.abspath(context.scene.e_path_TEX)
        
        if not os.path.isdir(input_dir):
            self.report({'ERROR'}, "无效输入路径")
            return {'CANCELLED'}
        
        processed_count = 0
        error_count = 0
        
        # 遍历所有子目录中的FBX文件
        for root, dirs, files in os.walk(input_dir):
            for file in files:
                if file.lower().endswith('.fbx'):
                    input_path = os.path.join(root, file)
                    # 保持目录结构
                    relative_path_TEX = os.path.relpath(root, input_dir)
                    output_subdir = os.path.join(output_dir, relative_path_TEX)
                    
                    if self.process_single_fbx(input_path, output_subdir, context):
                        processed_count += 1
                    else:
                        error_count += 1
        
        self.report({'INFO'}, f"处理完成! 成功: {processed_count}, 失败: {error_count}")
        return {'FINISHED'}

class TEXTURE_PT_Panel(Panel):
    bl_label = "2.贴图工具"
    bl_idname = "VIEW3D_PT_texture_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "综合工具"


    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        box = layout.box()
        box.label(text="贴图路径设置", icon='TEXTURE')
        box.prop(scene, "c_path_TEX", text="贴图目录")
        
        # 添加贴图类型选择
        box = layout.box()
        box.label(text="选择贴图类型", icon='CHECKBOX_HLT')
        row = box.row()
        row.prop(scene, "connect_basecolor", text="BaseColor", toggle=True)
        row.prop(scene, "connect_metallic", text="Metallic", toggle=True)
        row = box.row()
        row.prop(scene, "connect_roughness", text="Roughness", toggle=True)
        row.prop(scene, "connect_normal", text="Normal", toggle=True)
        
        box.operator("texture.connect_textures", icon='MATERIAL')

        # 新增断连贴图部分
        box = layout.box()
        box.label(text="断开贴图连接", icon='MATERIAL')
        box.prop(scene, "d_path_TEX", text="输入目录")
        box.prop(scene, "e_path_TEX", text="输出目录")
        
        box = layout.box()
        box.label(text="选择断开类型", icon='CHECKBOX_HLT')
        row = box.row()
        row.prop(scene, "disconnect_basecolor", text="BaseColor", toggle=True)
        row.prop(scene, "disconnect_metallic", text="Metallic", toggle=True)
        row = box.row()
        row.prop(scene, "disconnect_roughness", text="Roughness", toggle=True)
        row.prop(scene, "disconnect_normal", text="Normal", toggle=True)
        row = box.row()
        row.prop(scene, "disconnect_alpha", text="Alpha", toggle=True)
        
        box.operator("texture.disconnect_textures", icon='MATERIAL')

# ==================== 3. 材质处理工具 ====================
class MATERIAL_OT_ProcessMaterials(Operator):
    bl_idname = "material.process_materials"
    bl_label = "处理材质和法线"

    def execute(self, context):
        def process_fbx_files(a_path_MAT, b_path_MAT):
            pattern = re.compile(r"\.\d{3}$")
            os.makedirs(b_path_MAT, exist_ok=True)
            purge_unused_data()

            for fbx_name in [f for f in os.listdir(a_path_MAT) if f.lower().endswith(".fbx")]:

                input_path = os.path.join(a_path_MAT, fbx_name)
                output_path = os.path.join(b_path_MAT, fbx_name)
                
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
                purge_unused_data()

        try:
            process_fbx_files(
                bpy.path.abspath(context.scene.a_path_MAT),
                bpy.path.abspath(context.scene.b_path_MAT)
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
        box.prop(scene, "a_path_MAT", text="输入目录")
        box.prop(scene, "b_path_MAT", text="输出目录")
        
        box.operator("material.process_materials", icon='MODIFIER')

# ==================== 注册与属性 ====================
def register():
    # 注册所有类
    classes = (
        BASE_OT_ClearScene,
        BASE_OT_ImportFBX,
        BASE_OT_ProtectMaterials,
        BASE_OT_PurgeUnused,
        BASE_PT_Panel,
        UVTOOLS_OT_BatchProcess,
        UVTOOLS_PT_Panel,
#        TEXTURE_OT_ImportFBX,
#        TEXTURE_OT_ClearScene,
        TEXTURE_OT_ConnectTextures,
        TEXTURE_PT_Panel,
        TEXTURE_OT_DisconnectTextures,
        MATERIAL_OT_ProcessMaterials,
        MATERIAL_PT_Panel,
        

    )
    for cls in classes:
        bpy.utils.register_class(cls)

    # 场景属性
    scene = bpy.types.Scene
    scene.a_folder_UV = StringProperty(
        name="输入目录",
        description="UV处理输入文件夹",
        subtype='DIR_PATH'
    )
    scene.b_folder_UV = StringProperty(
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
    scene.c_path_TEX = StringProperty(
        name="贴图路径",
        default="D:/puyuntao/archi/UV_edit_Building_Assets/textures_original",
        subtype='DIR_PATH',
        description="材质贴图存储目录"
    )
    scene.a_path_MAT = StringProperty(
        name="输入路径",
        default="D:/puyuntao/archi/UV_edit_Building_Assets/UVOK",
        subtype='DIR_PATH',
        description="材质处理输入目录"
    )
    scene.b_path_MAT = StringProperty(
        name="输出路径",
        default="D:/puyuntao/archi/UV_edit_Building_Assets/output",
        subtype='DIR_PATH',
        description="材质处理输出目录"
    )

    # 添加贴图类型选择属性
    scene = bpy.types.Scene
    scene.connect_basecolor = bpy.props.BoolProperty(
        name="连接BaseColor",
        default=True,
        description="是否连接BaseColor贴图"
    )
    scene.connect_metallic = bpy.props.BoolProperty(
        name="连接Metallic",
        default=True,
        description="是否连接Metallic贴图"
    )
    scene.connect_roughness = bpy.props.BoolProperty(
        name="连接Roughness",
        default=True,
        description="是否连接Roughness贴图"
    )
    scene.connect_normal = bpy.props.BoolProperty(
        name="连接Normal",
        default=True,
        description="是否连接Normal贴图"
    )

    # 添加断开贴图属性
    scene = bpy.types.Scene
    scene.d_path_TEX = bpy.props.StringProperty(
        name="输入路径",
        subtype='DIR_PATH',
        description="断连贴图输入目录"
    )
    scene.e_path_TEX = bpy.props.StringProperty(
        name="输出路径",
        subtype='DIR_PATH',
        description="断连贴图输出目录"
    )
    scene.disconnect_basecolor = bpy.props.BoolProperty(
        name="断开BaseColor",
        default=True
    )
    scene.disconnect_metallic = bpy.props.BoolProperty(
        name="断开Metallic",
        default=True
    )
    scene.disconnect_roughness = bpy.props.BoolProperty(
        name="断开Roughness",
        default=True
    )
    scene.disconnect_normal = bpy.props.BoolProperty(
        name="断开Normal",
        default=True
    )
    scene.disconnect_alpha = bpy.props.BoolProperty(
        name="断开Alpha",
        default=True,
        description="断开Alpha贴图并设置值为1"
    )

def unregister():
    # 注销所有类
    classes = (
        BASE_OT_ClearScene,
        BASE_OT_ImportFBX,
        BASE_OT_ProtectMaterials,
        BASE_OT_PurgeUnused,
        BASE_PT_Panel,
        UVTOOLS_OT_BatchProcess,
        UVTOOLS_PT_Panel,
 #        TEXTURE_OT_ImportFBX,
 #        TEXTURE_OT_ClearScene,
        TEXTURE_OT_ConnectTextures,
        TEXTURE_PT_Panel,
        TEXTURE_OT_DisconnectTextures,
        MATERIAL_OT_ProcessMaterials,
        MATERIAL_PT_Panel,

    )
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    # 删除属性
    scene = bpy.types.Scene
    del scene.a_folder_UV
    del scene.b_folder_UV
    del scene.project_scale
    del scene.target_material_name
    del scene.c_path_TEX
    del scene.a_path_MAT
    del scene.b_path_MAT
    
    # 删除新增属性
    scene = bpy.types.Scene
    del scene.connect_basecolor
    del scene.connect_metallic
    del scene.connect_roughness
    del scene.connect_normal

    # 删除贴图断连属性
    scene = bpy.types.Scene
    del scene.d_path_TEX
    del scene.e_path_TEX
    del scene.disconnect_basecolor
    del scene.disconnect_metallic 
    del scene.disconnect_roughness
    del scene.disconnect_normal
    del scene.disconnect_alpha

if __name__ == "__main__":
    register()
