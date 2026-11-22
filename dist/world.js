/* Boston's fixed street grid and low-poly harbor diorama. */
(() => {
  "use strict";
  const T = window.THREE;
  function mount(container,{onPoint,onHover,getTool,onRoadStart,onRoadEnd,onRoadCancel}) {
    const scene=new T.Scene();
    scene.background = new T.Color(0x7ba9ba);
    const camera=new T.OrthographicCamera(-2000,2000,1600,-1600,1,30000);
    const renderer=new T.WebGLRenderer({antialias:true,alpha:false,powerPreference:"low-power"});
    renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
    renderer.shadowMap.enabled=true;
    renderer.shadowMap.type=T.PCFSoftShadowMap;
    renderer.domElement.style.cssText="width:100%;height:100%;display:block;touch-action:none";
    renderer.domElement.tabIndex=0;
    renderer.domElement.setAttribute("aria-label","Boston map. Select a road and click endpoints or drag. Deselect tools to pan. Scroll to zoom. Arrow keys move the cursor. Enter places a road endpoint.");
    container.appendChild(renderer.domElement);
    scene.add(new T.HemisphereLight(0xfff7df,0xb4c9bf,1.8));
    const sun=new T.DirectionalLight(0xfff1d8,2.3);
    sun.position.set(-1500,4000,1800);sun.castShadow=true;
    Object.assign(sun.shadow.camera,{left:-2200,right:2200,top:2000,bottom:-2000,far:10000});
    sun.shadow.mapSize.set(2048,2048);sun.shadow.normalBias=.05;sun.shadow.bias=-.00015;
    scene.add(sun);
    const geometries={box:new T.BoxGeometry(1,1,1), round:new T.CylinderGeometry(1,1,1,12), roof:new T.ConeGeometry(1,1,4), pine:new T.ConeGeometry(1,1,7), crown:new T.IcosahedronGeometry(1,0), dome:new T.SphereGeometry(1,10,4,0,Math.PI*2,0,Math.PI/2)};
    const material=new T.MeshStandardMaterial({roughness:1,flatShading:true});
    let pending=[], origin=null, yaw=0, modelScale=1;
    function part(shape,x,y,z,w,h,d,color,yaw=0) {
      const object=new T.Object3D();
      if(origin){const dx=(x-origin.x)*modelScale,dz=(z-origin.z)*modelScale;x=origin.x+dx*Math.cos(origin.rotation||0)+dz*Math.sin(origin.rotation||0);z=origin.z-dx*Math.sin(origin.rotation||0)+dz*Math.cos(origin.rotation||0);y=.8+(y-.8)*modelScale;w*=modelScale;h*=modelScale;d*=modelScale;yaw+=origin.rotation||0;}
      object.position.set(x,y,z);object.rotation.y=yaw;object.scale.set(w,h,d);object.updateMatrix();
      pending.push({shape,matrix:object.matrix,color});
    }
    const box=(x,y,z,w,h,d,c,r=0)=>part("box",x,y,z,w,h,d,c,r);
    function flush() {
      const group=new T.Group();
      Object.keys(geometries).forEach(shape=>{
        const batch=pending.filter(v=>v.shape===shape);
        if (!batch.length)return;
        const mesh=new T.InstancedMesh(geometries[shape],material,batch.length);
        batch.forEach((v,i)=>{mesh.setMatrixAt(i,v.matrix);mesh.setColorAt(i,new T.Color(v.color));});
        mesh.castShadow=true;mesh.receiveShadow=true;group.add(mesh);
      });
      pending=[];scene.add(group);return group;
    }
    let seed=1082;
    const rand=()=>((seed=Math.imul(seed,1664525)+1013904223>>>0)/4294967296);
    function tree(x,z,h=2.6,color=0x63965c) {
      box(x,1,z,.30,1.24,.30,0x80593d);
      part("crown",x,1.17+h*.37,z,h*.38,h*.47,h*.36,color,x);
      part("crown",x+.25,1.4+h*.57,z+.05,h*.28,h*.34,h*.28,color,z);
    }
    function pine(x,z,h) {
      box(x,1,z,.25,1.2,.25,0x855f4b);
      part("pine",x,1.5,z,1.1,h*.72,1.1,0x396e60);
      part("pine",x,2.4,z,.86,h*.68,.86,0x53856c);
    }
    function windows(x,z,w,h,d,floors,cols) {
      for(let row=0;row<floors;row++)for(let col=0;col<cols;col++)
        box(x + (col+.5-cols/2)*w/cols,.9+(row+.48)*h/floors,z+d/2+.035,w/cols*.43,h/floors*.48,.08,0x536867);
      for(let row=0;row<floors;row++) for(let col=0;col<2;col++)
        box(x+w/2+.03,.9+(row+.48)*h/floors,z+(col-.5)*d*.45,.08,h/floors*.48,d*.2,0x597578);
    }
    function house(x,z,w,h,d,wall,roof) {
      box(x,.84+h/2,z,w,h,d,wall);windows(x,z,w,h,d,Math.max(1,Math.round(h/1.65)),Math.max(2,Math.round(w/1.3)));
      part("roof",x,.83+h+.58,z,w*.76,1.22,d*.76,roof,Math.PI/4);
      box(x+.6,h+1.6,z,.48,1,.47,wall);
    }
    function civic(x,z) {
      box(x,1,z,7.8,.5,6.2,0xdbd1ad);
      box(x,2.6,z,6.7,3,4.7,0xc28468);windows(x,z,6.7,3,4.7,2,6);
      box(x,4.22,z,7.1,.35,5.1,0xefddbd);
      box(x,4.57,z,6.8,.45,4.7,0x677570);
      for(let i=-2;i<=2;i++)part("round",x+i*.73,2.67,z+2.65,.18,2.87,.18,0xffe8bd);
      box(x,4.2,z+2.72,4.1,.36,1.4,0xf8eac9);
      part("round",x,5.1,z,1.65,.82,1.65,0xebd9ae);
      part("dome",x,5.45,z,1.76,1.75,1.76,0xdba348);
      part("round",x,7.37,z,.23,.52,.23,0xe8c977);part("pine",x,7.91,z,.21,.75,.21,0x566766);
    }
    function landmark(cell) {
      const {x,z,site}=cell;
      if(site==="statehouse")civic(x,z);
      if(site==="hall"){
        // Boston City Hall's brick plinth, recessed middle and concrete upper galleries.
        box(x,1.25,z,7.5,.9,6.6,0xb78b72);
        box(x,2.55,z,5.6,1.8,4.65,0xaf7e67);
        for(const i of [-2.6,0,2.6]) box(x+i,2.66,z+2.55,.54,2.05,.88,0xc0b7a0);
        box(x,4.1,z,7.7,1.15,6.25,0xc9bea6);
        box(x,4.87,z,7.48,.52,6.05,0x677b78);
        for(let i=0;i<9;i++)box(x-3.45+i*.86,4.86,z+2.98,.20,1.06,.31,0xd4cbb5);
        for(let i=0;i<7;i++)box(x+3.72,4.85,z-2.6+i*.87,.28,1.05,.21,0xd4cbb5);
        box(x,5.38,z,7.75,.45,6.26,0xd7cdb7);
        box(x-.5,5.65,z-.15,3,.38,2.2,0x9da99d);
      }
      if(site==="garden") {
        box(x,2,z,7.7,2.4,6.2,0xa48361);
        box(x,3.28,z,8,.45,6.55,0x616f72);
        box(x,3.62,z,6.5,.45,5.3,0x9da9a7);
        for(let j=-2;j<=2;j++)box(x+j*1.2,3.88,z,.13,.15,5,0xc7cebf);
        windows(x,z,7.7,2.4,6.2,1,7);
      }
      if(site==="hospital"){
        box(x-.8,3.6,z,4.5,5.6,4.6,0xdbd6b9);windows(x-.8,z,4.5,5.6,4.6,4,4);
        box(x-.8,6.5,z,4.8,.38,4.9,0x81968f);
        box(x+2.25,2.10,z+.6,2.1,2.6,4,0xacbea8);
        box(x-.8,6.73,z,1.8,.1,.57,0xc95748);box(x-.8,6.74,z,.57,.1,1.8,0xc95748);
      }
      if(site==="church"){
        house(x,z+.2,3.5,3.2,5.1,0xe5d9b7,0x4f625e);
        box(x,4.05,z+2.2,1.6,6.7,1.5,0xf5ead4);
        for(let j=-1;j<=1;j++)box(x+j*.38,6.8,z+2.99,.18,.74,.08,0x657470);
        part("roof",x,9.1,z+2.2,1.25,3.7,1.2,0x61736b,Math.PI/4);
      }
      if(site==="market"){house(x,z,6.8,2.3,3.6,0xc4ad88,0x687e71);part("dome",x,4.1,z,1.36,1.48,1.36,0x80a294);}
      if(site==="common"){
        for(let i=0;i<7;i++)tree(x-3.6+(i%4)*2.3,z-2.2+Math.floor(i/4)*4,2.2+rand()*1.4);
        box(x,1,z,6,.16,1.1,0xc7c99d);
      }
    }
    const terrainMaterial=new T.MeshStandardMaterial({color:0xa5b992,roughness:1,flatShading:true});
    function landShape(poly,holes=[]) {
      const shape=new T.Shape(poly.map(p=>new T.Vector2(p.x,-p.z)));
      for(const hole of holes)shape.holes.push(new T.Path(hole.map(p=>new T.Vector2(p.x,-p.z))));
      const geo=new T.ExtrudeGeometry(shape,{depth:12,bevelEnabled:false,curveSegments:1});
      geo.rotateX(-Math.PI/2);geo.translate(0,-12,0);
      const mesh=new T.Mesh(geo,terrainMaterial);mesh.receiveShadow=true;scene.add(mesh);
      const line=new T.LineLoop(new T.BufferGeometry().setFromPoints(poly.map(p=>new T.Vector3(p.x,.1,p.z))),new T.LineBasicMaterial({color:0xd0c9ab}));scene.add(line);
    }
    CityPlan.polygons.forEach((poly,i)=>landShape(poly,CityPlan.holes[i]));
    box(0,-14,0,18000,1,18000,0x6598ac);
    for(const c of CityPlan.landmarks) {
      origin=c;modelScale=c.scale||8;landmark(c);origin=null;modelScale=1;
    }
    flush();
    const guard=new T.Mesh(new T.RingGeometry(CITY_HALL.radius-1,CITY_HALL.radius,100),new T.MeshBasicMaterial({color:0xf1d181,side:T.DoubleSide,transparent:true,opacity:.8,depthWrite:false}));
    guard.rotation.x=-Math.PI/2;guard.position.set(CITY_HALL.x,1.1,CITY_HALL.z);scene.add(guard);
    const preview=new T.Mesh(new T.PlaneGeometry(1,1),new T.MeshBasicMaterial({color:0xf6df9d,transparent:true,opacity:.5,side:T.DoubleSide,depthWrite:false}));
    preview.rotation.x=-Math.PI/2;preview.visible=false;scene.add(preview);
    const frontArrow=new T.ArrowHelper(new T.Vector3(0,0,1),new T.Vector3(0,2,0),10,0xf2cd68,4,3);frontArrow.visible=false;scene.add(frontArrow);
    let previewLine=null;
    const labelsLayer=document.createElement('div');labelsLayer.className='maplabels';container.append(labelsLayer);
    let labels=[];
    function refreshLabels(){labelsLayer.replaceChildren();labels=[...CityPlan.landmarks,...CityPlan.plan.buildings.filter(b=>b.area)].map(l=>{const el=document.createElement('span');el.textContent=l.name||l.label;labelsLayer.append(el);return {el,point:new T.Vector3(l.x,35,l.z)};});}
    refreshLabels();
    let fog=null;
    function drawFog(){
      disposeGroup(fog);const b=CityPlan.activeBounds;
      box((b.minX-9000)/2,160,0,b.minX+9000,2,18000,0x3c5960);
      box((b.maxX+9000)/2,160,0,9000-b.maxX,2,18000,0x3c5960);
      box((b.minX+b.maxX)/2,160,(b.minZ-9000)/2,b.maxX-b.minX,2,b.minZ+9000,0x3c5960);
      box((b.minX+b.maxX)/2,160,(b.maxZ+9000)/2,b.maxX-b.minX,2,9000-b.maxZ,0x3c5960);
      fog=flush();fog.children.forEach(m=>{m.castShadow=false;m.receiveShadow=false;});
    }
    drawFog();
    let roadsGroup=null;
    function drawRoads() {
      disposeGroup(roadsGroup);
      for(const r of CityPlan.plan.roads){
        const length=CityPlan.dist(r.a,r.b),x=(r.a.x+r.b.x)/2,z=(r.a.z+r.b.z)/2;
        const angle=-Math.atan2(r.b.z-r.a.z,r.b.x-r.a.x),w=CityPlan.widths[r.type];
        if(r.bridge){
          const n=Math.ceil(length/5);
          for(let i=0;i<n;i++){
            const t=(i+.5)/n,p={x:r.a.x+(r.b.x-r.a.x)*t,z:r.a.z+(r.b.z-r.a.z)*t},y=CityPlan.heightAt(p,r);
            box(p.x,y-.3,p.z,length/n+.2,1.3,w+2.4,0xb9b9a7,angle);
            box(p.x,y+.5,p.z,length/n+.2,.15,w,0x59666a,angle);
            for(const side of [-1,1])box(p.x+Math.sin(angle)*side*(w/2+1),y+2,p.z+Math.cos(angle)*side*(w/2+1),length/n+.2,1.5,.45,0xe0dfc5,angle);
          }
          for(let t=35;t<length-15;t+=65){
            const p={x:r.a.x+(r.b.x-r.a.x)*t/length,z:r.a.z+(r.b.z-r.a.z)*t/length},y=CityPlan.heightAt(p,r);
            box(p.x,(y-14)/2,p.z,3.2,y+14,w*.75,0x7c9292,angle);
          }
        }else{
          box(x,.2,z,length,.4,w+2.4,0xb7b5a5,angle);
          box(x,.5,z,length,.15,w,0x59666a,angle);
        }
        const line=(offset,color,dashed)=>{
          for(let t=2;t<length-1;t+=dashed?10:4){
            const d=Math.min(dashed?4:4.1,length-t),px=r.a.x+(r.b.x-r.a.x)*(t+d/2)/length,pz=r.a.z+(r.b.z-r.a.z)*(t+d/2)/length;
            box(px+Math.sin(angle)*offset,.62+CityPlan.heightAt({x:px,z:pz},r),pz+Math.cos(angle)*offset,d,.04,.2,color,angle);
          }
        };
        line(-w/2+.35,0xe7dfb8,false);line(w/2-.35,0xe7dfb8,false);
        if(r.type==='highway'){line(0,0xd4b957,false);line(-w/4,0xd9dfda,true);line(w/4,0xd9dfda,true);}
        else if(r.type==='twoway')line(0,0xe0ce9b,true);
        else {
          for(let t=10;t<length-4;t+=24){
            const x=r.a.x+(r.b.x-r.a.x)*t/length,z=r.a.z+(r.b.z-r.a.z)*t/length;
            box(x,.65+CityPlan.heightAt({x,z},r),z,3,.04,.25,0xf4e9c3,angle);
            for(const sign of [-1,1])box(x+Math.cos(angle)*.9+Math.sin(angle)*sign*.45,.65+CityPlan.heightAt({x,z},r),z-Math.sin(angle)*.9+Math.cos(angle)*sign*.45,1.6,.04,.22,0xf4e9c3,angle+sign*.65);
          }
        }
      }
      for(const building of CityPlan.plan.buildings){
        const connection=CityPlan.access(building),s=CityPlan.buildingScale(building.type),angle=building.rotation||0;
        const entrance={x:building.x+Math.sin(angle)*(building.radius||s*2.5),z:building.z+Math.cos(angle)*(building.radius||s*2.5)};
        box(entrance.x,1.1,entrance.z,8,.5,8,connection?0xf5d176:0xe98649,angle);
        if(connection){
          const p=connection.p,length=connection.length,rotation=-Math.atan2(p.z-entrance.z,p.x-entrance.x);
          const n=Math.max(1,Math.ceil(length/3)),endHeight=CityPlan.heightAt(p,connection.road);
          for(let i=0;i<n;i++){const t=(i+.5)/n;box(entrance.x+(p.x-entrance.x)*t,.7+endHeight*t,entrance.z+(p.z-entrance.z)*t,length/n+.1,.15,2.4,0xe5dac0,rotation);}
        }else{
          part('pine',building.x,12,building.z,2,3,2,0xe98649);
        }
      }
      roadsGroup=flush();
    }
    let buildingMesh=null,people=null,agentCount=0;
    function drawBuilding(type,c) {
      const {x,z}=c;
      if(type==="residential"){
        house(x-1.62,z-.1,2.55,2.8,3.65,0xd8b89c,0xa45d47);house(x+1.25,z+.27,2.55,2.6,3.8,0xc78e6f,0x617770);
      } else if(type==="office"){
        box(x,3.5,z,4.6,5.4,4.1,0x96aeb2);windows(x,z,4.6,5.4,4.1,4,4);box(x,6.28,z,4.9,.27,4.4,0x576e72);
        box(x-.5,6.6,z-.4,1.5,.57,1.05,0x8a9693);
      } else if(type==="shop"||type==="social"){
        house(x,z,5.1,2.32,3.55,type==="shop"?0xe3be8c:0xd8a397,type==="shop"?0xa4644d:0x757287);
        for(let i=0;i<8;i++)box(x-2.27+i*.65,2.45,z+2.11,.67,.19,1.21,i%2?0xf1dfb7:(type==="shop"?0xb85d43:0x617b8c));
      } else if(type==="park"){
        box(x,.87,z,1.2,.1,6.8,0xdace9a);tree(x+2,z-1.4);pine(x-1.6,z-1.5,3.8);tree(x-1.8,z+2,2.9);
        box(x+1.6,1.15,z+1,1.6,.34,.55,0x9e7858);
      } else if(type==="parking"){
        box(x,.88,z,6.3,.14,6.3,0x798789);
        for(let i=0;i<5;i++)box(x-2.6+i*1.3,.97,z+1.6,.085,.025,2.3,0xf1edcb);
        for(let i=0;i<3;i++){box(x-1.95+i*1.3,1.19,z+1.35,.85,.5,1.83,[0xc47058,0xe6ce94,0x789fa4][i]);}
      }
    }
    function disposeGroup(g) {if(g){scene.remove(g);g.children.forEach(m=>m.dispose());}}
    let cursor={x:0,z:500};
    let scale=1,tilt=false,pan={x:(CityPlan.activeBounds.minX+CityPlan.activeBounds.maxX)/2,z:(CityPlan.activeBounds.minZ+CityPlan.activeBounds.maxZ)/2},lastRevision=-1,drag=null,roadDrag=null,moved=false;
    const ray=new T.Raycaster(),pos=new T.Vector2(),ground=new T.Plane(new T.Vector3(0,1,0),0);
    function pick(e) {
      const r=renderer.domElement.getBoundingClientRect();
      pos.set((e.clientX-r.left)/r.width*2-1,1-(e.clientY-r.top)/r.height*2);ray.setFromCamera(pos,camera);
      const v=new T.Vector3();return ray.ray.intersectPlane(ground,v)?{x:v.x,z:v.z}:null;
    }
    renderer.domElement.addEventListener('pointerdown',e=>{
      const tool=getTool();
      if(e.button===1||e.button===2||e.shiftKey||(e.button===0&&tool.pan)){
        e.preventDefault();drag={point:pick(e)};moved=false;renderer.domElement.style.cursor='grabbing';renderer.domElement.setPointerCapture(e.pointerId);
      }else if(e.button===0&&tool.dragRoad){
        const p=pick(e);if(p){e.preventDefault();roadDrag=p;onRoadStart(p);renderer.domElement.setPointerCapture(e.pointerId);}
      }
    });
    renderer.domElement.addEventListener('pointermove',e=>{
      const p=pick(e);
      if(drag&&p){pan.x+=drag.point.x-p.x;pan.z+=drag.point.z-p.z;resize();moved=true;}
      else if(p)onHover?.(p);
    });
    renderer.domElement.addEventListener('pointerup',e=>{
      if(roadDrag){const p=pick(e);roadDrag=null;moved=true;if(p)onRoadEnd(p);else onRoadCancel();}
      drag=null;renderer.domElement.style.cursor=getTool().pan?'grab':'crosshair';
    });
    renderer.domElement.addEventListener('pointercancel',()=>{drag=null;roadDrag=null;moved=true;onRoadCancel();});
    renderer.domElement.addEventListener('contextmenu',e=>e.preventDefault());
    renderer.domElement.addEventListener('click',e=>{if(moved){moved=false;return;}const p=pick(e);if(p)onPoint(p);});
    renderer.domElement.addEventListener('keydown',e=>{
      const directions={ArrowLeft:[-25,0],ArrowRight:[25,0],ArrowUp:[0,-25],ArrowDown:[0,25]};
      if(directions[e.key]){e.preventDefault();let [dx,dz]=directions[e.key];if(e.shiftKey){dx/=5;dz/=5;}if(getTool().pan){pan.x+=dx*4/scale;pan.z+=dz*4/scale;resize();}else{cursor={x:cursor.x+dx,z:cursor.z+dz};onHover?.(cursor);}}
      if(e.key==='Enter'){e.preventDefault();onPoint(cursor);}
    });
    renderer.domElement.addEventListener('wheel',e=>{e.preventDefault();const before=pick(e);scale=Math.max(.7,Math.min(22,scale*(e.deltaY<0?1.15:1/1.15)));resize();const after=pick(e);if(before&&after){pan.x+=before.x-after.x;pan.z+=before.z-after.z;resize();}},{passive:false});
    renderer.domElement.addEventListener('pointerleave',()=>{preview.visible=false;render();});
    function render() {
      renderer.render(scene,camera);
      const width=container.clientWidth,height=container.clientHeight;
      const occupied=[];labels.forEach(({el,point})=>{const pt=point.clone().project(camera);el.style.left=(pt.x+1)*width/2+'px';el.style.top=(1-pt.y)*height/2+'px';const x=(pt.x+1)*width/2,y=(1-pt.y)*height/2;const bounds=CityPlan.activeBounds;const hidden=point.x<bounds.minX||point.x>bounds.maxX||point.z<bounds.minZ||point.z>bounds.maxZ||Math.abs(pt.x)>1||Math.abs(pt.y)>1||occupied.some(p=>Math.abs(p.x-x)<105&&Math.abs(p.y-y)<23);el.style.display=hidden?'none':'';if(!hidden)occupied.push({x,y});});
    }
    function resize() {
      const w=container.clientWidth,h=container.clientHeight;if(!w||!h)return;
      const half=Math.max((CityPlan.activeBounds.maxZ-CityPlan.activeBounds.minZ)/2+45,((CityPlan.activeBounds.maxX-CityPlan.activeBounds.minX)/2+45)*h/w)/scale;
      camera.left=-half*w/h;camera.right=half*w/h;camera.top=half;camera.bottom=-half;
      camera.position.set(pan.x,6000,pan.z+(tilt?3000:.01));camera.lookAt(pan.x,0,pan.z);camera.updateProjectionMatrix();
      renderer.setSize(w,h,false);render();
      document.getElementById('scaleValue').textContent='100 m';
      document.getElementById('scaleBar').style.width=(100*CityPlan.scale/(half*2*w/h)*w)+'px';
    }
    function update(lotMap={},agents=[],state={}) {
      renderer.domElement.style.cursor=getTool().pan?'grab':'crosshair';
      if(lastRevision!==CityPlan.revision){
        disposeGroup(buildingMesh);refreshLabels();drawFog();
        for(const c of CityPlan.plan.buildings){
          if(c.area){
            part('round',c.x,.2,c.z,59,.35,54,0xafbf92);
            for(const [dx,dz] of [[-31,-26],[26,-31],[-24,27],[31,22]]){
              const site={x:c.x+dx,z:c.z+dz,rotation:c.rotation};origin=site;modelScale=CityPlan.buildingScale(c.type);drawBuilding(c.type,site);origin=null;modelScale=1;
            }
          }else{origin=c;modelScale=CityPlan.buildingScale(c.type);drawBuilding(c.type,c);origin=null;modelScale=1;}
        }
        buildingMesh=flush();drawRoads();lastRevision=CityPlan.revision;
      }
      if(agents.length!==agentCount){if(people){scene.remove(people);people.dispose();}people=null;if(agents.length){people=new T.InstancedMesh(geometries.box,material,agents.length);people.frustumCulled=false;scene.add(people);}agentCount=agents.length;}
      if(people){agents.forEach((a,i)=>{const person=a.kind==='resident',obj=new T.Object3D();obj.position.set(a.x,CityPlan.elevationAt(a)+(person?1.2:1.5),a.z);obj.scale.set(person?1.8:2.5,person?2.2:2,person?1.8:5);obj.updateMatrix();people.setMatrixAt(i,obj.matrix);people.setColorAt(i,new T.Color(a.kind==='ambulance'?0xffe4a0:person?0x63467e:0xc04f35));});people.instanceMatrix.needsUpdate=true;people.instanceColor.needsUpdate=true;}
      guard.material.color.set(state.hallProtected===false?0xe17461:0xf0d275);render();
    }
    function ghost(p,type,rotation=0,start=null,bridge=false) {
      preview.visible=!!p;frontArrow.visible=!!p&&!CityPlan.widths[type];if(!p){if(previewLine){scene.remove(previewLine);previewLine.geometry.dispose();previewLine=null;}render();return;}
      const size=CityPlan.buildingScale(type)*7.8||8;frontArrow.position.set(p.x,2,p.z);frontArrow.setDirection(new T.Vector3(Math.sin(rotation),0,Math.cos(rotation)));frontArrow.setLength(size*.8,4,3);preview.scale.set(size,size,1);preview.position.set(p.x,1.5,p.z);preview.rotation.z=-rotation;
      preview.material.color.set(CityPlan.buildingError({...p,type})?0xda785d:0xf5db96);
      if(previewLine){scene.remove(previewLine);previewLine.geometry.dispose();previewLine=null;}
      if(start){previewLine=new T.Line(new T.BufferGeometry().setFromPoints([new T.Vector3(start.x,2,start.z),new T.Vector3(p.x,2,p.z)]),new T.LineBasicMaterial({color:CityPlan.roadError(start,p,type,bridge)?0xe87564:0xffe2a0}));scene.add(previewLine);preview.visible=false;}
      render();
    }
    new ResizeObserver(resize).observe(container);resize();
    return {update,ghost,zoom(delta){scale=Math.max(.7,Math.min(22,scale*(delta>0?1.4:1/1.4)));resize();},resetView(){scale=1;pan={x:(CityPlan.activeBounds.minX+CityPlan.activeBounds.maxX)/2,z:(CityPlan.activeBounds.minZ+CityPlan.activeBounds.maxZ)/2};resize();},focusLevel(){scale=1;pan={x:(CityPlan.activeBounds.minX+CityPlan.activeBounds.maxX)/2,z:(CityPlan.activeBounds.minZ+CityPlan.activeBounds.maxZ)/2};resize();},toggleView(){tilt=!tilt;resize();}};
  }
  window.CityWorld={mount};
})();
