import bpy, sys, math, os
import numpy as np
from mathutils import Vector
MD, WIG, FACE, OUT, NAME = sys.argv[-5:]
def srgb(h):
    c=[int(h[i:i+2],16)/255 for i in (1,3,5)]; return [x/12.92 if x<=0.04045 else ((x+0.055)/1.055)**2.4 for x in c]+[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
def load(p):
    b=set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=p); return [o for o in bpy.data.objects if o not in b and o.type=='MESH']
head=load(MD+"/master_head.glb")[0]; me=head.data
P=np.array([v.co[:] for v in me.vertices])
# 헤어라인(정면 0도 → 뒤 180도) 높이: 이마 → 관자놀이 → 귀 앞 구레나룻 → 귀 위 → 목덜미
KN=[(0,0.30),(40,0.27),(60,0.17),(70,0.02),(80,-0.11),(86,-0.11),(92,0.06),(105,0.10),(135,0.0),(180,-0.30)]
th=np.degrees(np.abs(np.arctan2(P[:,0],-P[:,1])))
zh=np.interp(th,[k[0] for k in KN],[k[1] for k in KN])
t=np.clip((P[:,2]-zh)/0.06+0.5,0,1); t=t*t*(3-2*t)
r=np.linalg.norm(P,axis=1); t[r>0.52]=0      # 귀 제외
ca=me.color_attributes.new("scalp",'FLOAT_COLOR','POINT')
for i,v in enumerate(ca.data): v.color=(t[i],t[i],t[i],1)
uv=me.uv_layers.new(name="face")
for poly in me.polygons:
    for li in poly.loop_indices:
        v=P[me.loops[li].vertex_index]; uv.data[li].uv=(0.5+v[0],0.5+v[2]) if v[1]<0.2 else (0.001,0.001)
m=bpy.data.materials.new("skin"); m.use_nodes=True; nt=m.node_tree; bs=nt.nodes["Principled BSDF"]; bs.inputs["Roughness"].default_value=0.6
att=nt.nodes.new("ShaderNodeAttribute"); att.attribute_name="scalp"
mt=nt.nodes.new("ShaderNodeMath"); mt.operation='MULTIPLY'; mt.inputs[1].default_value=0.75   # 깎은 머리 색 진하기
tint=nt.nodes.new("ShaderNodeMix"); tint.data_type='RGBA'; tint.inputs[6].default_value=srgb("#F2C9AC"); tint.inputs[7].default_value=srgb("#4A3226")
nt.links.new(att.outputs["Fac"],mt.inputs[0]); nt.links.new(mt.outputs[0],tint.inputs[0])
un=nt.nodes.new("ShaderNodeUVMap"); un.uv_map="face"; tx=nt.nodes.new("ShaderNodeTexImage"); tx.extension='CLIP'; tx.image=bpy.data.images.load(FACE); tx.image.alpha_mode='STRAIGHT'
fm=nt.nodes.new("ShaderNodeMix"); fm.data_type='RGBA'
nt.links.new(un.outputs[0],tx.inputs[0]); nt.links.new(tx.outputs["Alpha"],fm.inputs[0]); nt.links.new(tint.outputs[2],fm.inputs[6]); nt.links.new(tx.outputs["Color"],fm.inputs[7]); nt.links.new(fm.outputs[2],bs.inputs["Base Color"])
me.materials.clear(); me.materials.append(m)
objs=[head]
if WIG!="-":
    w=load(WIG)[0]; hm=bpy.data.materials.new("hair"); hm.use_nodes=True; hb=hm.node_tree.nodes["Principled BSDF"]; hb.inputs["Base Color"].default_value=srgb("#4A3226"); hb.inputs["Roughness"].default_value=0.65
    w.data.materials.clear(); w.data.materials.append(hm); objs.append(w)
for o in objs:
    bpy.context.view_layer.objects.active=o; o.select_set(True); bpy.ops.object.shade_smooth(); o.select_set(False)
sc=bpy.context.scene; sc.render.engine='CYCLES'; sc.cycles.samples=32; sc.cycles.use_denoising=True
sc.render.resolution_x=sc.render.resolution_y=500; sc.render.film_transparent=True; sc.view_settings.view_transform='Standard'
wd=bpy.data.worlds.new("w"); sc.world=wd; wd.use_nodes=True; wd.node_tree.nodes["Background"].inputs[1].default_value=0.6
for loc,e in (((-2,-4,2),260),((3,-3,0.5),110),((0,3,3),120)):
    l=bpy.data.lights.new("k",'AREA'); l.energy=e; l.size=4; lo=bpy.data.objects.new("k",l); lo.location=loc; sc.collection.objects.link(lo)
    lo.rotation_euler=(Vector((0,0,0))-lo.location).to_track_quat('-Z','Y').to_euler()
cam=bpy.data.objects.new("c",bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera=cam; cam.data.type='ORTHO'; cam.data.ortho_scale=1.5
for vn,yaw in (("front",0),("45",40),("side",90),("back",180)):
    a=math.radians(yaw); cam.location=(6*math.sin(a),-6*math.cos(a),0.05); cam.rotation_euler=(math.pi/2,0,a)
    sc.render.filepath=os.path.join(OUT,f"{NAME}_{vn}.png"); bpy.ops.render.render(write_still=True)
print("SCALP done")
