# 도담도담 캐릭터 공정: Meshy 리깅본(body_B3_rigged.glb)에 안경·가발을 머리 뼈(mixamorig:Head)에 붙이고 걷기·뛰기·손흔들기 자세로 렌더해 따라오는지 확인.
# 실행: Blender -b --factory-startup -P rig_check.py -- MESHY_DIR OUT_DIR  (MESHY_DIR에 body_B3_textured.glb, body_B3_rigged.glb, master/, glasses/, wig_lite_on_b3/)
import bpy, sys, math, os, json
import numpy as np
from mathutils import Vector, Matrix
D, OUT = sys.argv[-2], sys.argv[-1]; os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
def load(p):
    b=set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=p); return [o for o in bpy.data.objects if o not in b]
# 기준 몸(B3 텍스처본) 크기
ref=[o for o in load(D+"/body_B3_textured.glb") if o.type=='MESH'][0]
R0=np.array([ref.matrix_world@v.co for v in ref.data.vertices]); 
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
objs=load(D+"/body_B3_rigged.glb")
arm=[o for o in objs if o.type=='ARMATURE'][0]; body=[o for o in objs if o.type=='MESH' and o.name.startswith('geometry')][0]
ico=[o for o in objs if o.type=='MESH' and o.name.startswith('Icosphere')]
arm.data.pose_position='REST'; bpy.context.view_layer.update()
dg=bpy.context.evaluated_depsgraph_get(); be=body.evaluated_get(dg); me=be.to_mesh()
P=np.array([body.matrix_world@v.co for v in me.vertices]); be.to_mesh_clear()
info={}
info["ref_bbox"]=[R0.min(0).round(3).tolist(),R0.max(0).round(3).tolist()]
info["rig_bbox"]=[P.min(0).round(3).tolist(),P.max(0).round(3).tolist()]
s=(P[:,2].max()-P[:,2].min())/(R0[:,2].max()-R0[:,2].min())
off=Vector(((P.min(0)+P.max(0))/2 - s*(R0.min(0)+R0.max(0))/2).tolist())
# 앞 방향 비교: 코/얼굴 쪽이 -Y인지
info["scale"]=round(float(s),4)
for o in ico: info["ico"]=dict(loc=[round(x,3) for x in o.matrix_world.translation], dim=[round(x,3) for x in o.dimensions], parent=o.parent.name if o.parent else None, ptype=o.parent_type, pbone=o.parent_bone)
vg=body.vertex_groups; W={g.name:0 for g in vg}
for v in body.data.vertices:
    for g in v.groups:
        if g.weight>0.01: W[vg[g.group].name]+=1
info["extra_bones"]={b.name:dict(parent=b.parent.name if b.parent else None, verts=W.get(b.name,0)) for b in arm.data.bones if not b.name.startswith("mixamorig")}
info["head_verts"]=W.get("mixamorig:Head",0)
print("INFO",json.dumps(info))
mj=json.load(open(D+"/master/master_head.json")); C=Vector(mj["center_body"]); Rr=mj["radius_body"]
M2B=Matrix.Translation(off)@Matrix.Scale(s,4)@Matrix.Translation(C)@Matrix.Scale(Rr/0.5,4)
arm.data.pose_position='POSE'; bpy.context.view_layer.update()
hb=arm.pose.bones["mixamorig:Head"]
def attach(o):
    W0=o.matrix_world.copy()
    o.parent=arm; o.parent_type='BONE'; o.parent_bone="mixamorig:Head"
    bpy.context.view_layer.update()
    o.matrix_world=W0
g=[o for o in load(D+"/glasses/glasses.glb") if o.type=='MESH']
for o in g:
    o.matrix_world=M2B@o.matrix_world; o.hide_render=(o.name!="glasses_square")
wig=[o for o in load(D+"/wig_lite_on_b3/ponytail.glb") if o.type=='MESH'][0]; wig.matrix_world=M2B@wig.matrix_world
hm=bpy.data.materials.new("h"); hm.use_nodes=True; hm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value=(0.06,0.03,0.02,1)
wig.data.materials.clear(); wig.data.materials.append(hm)
# 붙이기 전 rest 자세 기준으로 위치 맞춤
arm.data.pose_position='REST'; bpy.context.view_layer.update()
for o in g+[wig]: attach(o)
arm.data.pose_position='POSE'
for o in ico: o.hide_render=True
for o in [body,wig]+g:
    bpy.context.view_layer.objects.active=o
sc=bpy.context.scene; sc.render.engine='CYCLES'; sc.cycles.samples=16; sc.cycles.use_denoising=True
sc.render.resolution_x,sc.render.resolution_y=300,400; sc.render.film_transparent=True; sc.view_settings.view_transform='Standard'
w=bpy.data.worlds.new("w"); sc.world=w; w.use_nodes=True; w.node_tree.nodes["Background"].inputs[1].default_value=0.9
l=bpy.data.lights.new("k",'SUN'); l.energy=3; lo=bpy.data.objects.new("k",l); lo.rotation_euler=(0.8,0,-0.5); sc.collection.objects.link(lo)
cam=bpy.data.objects.new("c",bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera=cam; cam.data.type='ORTHO'
zmin,zmax=P[:,2].min(),P[:,2].max(); H=zmax-zmin; cam.data.ortho_scale=H*1.35
plan=[("Walking",6,25),("Walking",18,-25),("Big_Wave_Hello",40,0),("Big_Wave_Hello",70,35),("Running",4,30),("Big_Wave_Hello",70,90)]
for k,(act,f,yaw) in enumerate(plan):
    arm.animation_data.action=bpy.data.actions[act]; sc.frame_set(int(bpy.data.actions[act].frame_range[0])+f)
    a=math.radians(yaw); cam.location=(6*math.sin(a),-6*math.cos(a),(zmin+zmax)/2+0.1*H); cam.rotation_euler=(math.pi/2,0,a)
    sc.render.filepath=os.path.join(OUT,f"a{k}.png"); bpy.ops.render.render(write_still=True)
print("DONE")
