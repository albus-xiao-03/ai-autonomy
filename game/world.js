/* Boston terrain, road-construction previews and low-poly rendering. */
(() => {
  "use strict";
  const T = window.THREE;
  function mount(container,{onPoint,onHover,getTool,onRoadStart,onRoadEnd,onRoadCancel}) {
    const scene=new T.Scene();
    scene.background = new T.Color(0x7ba9ba);
    // Top-down editing uses an orthographic camera; the default 3D view is a tilted perspective
    // camera with sky and distance haze (a Google Earth-style look).
    const orthoCamera=new T.OrthographicCamera(-2000,2000,1600,-1600,1,30000),perspCamera=new T.PerspectiveCamera(38,1,1,40000);
    let camera=orthoCamera;
    const skyColor=new T.Color(0xbfd6e4),planColor=new T.Color(0x7ba9ba),haze=new T.Fog(0xbfd6e4,2000,8000);
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
    sun.shadow.mapSize.set(2048,2048);sun.shadow.normalBias=1.5;sun.shadow.bias=-.00015;
    scene.add(sun);
    const geometries={box:new T.BoxGeometry(1,1,1), round:new T.CylinderGeometry(1,1,1,12), roof:new T.ConeGeometry(1,1,4), pine:new T.ConeGeometry(1,1,7), crown:new T.IcosahedronGeometry(1,0), dome:new T.SphereGeometry(1,10,4,0,Math.PI*2,0,Math.PI/2)};
    const material=new T.MeshStandardMaterial({roughness:1,flatShading:true});
    let pending=[],origin=null,yaw=0,modelScale=1,latestIncidents=[],damageById={},lastDamageKey='';
    function part(shape,x,y,z,w,h,d,color,yaw=0) {
      const object=new T.Object3D();
      if(origin){const dx=(x-origin.x)*modelScale,dz=(z-origin.z)*modelScale;x=origin.x+dx*Math.cos(origin.rotation||0)+dz*Math.sin(origin.rotation||0);z=origin.z-dx*Math.sin(origin.rotation||0)+dz*Math.cos(origin.rotation||0);y=.8+(y-.8)*modelScale;w*=modelScale;h*=modelScale;d*=modelScale;yaw+=origin.rotation||0;}
      object.position.set(x,y,z);object.rotation.y=yaw;object.scale.set(w,h,d);object.updateMatrix();
      if(origin?.damage)color=new T.Color(color).lerp(new T.Color(0x574741),Math.min(.8,origin.damage/125)).getHex();
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
    for(const c of CityPlan.landmarks.filter(l=>l.site==='common')) {
      origin=c;modelScale=c.scale||8;landmark(c);origin=null;modelScale=1;
    }
    flush();
    // ---- Real Boston city layer (OpenStreetMap footprints, 1:1) ----
    // Level of detail saves GPU, memory and CPU: building masses are always drawn; detail
    // (cornices, porches, awnings) appears at zoom >= 3 and window rows at zoom >= 6, and both
    // only for the 300 m tiles in view. Only masses cast shadows.
    const CITY_TILE=300,CITY_GROUND=.85,cityTiles=new Map(),cityInstances=new Map(),cityHidden=new T.Matrix4().makeScale(0,0,0),cityObject=new T.Object3D();
    function cityTile(b){const tx=Math.floor(b.x/CITY_TILE),tz=Math.floor(b.z/CITY_TILE),key=tx+','+tz;if(!cityTiles.has(key))cityTiles.set(key,{minX:tx*CITY_TILE,minZ:tz*CITY_TILE,layers:{mass:[],detail:[],fine:[]},groups:{}});return cityTiles.get(key);}
    // Place one part in the building's own frame: lx runs along the footprint's long edge (w), lz across it (d).
    function cpart(tile,layer,b,shape,lx,ly,lz,w,h,d,color,yaw=0){
      const c=Math.cos(b.r),s=Math.sin(b.r);
      cityObject.position.set(b.x+lx*c-lz*s,ly,b.z+lx*s+lz*c);cityObject.rotation.set(0,-b.r+yaw,0);cityObject.scale.set(w,h,d);cityObject.updateMatrix();
      tile.layers[layer].push({shape,matrix:cityObject.matrix.clone(),color,id:b.id});
    }
    const cityBrick=[0xa4553f,0x9b4a39,0xb0614a,0x97503e],cityClapboard=[0xd8cdb0,0xa9bcc4,0xc9a88a,0xb7c4a5];
    function cityBuilding(b){
      const t=cityTile(b),G=CITY_GROUND,W=Math.max(4,b.w),D=Math.max(4,b.d),H=Math.max(4,b.h),top=G+H,floors=Math.max(1,Math.min(60,Math.round(H/3.3))),id=Math.abs(b.id);
      const P=(layer,shape,lx,ly,lz,w,h,d,color,yaw)=>cpart(t,layer,b,shape,lx,ly,lz,w,h,d,color,yaw);
      const body=color=>P('mass','box',0,G+H/2,0,W,H,D,color);
      const bands=(color,all=false)=>{for(let f=0;f<floors;f++){const y=G+2+f*3.3;if(y>top-1)break;
        P('fine','box',0,y,D/2+.06,W*.82,1.2,.12,color);P('fine','box',0,y,-D/2-.06,W*.82,1.2,.12,color);
        if(all){P('fine','box',W/2+.06,y,0,.12,1.2,D*.82,color);P('fine','box',-W/2-.06,y,0,.12,1.2,D*.82,color);}}};
      if(b.k==='res'){
        // Four Boston residential styles, chosen per building by the data file (b.s).
        if(b.s===0){ // red-brick rowhouse with a white cornice
          body(cityBrick[id%4]);P('mass','box',0,top+.15,0,W,.3,D,0x4a4440);P('detail','box',0,top-.4,0,W+.5,.7,D+.5,0xe9e0c8);P('detail','box',0,G+.5,D/2+.8,1.6,1,1.4,0x8f8576);bands(0x2f3b40);
        }else if(b.s===1){ // brownstone with a bay window and stoop
          body(0x6e4a3a);P('mass','box',0,top+.15,0,W,.3,D,0x3d3532);P('detail','box',-W*.22,G+H*.42,D/2+.7,W*.34,H*.8,1.4,0x7a5444);P('detail','box',W*.25,G+.7,D/2+1.2,1.6,1.4,2.2,0x8a6a5a);P('detail','box',0,top-.35,0,W+.4,.6,D+.4,0x2e2724);bands(0x2a3236);
        }else if(b.s===2){ // triple-decker with stacked porches
          const porch=Math.min(H,13);body(cityClapboard[id%4]);P('mass','box',0,top+.2,0,W+.9,.4,D+.9,0x5a5550);
          for(let f=0;f<Math.min(floors,4);f++)P('detail','box',0,G+.3+f*3.3,D/2+1.1,W*.9,.25,2.2,0xf2efe6);
          for(const sx of [-.42,.42])P('detail','box',W*sx,G+porch/2,D/2+2.1,.3,porch,.3,0xf2efe6);bands(0x34414a);
        }else{ // Beacon Hill federal brick with slate roof, dormer and black shutters
          body(0x8a3a2c);P('mass','roof',0,top+1.6,0,W*.72,3.2,D*.72,0x4b4f55,Math.PI/4);P('detail','box',0,top+1.4,D*.22,W*.25,1.6,1.2,0x4b4f55);
          for(const sx of [-.32,-.12,.12,.32])P('detail','box',W*sx,G+H*.5,D/2+.1,.45,H*.75,.12,0x1d1f22);bands(0xe8e2d0);
        }
      }else if(b.k==='office'){
        body(id%2?0x9eadb2:0xc7c0ae);P('mass','box',W*.15,top+1.2,-D*.1,Math.min(W*.35,14),2.4,Math.min(D*.35,10),0x7d878a);P('detail','box',0,top-.3,0,W+.4,.6,D+.4,0x5e6c70);bands(0x46606b,true);
      }else if(b.k==='shop'){
        body(0xe0b98a);P('mass','box',0,top+.15,0,W,.3,D,0x6b5a4a);for(let i=0;i<6;i++)P('detail','box',-W*.42+i*W*.168,G+3.2,D/2+.9,W*.168,.25,1.8,i%2?0xf1dfb7:0xb85d43);bands(0x2f3b40);
      }else if(b.k==='parking'){
        body(0x8a9396);for(let f=1;f<floors;f++)P('detail','box',0,G+f*3.3,0,W+.3,.35,D+.3,0x6c7477);
      }else{ // fire, police and medical share one civic style with a department colour band
        const look={fire:[0xa13d30,0xd9443a],police:[0x5f6670,0x2d5aa8],medical:[0xe9e7df,0x2f8f6f]}[b.k]||[0xb0a89a,0x777777];
        body(look[0]);P('mass','box',0,top-1.2,0,W+.3,1.6,D+.3,look[1]);P('mass','box',0,top+.15,0,W,.3,D,0x3f3f3f);
        if(b.k==='fire'){P('mass','box',W/2-3,top+5,-D/2+3,5,10,5,look[0]);for(const sx of [-.25,.25])P('detail','box',W*sx,G+2.5,D/2+.08,W*.32,5,.15,0x2b2b2b);}
        if(b.k==='police'){P('mass','round',W*.3,top+1.2,D*.3,.8,2,.8,0x3b6fd6);P('detail','box',0,G+3,D/2+.1,W*.6,1.2,.15,0x2d5aa8);}
        if(b.k==='medical'){const m=Math.min(W,D);P('mass','box',0,top+.5,0,m*.5,.5,m*.14,0xd23c34);P('mass','box',0,top+.5,0,m*.14,.5,m*.5,0xd23c34);}
        bands(b.k==='medical'?0x4d7f95:0x2f3b40,true);
      }
    }
    // Unique and historical buildings: the real footprint extruded to real height (1:1), plus accents.
    const uniqueGroup=new T.Group();scene.add(uniqueGroup);
    const uniqueMaterials=new Map(),uniqueMaterial=color=>{if(!uniqueMaterials.has(color))uniqueMaterials.set(color,new T.MeshStandardMaterial({color,roughness:.9,flatShading:true}));return uniqueMaterials.get(color);};
    function uniqueColor(b){const n=(b.n||'').toLowerCase();if(n.includes('massachusetts state house'))return 0xc9885a;if(n==='boston city hall')return 0xb9b2a2;if(n.includes('quincy'))return 0xd9cdb0;if(n.includes('garden')||n.includes('north station'))return 0x8d8f8a;if(n.includes('custom house'))return 0xd8d2bf;if(n.includes('court'))return 0xcfc6b0;if(/church|shul|chapel/.test(n))return 0xe2d9c4;return [0xb5654a,0xa95b45,0xc07a5c][Math.abs(b.id)%3];}
    function uniqueBuilding(b){
      const G=CITY_GROUND,n=(b.n||'').toLowerCase(),church=/church|shul|chapel/.test(n),bodyH=church?Math.min(b.h,16):Math.max(6,b.h);
      const geo=new T.ExtrudeGeometry(new T.Shape(b.fp.map(([x,z])=>new T.Vector2(x,-z))),{depth:bodyH,bevelEnabled:false});geo.rotateX(-Math.PI/2);
      const mesh=new T.Mesh(geo,uniqueMaterial(uniqueColor(b)));mesh.position.set(b.x,G,b.z);mesh.castShadow=mesh.receiveShadow=true;mesh.userData.cityId=b.id;uniqueGroup.add(mesh);
      const t=cityTile(b),P=(shape,lx,ly,lz,w,h,d,color,yaw)=>cpart(t,'mass',b,shape,lx,ly,lz,w,h,d,color,yaw),m=Math.min(b.w,b.d);
      if(n.includes('massachusetts state house')){P('round',0,G+bodyH+2,0,m*.16,4,m*.16,0xf0ead8);P('dome',0,G+bodyH+4,0,m*.15,m*.13,m*.15,0xe0b04a);P('round',0,G+bodyH+5.2+m*.13,0,.8,2.4,.8,0xe8c977);}
      else if(church){const tx=-b.w/2+Math.min(5,b.w*.2);P('box',tx,G+b.h*.35,0,6,b.h*.7,6,0xe2d9c4);P('pine',tx,G+b.h*.85,0,3.2,b.h*.3,3.2,0xf3f0e6);}
      else if(n.includes('faneuil hall')){P('round',0,G+bodyH+2,b.d*.1,2.2,4,2.2,0xf3efe2);P('dome',0,G+bodyH+4,b.d*.1,2.3,2.5,2.3,0x6f8f7c);}
      else if(n.includes('quincy market')){P('dome',0,G+bodyH,0,m*.3,m*.22,m*.3,0xa96f45);}
      else if(n.includes('custom house tower')){P('roof',0,G+bodyH+6,0,b.w*.4,12,b.d*.4,0x5f7f74,Math.PI/4);}
      else if(n.includes('old state house')){P('box',b.w*.3,G+bodyH+3,0,3,6,3,0xf3efe2);P('pine',b.w*.3,G+bodyH+8,0,1.6,4,1.6,0xf3efe2);}
    }
    // Gold outline = permanent historical protection; dashed blue outline = author-set lock.
    function lockOutlines(){
      const gold=[],blue=[];
      for(const b of CityPlan.city){if(!b.locked||!b.fp)continue;const list=b.locked==='permanent'?gold:blue;
        b.fp.forEach(([x,z],i)=>{const [nx,nz]=b.fp[(i+1)%b.fp.length];list.push(new T.Vector3(b.x+x,CITY_GROUND+.3,b.z+z),new T.Vector3(b.x+nx,CITY_GROUND+.3,b.z+nz));});}
      scene.add(new T.LineSegments(new T.BufferGeometry().setFromPoints(gold),new T.LineBasicMaterial({color:0xf1d181})));
      const dashed=new T.LineSegments(new T.BufferGeometry().setFromPoints(blue),new T.LineDashedMaterial({color:0x5fa8ff,dashSize:3,gapSize:2}));dashed.computeLineDistances();scene.add(dashed);
    }
    // Real Boston streets: drawn once into the same tiles (asphalt and sidewalks always, markings when
    // zoomed in). Bridges, tunnels, edited streets and player roads still go through drawRoads().
    const streetIds=new Set();let streetGone=new Set();
    function buildStreets(){
      for(const r of CityPlan.plan.roads){
        if(!r.real||r.bridge||r.tunnel)continue;
        const length=CityPlan.dist(r.a,r.b),w=CityPlan.roadWidth(r),seg={x:(r.a.x+r.b.x)/2,z:(r.a.z+r.b.z)/2,r:Math.atan2(r.b.z-r.a.z,r.b.x-r.a.x),id:r.pathId},t=cityTile(seg);
        streetIds.add(r.pathId);
        cpart(t,'mass',seg,'box',0,.38,0,length+.6,.12,w+2.4,0xb7b5a5);cpart(t,'mass',seg,'box',0,.52,0,length+.6,.12,w,0x59666a);
        for(const end of [r.a,r.b]){const e={x:end.x,z:end.z,r:0,id:r.pathId};cpart(t,'mass',e,'round',0,.38,0,w/2+1.2,.12,w/2+1.2,0xb7b5a5);cpart(t,'mass',e,'round',0,.52,0,w/2,.12,w/2,0x59666a);}
        if(r.type==='twoway'||r.type==='highway')for(let s=((2-(r.pathStart||0))%10+10)%10;s<length-1;s+=10){const d=Math.min(4,length-s);cpart(t,'detail',seg,'box',s+d/2-length/2,.6,0,d,.03,.2,r.type==='highway'?0xd4b957:0xe0ce9b);}
        if(r.type==='oneway')for(let s=((10-(r.pathStart||0))%24+24)%24;s<length-1;s+=24){cpart(t,'detail',seg,'box',s-length/2,.6,0,3,.03,.25,0xf4e9c3);for(const sign of [-1,1])cpart(t,'detail',seg,'box',s-length/2+.9,.6,sign*.45,1.6,.03,.22,0xf4e9c3,sign*.65);}
      }
    }
    function applyStreetRemoval(){
      const present=new Set(CityPlan.plan.roads.filter(r=>r.real&&!r.bridge&&!r.tunnel&&CityPlan.streetOriginal(r)).map(r=>r.pathId)),touched=new Set();
      for(const id of streetIds){const hide=!present.has(id);if(hide===streetGone.has(id))continue;for(const e of cityInstances.get(id)||[]){e.mesh.setMatrixAt(e.i,hide?cityHidden:e.matrix);touched.add(e.mesh);}if(hide)streetGone.add(id);else streetGone.delete(id);}
      touched.forEach(m=>{m.instanceMatrix.needsUpdate=true;m.computeBoundingSphere();});
    }
    function buildCity(){
      buildStreets();
      for(const b of CityPlan.city){if(b.k==='unique'){if(b.fp)uniqueBuilding(b);}else cityBuilding(b);}
      for(const tile of cityTiles.values())for(const layer of ['mass','detail','fine']){
        const group=new T.Group();group.visible=layer==='mass';scene.add(group);tile.groups[layer]=group;
        const byShape={};for(const p of tile.layers[layer])(byShape[p.shape]??=[]).push(p);
        for(const [shape,list] of Object.entries(byShape)){
          const mesh=new T.InstancedMesh(geometries[shape],material,list.length);
          list.forEach((p,i)=>{mesh.setMatrixAt(i,p.matrix);mesh.setColorAt(i,new T.Color(p.color));if(!cityInstances.has(p.id))cityInstances.set(p.id,[]);cityInstances.get(p.id).push({mesh,i,matrix:p.matrix});});
          mesh.castShadow=layer==='mass';mesh.receiveShadow=layer!=='fine';mesh.computeBoundingSphere();group.add(mesh);
        }
        tile.layers[layer]=null;
      }
      lockOutlines();
    }
    let cityGone=new Set();
    // Hide bulldozed buildings (and restore them on undo) by touching only the changed instances.
    function applyCityRemoval(){
      const now=CityPlan.removedCity,changed=[...now].filter(id=>!cityGone.has(id)).concat([...cityGone].filter(id=>!now.has(id)));
      if(!changed.length)return;const touched=new Set();
      for(const id of changed)for(const e of cityInstances.get(id)||[]){e.mesh.setMatrixAt(e.i,now.has(id)?cityHidden:e.matrix);touched.add(e.mesh);}
      touched.forEach(m=>{m.instanceMatrix.needsUpdate=true;m.computeBoundingSphere();});cityGone=new Set(now);
    }
    function updateCityLod(halfWidth,halfHeight){
      const pad=tilt?2.2:1.15;
      for(const t of cityTiles.values()){
        const inView=t.minX<pan.x+halfWidth*pad&&t.minX+CITY_TILE>pan.x-halfWidth*pad&&t.minZ<pan.z+halfHeight*pad&&t.minZ+CITY_TILE>pan.z-halfHeight*pad;
        t.groups.detail.visible=scale>=3&&inView;t.groups.fine.visible=scale>=6&&inView;
      }
    }
    buildCity();
    const guard=new T.Mesh(new T.RingGeometry(CITY_HALL.radius-1,CITY_HALL.radius,100),new T.MeshBasicMaterial({color:0xf1d181,side:T.DoubleSide,transparent:true,opacity:.8,depthWrite:false}));
    guard.rotation.x=-Math.PI/2;guard.position.set(CITY_HALL.x,1.1,CITY_HALL.z);scene.add(guard);
    const preview=new T.Mesh(new T.PlaneGeometry(1,1),new T.MeshBasicMaterial({color:0xf6df9d,transparent:true,opacity:.5,side:T.DoubleSide,depthWrite:false}));
    preview.rotation.x=-Math.PI/2;preview.visible=false;scene.add(preview);
    const frontArrow=new T.ArrowHelper(new T.Vector3(0,0,1),new T.Vector3(0,2,0),10,0xf2cd68,4,3);frontArrow.visible=false;scene.add(frontArrow);
    let previewLine=null;
    const labelsLayer=document.createElement('div');labelsLayer.className='maplabels';container.append(labelsLayer);
    let labels=[];
    function refreshLabels(){labelsLayer.replaceChildren();labels=[...latestIncidents.filter(i=>!['resolved','averted'].includes(i.status)).map(i=>({name:i.label.toUpperCase()+' · '+i.response,x:i.x,z:i.z,incident:true})),...CityPlan.landmarks,...CityPlan.highwayGates(),...CityPlan.highwayRamps(),...CityPlan.servicePoints(),...CityPlan.city.filter(b=>b.n&&(['fire','police'].includes(b.k)||/^(paul revere house|faneuil hall|old state house|museum of science|north station|old west church|the vilna shul|otis house museum|old north church)$/i.test(b.n))).map(b=>({name:b.n.replace('Boston Fire Department ','Fire · ').replace('Boston Police Department ','Police · '),x:b.x,z:b.z,height:b.h+12})),...CityPlan.plan.buildings.filter(b=>b.area),...[...new Map(CityPlan.plan.roads.filter(r=>r.real&&r.bridge&&r.name&&r.pathStart===0&&!CityPlan.land({x:(r.a.x+r.b.x)/2,z:(r.a.z+r.b.z)/2})).map(r=>[r.name,{name:r.name.toUpperCase(),x:(r.a.x+r.b.x)/2,z:(r.a.z+r.b.z)/2,structure:true}])).values()],...CityPlan.plan.roads.filter(r=>!r.real&&(r.bridge||r.tunnel)&&(!r.pathId||r.pathStart===0)).map(r=>({name:r.tunnel?'TUNNEL':'OVERPASS',x:(r.a.x+r.b.x)/2,z:(r.a.z+r.b.z)/2,structure:true})),...CityPlan.plan.controls.filter(c=>c.kind!=='signal').map(c=>({name:c.kind==='stop'?'STOP':'▽ YIELD',x:c.x+c.approach.x*20+c.approach.z*7,z:c.z+c.approach.z*20-c.approach.x*7,traffic:true}))].map(l=>{const el=document.createElement('span');el.textContent=l.name||l.label;if(l.traffic)el.className='trafficLabel';if(l.structure)el.className='structureLabel';if(l.incident)el.className='incidentLabel';labelsLayer.append(el);return {el,point:new T.Vector3(l.x,l.height??35,l.z)};});}
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
    let roadsGroup=null,controlsGroup=null,controlsKey='';
    const shoulderMaterial=new T.MeshStandardMaterial({color:0xb7b5a5,roughness:1});
    const asphaltMaterial=new T.MeshStandardMaterial({color:0x59666a,roughness:1});
    function flatSurface(polygons,height,material) {
      const shapes=polygons.map(polygon=>{
        const shape=new T.Shape(polygon[0].map(([x,z])=>new T.Vector2(x,-z)));
        for(const ring of polygon.slice(1))shape.holes.push(new T.Path(ring.map(([x,z])=>new T.Vector2(x,-z))));
        return shape;
      });
      if(!shapes.length)return null;
      const geometry=new T.ShapeGeometry(shapes);geometry.rotateX(-Math.PI/2);
      const mesh=new T.Mesh(geometry,material);mesh.position.y=height;mesh.receiveShadow=true;mesh.userData.ownedGeometry=true;
      return mesh;
    }
    function markingBlocked(road,p){
      return CityPlan.plan.roads.some(other=>other!==road&&!(road.pathId&&other.pathId===road.pathId)&&Math.abs(CityPlan.heightAt(p,road)-CityPlan.heightAt(p,other))<.75&&CityPlan.dist(p,CityPlan.projection(p,other.a,other.b))<CityPlan.roadWidth(other)/2+.65);
    }
    function drawControls(time){
      const key=CityPlan.revision+'|'+CityPlan.plan.controls.map(c=>c.kind==='signal'?CityPlan.signalState(c,time,true):c.kind).join('|');
      if(key===controlsKey)return;
      controlsKey=key;disposeGroup(controlsGroup);
      for(const control of CityPlan.plan.controls){
        if(control.kind==='signal'){
          for(const [dx,dz,horizontal] of [[10,10,true],[-10,-10,false]]){
            const x=control.x+dx,z=control.z+dz;
            box(x,3,z,.6,6,.6,0x53615b);box(x,6.1,z,2,5.3,1.3,0x263430);
            const phase=CityPlan.signalState(control,time,horizontal);
            ['red','amber','green'].forEach((color,i)=>part('round',x,7.7-i*1.65,z+.72,.65,.8,.65,phase===color?{red:0xf35a43,amber:0xffd468,green:0x7cce84}[color]:0x3e4944));
          }
        }else{
          const arm=control.approach,flow={x:-arm.x,z:-arm.z},x=control.x+arm.x*20,z=control.z+arm.z*20,angle=-Math.atan2(flow.z,flow.x);
          // The arrow lies in the incoming lane and points into the junction.
          box(x,.79,z,7,.08,.65,0xf4eacf,angle);
          for(const side of [-1,1])box(x+flow.x*2+arm.z*side*1.2,.79,z+flow.z*2-arm.x*side*1.2,3.7,.08,.65,0xf4eacf,angle+side*.65);
          const sx=x+arm.z*7,sz=z-arm.x*7;
          box(sx,2.3,sz,.45,4.6,.45,0x707e76);
          if(control.kind==='stop'){
            part('round',sx,4.8,sz,2.2,.25,2.2,0xe5e2d3);
            part('round',sx,5.02,sz,1.86,.25,1.86,0xcf5140);
          }else{
            part('roof',sx,4.5,sz,2.6,.4,2.6,0xdd5c45,Math.PI/4);
            part('roof',sx,4.8,sz,1.85,.4,1.85,0xf1ead5,Math.PI/4);
          }
        }
      }
      controlsGroup=flush();
    }
    function bridgeRibbon(road,width,offset,material){
      const length=CityPlan.dist(road.a,road.b),nx=-(road.b.z-road.a.z)/length,nz=(road.b.x-road.a.x)/length,vertices=[];
      const count=Math.ceil(length/5);
      const vertex=(t,side)=>{const p={x:road.a.x+(road.b.x-road.a.x)*t,z:road.a.z+(road.b.z-road.a.z)*t};return [p.x+nx*side*width/2,CityPlan.heightAt(p,road)+offset,p.z+nz*side*width/2];};
      for(let i=0;i<count;i++){const a=vertex(i/count,-1),b=vertex(i/count,1),c=vertex((i+1)/count,1),d=vertex((i+1)/count,-1);vertices.push(...a,...b,...c,...a,...c,...d);}
      const geometry=new T.BufferGeometry();geometry.setAttribute('position',new T.Float32BufferAttribute(vertices,3));geometry.computeVertexNormals();
      const mesh=new T.Mesh(geometry,material);mesh.receiveShadow=true;mesh.userData.ownedGeometry=true;return mesh;
    }
    function drawRoads() {
      disposeGroup(roadsGroup);const bridgeSurfaces=[];
      for(const r of CityPlan.plan.roads.filter(r=>!r.real||r.bridge||r.tunnel||!CityPlan.streetOriginal(r))){
        const length=CityPlan.dist(r.a,r.b),x=(r.a.x+r.b.x)/2,z=(r.a.z+r.b.z)/2;
        const angle=-Math.atan2(r.b.z-r.a.z,r.b.x-r.a.x),w=CityPlan.roadWidth(r);
        if(r.bridge){
          bridgeSurfaces.push(bridgeRibbon(r,w+2.4,-.1,shoulderMaterial),bridgeRibbon(r,w,.58,asphaltMaterial));
          const n=Math.ceil(length/5);
          for(let i=0;i<n;i++){
            const t=(i+.5)/n,p={x:r.a.x+(r.b.x-r.a.x)*t,z:r.a.z+(r.b.z-r.a.z)*t},y=CityPlan.heightAt(p,r);

            for(const side of [-1,1])box(p.x+Math.sin(angle)*side*(w/2+1),y+2,p.z+Math.cos(angle)*side*(w/2+1),length/n+.2,1.5,.45,0xe0dfc5,angle);
          }
          for(let t=((35-(r.pathStart||0))%65+65)%65;t<length;t+=65){
            const p={x:r.a.x+(r.b.x-r.a.x)*t/length,z:r.a.z+(r.b.z-r.a.z)*t/length},y=CityPlan.heightAt(p,r);
            box(p.x,(y-14)/2,p.z,3.2,y+14,w*.75,0x7c9292,angle);
          }
        }
        if(r.tunnel){
          // The dashed guide stays visible while the actual tunnel and cars are underground.
          for(let t=4;t<length-4;t+=13){
            const p={x:r.a.x+(r.b.x-r.a.x)*t/length,z:r.a.z+(r.b.z-r.a.z)*t/length};
            box(p.x,1.05,p.z,6,.08,w*.62,0x577e86,angle);
          }
          for(const [end,other] of [[r.a,r.b],[r.b,r.a]].filter((pair,i)=>Math.abs(CityPlan.heightAt(pair[0],r))<.75&&(!r.pathId||r.fixed||(i===0?r.pathStart===0:Math.abs(r.pathEnd-r.pathLength)<.01)))){
            const dx=(other.x-end.x)/length,dz=(other.z-end.z)/length;
            box(end.x+dx*5,.85,end.z+dz*5,10,.2,w,0x24393d,angle);
            box(end.x,4,end.z,3,1.5,w+3,0xb8b8a4,angle);
            for(const side of [-1,1])box(end.x-dz*side*(w/2+1),2,end.z+dx*side*(w/2+1),3,4,1.5,0xa6aca0,angle);
          }
          continue;
        }
        const line=(offset,color,dashed)=>{
          const interval=dashed?10:4,start=((2-(r.pathStart||0))%interval+interval)%interval;
          for(let t=start;t<length-.1;t+=interval){
            const d=Math.min(dashed?4:4.1,length-t),px=r.a.x+(r.b.x-r.a.x)*(t+d/2)/length,pz=r.a.z+(r.b.z-r.a.z)*(t+d/2)/length;
            const marking={x:px+Math.sin(angle)*offset,z:pz+Math.cos(angle)*offset};
            if(!markingBlocked(r,marking))box(marking.x,.62+CityPlan.heightAt({x:px,z:pz},r),marking.z,d,.04,.2,color,angle);
          }
        };
        line(-w/2+.35,0xe7dfb8,false);line(w/2-.35,0xe7dfb8,false);
        if(r.type==='highway'&&!r.oneway){line(0,0xd4b957,false);line(-w/4,0xd9dfda,true);line(w/4,0xd9dfda,true);}
        else if(r.type==='twoway')line(0,0xe0ce9b,true);
        else if(r.type==='highway')line(0,0xd9dfda,true);
        if(r.type==='oneway'||r.oneway){
          for(let t=((10-(r.pathStart||0))%24+24)%24;t<length-1;t+=24){
            const x=r.a.x+(r.b.x-r.a.x)*t/length,z=r.a.z+(r.b.z-r.a.z)*t/length;
            if(markingBlocked(r,{x,z}))continue;
            box(x,.65+CityPlan.heightAt({x,z},r),z,3,.04,.25,0xf4e9c3,angle);
            for(const sign of [-1,1])box(x+Math.cos(angle)*.9+Math.sin(angle)*sign*.45,.65+CityPlan.heightAt({x,z},r),z-Math.sin(angle)*.9+Math.cos(angle)*sign*.45,1.6,.04,.22,0xf4e9c3,angle+sign*.65);
          }
        }
      }
      for(const building of [...CityPlan.plan.buildings,...CityPlan.landmarks.filter(l=>['hall','hospital'].includes(l.site))]){
        const connection=CityPlan.access(building),s=building.scale||CityPlan.buildingScale(building.type),angle=building.rotation||0;
        const entrance={x:building.x+Math.sin(angle)*(building.radius||s*2.5),z:building.z+Math.cos(angle)*(building.radius||s*2.5)};
        box(entrance.x,1.1,entrance.z,8,.5,8,(connection||building.site)?0xf5d176:0xe98649,angle);
        if(connection){
          const p=connection.p,length=connection.length,rotation=-Math.atan2(p.z-entrance.z,p.x-entrance.x);
          const n=Math.max(1,Math.ceil(length/3)),endHeight=CityPlan.heightAt(p,connection.road);
          for(let i=0;i<n;i++){const t=(i+.5)/n;box(entrance.x+(p.x-entrance.x)*t,.7+endHeight*t,entrance.z+(p.z-entrance.z)*t,length/n+.1,.15,2.4,0xe5dac0,rotation);}
        }else{
          part('pine',building.x,12,building.z,2,3,2,0xe98649);
        }
      }
      for(const ramp of CityPlan.highwayRamps())part('round',ramp.x,1.2,ramp.z,4,.6,4,ramp.flow==='on'?0x90cfb6:0xf1d57a);
      roadsGroup=flush();if(bridgeSurfaces.length)roadsGroup.add(...bridgeSurfaces);
      const shoulder=flatSurface(CityPlan.roadSurfaces(1.2),.4,shoulderMaterial);
      const asphalt=flatSurface(CityPlan.roadSurfaces(),.58,asphaltMaterial);
      if(shoulder)roadsGroup.add(shoulder);if(asphalt)roadsGroup.add(asphalt);
    }
    let buildingMesh=null,people=null,roofs=null,wheels=null,agentCount=0;
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
    function disposeGroup(g) {if(g){scene.remove(g);g.children.forEach(m=>{m.dispose?.();if(m.userData.ownedGeometry)m.geometry.dispose();});}}
    let cursor={x:0,z:500};
    let scale=1.3,tilt=true,azimuth=.35,elevationAngle=Math.PI*.3,orbit=null,pan={x:(CityPlan.activeBounds.minX+CityPlan.activeBounds.maxX)/2,z:(CityPlan.activeBounds.minZ+CityPlan.activeBounds.maxZ)/2},lastRevision=-1,drag=null,roadDrag=null,moved=false;
    const ray=new T.Raycaster(),pos=new T.Vector2(),ground=new T.Plane(new T.Vector3(0,1,0),0);
    function pick(e) {
      const r=renderer.domElement.getBoundingClientRect();
      pos.set((e.clientX-r.left)/r.width*2-1,1-(e.clientY-r.top)/r.height*2);ray.setFromCamera(pos,camera);
      const v=new T.Vector3();return ray.ray.intersectPlane(ground,v)?{x:v.x,z:v.z}:null;
    }
    renderer.domElement.addEventListener('pointerdown',e=>{
      if(e.button===0)moved=false;
      const tool=getTool();
      if(e.button===1){e.preventDefault();orbit={x:e.clientX,y:e.clientY};moved=false;renderer.domElement.setPointerCapture(e.pointerId);}
      else if(e.button===2||e.shiftKey||(e.button===0&&tool.pan)){
        e.preventDefault();drag={point:pick(e),x:e.clientX,y:e.clientY,button:e.button};moved=false;renderer.domElement.style.cursor='grabbing';renderer.domElement.setPointerCapture(e.pointerId);
      }else if(e.button===0&&tool.dragRoad){
        const p=pick(e);if(p){e.preventDefault();roadDrag=p;onRoadStart(p);renderer.domElement.setPointerCapture(e.pointerId);}
      }
    });
    renderer.domElement.addEventListener('pointermove',e=>{
      const p=pick(e);
      if(orbit){
        azimuth-=(e.clientX-orbit.x)*.006;elevationAngle=Math.max(.4,Math.min(Math.PI/2-.001,elevationAngle+(e.clientY-orbit.y)*.006));
        orbit={x:e.clientX,y:e.clientY};tilt=true;resize();moved=true;
      }else if(drag&&p){pan.x+=drag.point.x-p.x;pan.z+=drag.point.z-p.z;resize();moved=true;}
      else if(p)onHover?.(p);
    });
    renderer.domElement.addEventListener('pointerup',e=>{
      if(roadDrag){const p=pick(e);roadDrag=null;moved=true;if(p)onRoadEnd(p);else onRoadCancel();}
      if(drag?.button===2&&Math.hypot(e.clientX-drag.x,e.clientY-drag.y)<3){onRoadCancel();moved=true;}
      drag=orbit=null;renderer.domElement.style.cursor=getTool().pan?'grab':'crosshair';
    });
    renderer.domElement.addEventListener('pointercancel',()=>{drag=orbit=null;roadDrag=null;moved=true;onRoadCancel();});
    renderer.domElement.addEventListener('contextmenu',e=>e.preventDefault());
    renderer.domElement.addEventListener('click',e=>{if(moved){moved=false;return;}const p=pick(e);if(p)onPoint(p);});
    renderer.domElement.addEventListener('keydown',e=>{
      const directions={ArrowLeft:[-25,0],ArrowRight:[25,0],ArrowUp:[0,-25],ArrowDown:[0,25]};
      if(directions[e.key]){e.preventDefault();let [dx,dz]=directions[e.key];if(e.shiftKey){dx/=5;dz/=5;}if(getTool().pan){pan.x+=(dx*Math.cos(azimuth)+dz*Math.sin(azimuth))*4/scale;pan.z+=(-dx*Math.sin(azimuth)+dz*Math.cos(azimuth))*4/scale;resize();}else{cursor={x:cursor.x+dx,z:cursor.z+dz};onHover?.(cursor);}}
      if(e.key==='Enter'){e.preventDefault();onPoint(cursor);}
    });
    renderer.domElement.addEventListener('wheel',e=>{e.preventDefault();const before=pick(e);scale=Math.max(.7,Math.min(60,scale*(e.deltaY<0?1.15:1/1.15)));resize();const after=pick(e);if(before&&after){pan.x+=before.x-after.x;pan.z+=before.z-after.z;resize();}},{passive:false});
    renderer.domElement.addEventListener('pointerleave',()=>{ghost(null);document.getElementById('buildHint').textContent='';});
    function render() {
      renderer.render(scene,camera);
      const width=container.clientWidth,height=container.clientHeight;
      const occupied=[];labels.forEach(({el,point})=>{const pt=point.clone().project(camera);el.style.left=(pt.x+1)*width/2+'px';el.style.top=(1-pt.y)*height/2+'px';const x=(pt.x+1)*width/2,y=(1-pt.y)*height/2;const bounds=CityPlan.activeBounds;const hidden=point.x<bounds.minX||point.x>bounds.maxX||point.z<bounds.minZ||point.z>bounds.maxZ||pt.z>1||Math.abs(pt.x)>1||Math.abs(pt.y)>1||occupied.some(p=>Math.abs(p.x-x)<105&&Math.abs(p.y-y)<23);el.style.display=hidden?'none':'';if(!hidden)occupied.push({x,y});});
    }
    function resize() {
      const w=container.clientWidth,h=container.clientHeight;if(!w||!h)return;
      const half=Math.max((CityPlan.activeBounds.maxZ-CityPlan.activeBounds.minZ)/2+45,((CityPlan.activeBounds.maxX-CityPlan.activeBounds.minX)/2+45)*h/w)/scale;
      if(tilt){
        const distance=half/Math.tan(perspCamera.fov*Math.PI/360);camera=perspCamera;
        perspCamera.aspect=w/h;perspCamera.near=Math.max(1,distance/300);perspCamera.far=distance*10+8000;
        perspCamera.position.set(pan.x+Math.sin(azimuth)*Math.cos(elevationAngle)*distance,Math.sin(elevationAngle)*distance,pan.z+Math.cos(azimuth)*Math.cos(elevationAngle)*distance);perspCamera.lookAt(pan.x,0,pan.z);perspCamera.updateProjectionMatrix();
        haze.near=distance*1.1;haze.far=distance*4.5;scene.fog=haze;scene.background=skyColor;if(fog)fog.position.y=-158.5;
      }else{
        camera=orthoCamera;camera.left=-half*w/h;camera.right=half*w/h;camera.top=half;camera.bottom=-half;
        camera.position.set(pan.x+Math.sin(azimuth)*Math.cos(elevationAngle)*6000,Math.sin(elevationAngle)*6000,pan.z+Math.cos(azimuth)*Math.cos(elevationAngle)*6000);camera.lookAt(pan.x,0,pan.z);camera.updateProjectionMatrix();
        scene.fog=null;scene.background=planColor;if(fog)fog.position.y=0;
      }
      updateCityLod(half*w/h,half);renderer.setSize(w,h,false);document.querySelector('.compass').style.transform='rotate('+(-azimuth*180/Math.PI)+'deg)';render();
      document.getElementById('scaleValue').textContent='100 m';
      document.getElementById('scaleBar').style.width=(100*CityPlan.scale/(half*2*w/h)*w)+'px';
    }
    let incidentGroup=null,incidentEffectKey='',incidentLabelKey='';
    const waterMaterial=new T.MeshBasicMaterial({color:0x438fb8,transparent:true,opacity:.55,side:T.DoubleSide});
    function drawIncidents(state){
      const active=(state.incidents||[]).filter(i=>!['resolved','averted'].includes(i.status));
      const labelKey=active.map(i=>i.id+i.status+i.response).join('|');
      if(labelKey!==incidentLabelKey){latestIncidents=active;incidentLabelKey=labelKey;refreshLabels();}
      const key=CityPlan.revision+'|'+Math.floor((state.minute||0)*3)+'|'+labelKey;
      if(key===incidentEffectKey)return;
      incidentEffectKey=key;disposeGroup(incidentGroup);
      const water=[];
      for(const incident of active){
        const {x,z,radius,kind}=incident;
        if(kind==='flood'&&incident.status==='active'){
          const geometry=new T.CircleGeometry(radius,48);geometry.rotateX(-Math.PI/2);
          const mesh=new T.Mesh(geometry,waterMaterial);mesh.position.set(x,1.1,z);mesh.userData.ownedGeometry=true;water.push(mesh);
          for(let i=0;i<10;i++)box(x+Math.cos(i*2.3)*radius*.6,1.35,z+Math.sin(i*2.3)*radius*.6,12,.1,.7,0xa3d9e1,i);
        }else if(kind==='storm'&&incident.status==='active'){
          for(let i=0;i<36;i++){
            const angle=i*2.4,spread=radius*Math.sqrt((i+.5)/36),height=8+((i*3+(state.minute||0)*20)%20);
            box(x+Math.cos(angle)*spread,height,z+Math.sin(angle)*spread,.25,6,.25,0xc6d9d8,.3);
          }
          for(let i=0;i<4;i++)part('crown',x+Math.cos(i*2)*radius*.5,30,z+Math.sin(i*2)*radius*.5,23,7,15,0x708589);
        }else if(kind==='earthquake'){
          for(let i=0;i<16;i++){
            const angle=i*2.2,spread=radius*Math.sqrt((i+.5)/16);
            box(x+Math.cos(angle)*spread,1,z+Math.sin(angle)*spread,14,.4,1.6,0x685e4d,angle);
            part('crown',x+Math.cos(angle)*spread,2,z+Math.sin(angle)*spread,2.5,2,3,0x8a7b67);
          }
        }else if(kind==='fire'){
          for(let i=0;i<9;i++){
            const angle=i*2.4,spread=12*Math.sqrt((i+.5)/9),height=8+Math.sin(i+(state.minute||0)*3)*2;
            part('pine',x+Math.cos(angle)*spread,height/2,z+Math.sin(angle)*spread,3,height,3,i%2?0xffad47:0xea6544);
            part('crown',x+Math.cos(angle)*spread,20+i*2,z+Math.sin(angle)*spread,5,6,5,0x7c7b70);
          }
        }else if(kind==='protest'){
          // Two protester models: marchers holding placards, and pairs carrying a banner.
          // They stand only on open ground (streets, plazas, yards), never inside a building.
          const shirts=[0x7d607c,0x527787,0xb46f53,0x5f8a5a,0xc9a54a];
          const person=(px,pz,c)=>{box(px-.18,1.3,pz,.22,.9,.25,0x2f3640);box(px+.18,1.3,pz,.22,.9,.25,0x2f3640);box(px,2.25,pz,.7,1,.4,c);part('crown',px,3.05,pz,.32,.32,.32,0xd8b28a);};
          const open=(px,pz)=>CityPlan.land({x:px,z:pz})&&!CityPlan.cityAt({x:px,z:pz});
          let marchers=0,pairs=0;
          for(let i=0;i<260&&(marchers<20||pairs<5);i++){
            const a=i*2.4,sp=6+i*.45,px=x+Math.cos(a)*sp,pz=z+Math.sin(a)*sp;
            if(!open(px,pz))continue;
            if(marchers<20&&(i%4||pairs>=5)){marchers++;person(px,pz,shirts[i%5]);box(px+.45,3.3,pz,.12,2.4,.12,0x847352);box(px+.45,4.4,pz,1.6,1,.1,[0xf1dfaf,0xffffff,0xf4c9a0][i%3]);}
            else if(pairs<5){const tx=-Math.sin(a),tz=Math.cos(a);if(!open(px-tx*1.6,pz-tz*1.6)||!open(px+tx*1.6,pz+tz*1.6))continue;pairs++;person(px-tx*1.6,pz-tz*1.6,shirts[(i+2)%5]);person(px+tx*1.6,pz+tz*1.6,shirts[(i+3)%5]);box(px,3,pz,3.6,1.1,.1,[0xd9443a,0xf1d181,0x2d5aa8][i%3],-a-Math.PI/2);}
          }
        }
      }
      for(const road of CityPlan.plan.roads.filter(r=>CityPlan.roadBlocked(r)&&!r.tunnel)){
        const x=(road.a.x+road.b.x)/2,z=(road.a.z+road.b.z)/2,length=CityPlan.dist(road.a,road.b),angle=-Math.atan2(road.b.z-road.a.z,road.b.x-road.a.x);
        box(x,CityPlan.heightAt({x,z},road)+1,z,length,.2,CityPlan.roadWidth(road),0xb85a43,angle);
      }
      incidentGroup=flush();for(const mesh of water)incidentGroup.add(mesh);
    }
    function update(lotMap={},agents=[],state={}) {
      renderer.domElement.style.cursor=getTool().pan?'grab':'crosshair';
      const damageKey=JSON.stringify(state.damage||{});damageById=state.damage||{};
      if(lastRevision!==CityPlan.revision||damageKey!==lastDamageKey){
        disposeGroup(buildingMesh);refreshLabels();drawFog();if(fog)fog.position.y=tilt?-158.5:0;
        for(const c of CityPlan.plan.buildings){
          if(c.area){
            // Neighbourhood hub: where residents of this area join the road network.
            part('round',c.x,.95,c.z,c.radius,.3,c.radius,0xd9c27a);box(c.x,4,c.z,.6,6,.6,0x4a4f4a);box(c.x,6.8,c.z,6,1.8,.3,0xf1d181,-(c.rotation||0));
          }else{origin={...c,damage:damageById[c.id]||0};modelScale=CityPlan.buildingScale(c.type);drawBuilding(c.type,c);origin=null;modelScale=1;}
        }
        buildingMesh=flush();applyCityRemoval();applyStreetRemoval();drawRoads();lastRevision=CityPlan.revision;lastDamageKey=damageKey;
      }
      if(agents.length!==agentCount){
        for(const mesh of [people,roofs,wheels])if(mesh){scene.remove(mesh);mesh.dispose();}
        people=roofs=wheels=null;
        if(agents.length){
          people=new T.InstancedMesh(geometries.box,material,agents.length);
          roofs=new T.InstancedMesh(geometries.box,material,agents.length);
          wheels=new T.InstancedMesh(geometries.box,material,agents.length*4);
          for(const mesh of [people,roofs,wheels]){mesh.frustumCulled=false;mesh.castShadow=true;scene.add(mesh);}
        }
        agentCount=agents.length;
      }
      if(people){
        agents.forEach((a,i)=>{
          const person=a.kind==='resident',ground=Number.isFinite(a.height)?a.height:CityPlan.elevationAt(a),heading=a.heading||0,visible=ground>-.6?1:0;
          const body=new T.Object3D();body.position.set(a.x,ground+(person?1.5:1.25),a.z);body.rotation.set(a.pitch||0,heading,0,'YXZ');
          body.scale.set((person?.65:2.1)*visible,(person?1.45:.9)*visible,(person?.65:4.4)*visible);body.updateMatrix();people.setMatrixAt(i,body.matrix);
          const palette=[0xd87451,0xe7c16d,0x729eaa,0xb7c9ad];
          people.setColorAt(i,new T.Color(a.kind==='ambulance'?0xf5eaca:a.kind==='firetruck'?0xd55741:a.kind==='police'?0x456b9b:a.kind==='repair'?0xe2b64e:a.kind==='bus'?0xe49a57:person?0x634b71:palette[(typeof a.id==='number'?a.id:parseInt(String(a.id).split('-').at(-1),10)||0)%palette.length]));
          const roof=new T.Object3D();roof.position.set(a.x,ground+(person?2.45:2),a.z);roof.rotation.set(a.pitch||0,heading,0,'YXZ');
          roof.scale.set((person?.55:1.65)*visible,(person?.55:.65)*visible,(person?.55:2.25)*visible);roof.updateMatrix();roofs.setMatrixAt(i,roof.matrix);
          roofs.setColorAt(i,new T.Color(person?0xdbac85:0x344f58));
          for(let j=0;j<4;j++){
            const x=j%2?1.02:-1.02,z=j<2?-1.35:1.35,wheel=new T.Object3D();
            wheel.position.set(a.x+x*Math.cos(heading)+z*Math.sin(heading),ground+.78,a.z-x*Math.sin(heading)+z*Math.cos(heading));
            wheel.rotation.y=heading;wheel.scale.set(person?0:.42*visible,person?0:.65*visible,person?0:.85*visible);wheel.updateMatrix();wheels.setMatrixAt(i*4+j,wheel.matrix);
            wheels.setColorAt(i*4+j,new T.Color(0x263330));
          }
        });
        for(const mesh of [people,roofs,wheels]){mesh.instanceMatrix.needsUpdate=true;mesh.instanceColor.needsUpdate=true;}
      }
      drawControls(state.minute||360);drawIncidents(state);
      guard.material.color.set(state.hallProtected===false?0xe17461:0xf0d275);render();
    }
    const incidentCursor=new T.Mesh(new T.CircleGeometry(1,48),new T.MeshBasicMaterial({color:0xda7658,transparent:true,opacity:.28,side:T.DoubleSide,depthWrite:false}));
    incidentCursor.rotation.x=-Math.PI/2;incidentCursor.visible=false;scene.add(incidentCursor);
    function incidentPreview(p,kind){
      ghost(null);const spec=CityIncidents.types[kind];
      incidentCursor.visible=!!spec;if(spec){incidentCursor.position.set(p.x,2,p.z);incidentCursor.scale.set(spec.radius,spec.radius,1);incidentCursor.material.color.set(kind==='flood'?0x4a9fc0:kind==='protest'?0xe4bc67:0xd96d51);}
      render();
    }
    let roadDraft=null;
    function clearRoadPreview(){if(roadDraft){scene.remove(roadDraft);roadDraft.geometry.dispose();roadDraft.material.dispose();roadDraft=null;}}
    function roadPreview(points,type,bridge=false,tunnel=false,error='',overrideColor=null){
      clearRoadPreview();preview.visible=false;frontArrow.visible=false;
      if(points.length<2)return;
      const length=points.slice(1).reduce((sum,p,i)=>sum+CityPlan.dist(points[i],p),0);
      const vertices=[],half=CityPlan.widths[type]/2;let offset=0;
      for(let i=1;i<points.length;i++){
        const a=points[i-1],b=points[i],segmentLength=CityPlan.dist(a,b);if(segmentLength<.001)continue;
        const nx=-(b.z-a.z)/segmentLength,nz=(b.x-a.x)/segmentLength;
        const height=distance=>tunnel?1.3:1.3+(bridge?Math.min(12,distance/3,(length-distance)/3):0);
        const left=[a.x+nx*half,height(offset),a.z+nz*half],right=[a.x-nx*half,height(offset),a.z-nz*half];
        offset+=segmentLength;
        const endLeft=[b.x+nx*half,height(offset),b.z+nz*half],endRight=[b.x-nx*half,height(offset),b.z-nz*half];
        vertices.push(...right,...left,...endLeft,...right,...endLeft,...endRight);
      }
      const geometry=new T.BufferGeometry();geometry.setAttribute('position',new T.Float32BufferAttribute(vertices,3));geometry.computeVertexNormals();
      const material=new T.MeshBasicMaterial({color:overrideColor||(error?0xed705a:0x7fd6bd),transparent:true,opacity:.8,side:T.DoubleSide,depthWrite:false});
      roadDraft=new T.Mesh(geometry,material);scene.add(roadDraft);
      const end=points.at(-1);preview.visible=true;preview.scale.set(snapTolerance()*1.2,snapTolerance()*1.2,1);preview.position.set(end.x,1.8,end.z);preview.rotation.z=0;preview.material.color.copy(material.color);
      render();
    }
    function snapTolerance(){return Math.max(4,Math.min(30,(camera.right-camera.left)/Math.max(1,container.clientWidth)*10));}
    function ghost(p,type,rotation=0,start=null,bridge=false,tunnel=false) {
      clearRoadPreview();incidentCursor.visible=false;
      preview.visible=!!p;frontArrow.visible=!!p&&!CityPlan.widths[type];if(!p){if(previewLine){scene.remove(previewLine);previewLine.geometry.dispose();previewLine=null;}render();return;}
      if(CityPlan.controlTypes[type]){
        const placement=CityPlan.controlPlacement(p,type);preview.visible=!!placement;frontArrow.visible=!!placement?.approach;
        if(placement){const arm=placement.approach;preview.position.set(placement.x,1.5,placement.z);preview.scale.set(15,15,1);preview.rotation.z=0;preview.material.color.set(0xffdb87);
          if(arm){frontArrow.position.set(placement.x+arm.x*25,2,placement.z+arm.z*25);frontArrow.setDirection(new T.Vector3(-arm.x,0,-arm.z));frontArrow.setLength(15,5,4);}}
        render();return;
      }
      if(CityPlan.widths[type]){
        preview.visible=true;frontArrow.visible=false;preview.scale.set(snapTolerance()*1.2,snapTolerance()*1.2,1);
        preview.position.set(p.x,1.5,p.z);preview.rotation.z=0;preview.material.color.set(CityPlan.land(p)?0x7fd6bd:0xed705a);render();return;
      }
      const size=CityPlan.buildingScale(type)*7.8||8;frontArrow.position.set(p.x,2,p.z);frontArrow.setDirection(new T.Vector3(Math.sin(rotation),0,Math.cos(rotation)));frontArrow.setLength(size*.8,4,3);preview.scale.set(size,size,1);preview.position.set(p.x,1.5,p.z);preview.rotation.z=-rotation;
      preview.material.color.set(CityPlan.buildingError({...p,type})?0xda785d:0xf5db96);
      if(previewLine){scene.remove(previewLine);previewLine.geometry.dispose();previewLine=null;}
      if(start){previewLine=new T.Line(new T.BufferGeometry().setFromPoints([new T.Vector3(start.x,2,start.z),new T.Vector3(p.x,2,p.z)]),new T.LineBasicMaterial({color:CityPlan.roadError(start,p,type,bridge,tunnel)?0xe87564:0xffe2a0}));scene.add(previewLine);preview.visible=false;}
      render();
    }
    const pressed=new Set();let cameraFrame=performance.now();
    window.addEventListener('keydown',e=>{
      if(e.target.matches('input,select,textarea')||document.querySelector('dialog[open]'))return;
      const key=e.key.toLowerCase();
      if('wasdqe'.includes(key)&&key.length===1){e.preventDefault();pressed.add(key);}
    });
    window.addEventListener('keyup',e=>pressed.delete(e.key.toLowerCase()));
    window.addEventListener('blur',()=>pressed.clear());
    function cameraLoop(now){
      const elapsed=Math.min(.1,(now-cameraFrame)/1000);cameraFrame=now;
      if(pressed.size){
        const rate=450*elapsed/scale,dx=(Number(pressed.has('d'))-Number(pressed.has('a')))*rate,dz=(Number(pressed.has('s'))-Number(pressed.has('w')))*rate;
        pan.x+=dx*Math.cos(azimuth)+dz*Math.sin(azimuth);pan.z+=-dx*Math.sin(azimuth)+dz*Math.cos(azimuth);
        azimuth+=(Number(pressed.has('e'))-Number(pressed.has('q')))*elapsed;
        resize();
      }
      requestAnimationFrame(cameraLoop);
    }
    requestAnimationFrame(cameraLoop);
    new ResizeObserver(resize).observe(container);resize();
    return {update,ghost,incidentPreview,roadPreview,snapTolerance,zoom(delta){scale=Math.max(.7,Math.min(60,scale*(delta>0?1.4:1/1.4)));resize();},resetView(){scale=1;azimuth=0;elevationAngle=Math.PI/2-.001;tilt=false;pan={x:(CityPlan.activeBounds.minX+CityPlan.activeBounds.maxX)/2,z:(CityPlan.activeBounds.minZ+CityPlan.activeBounds.maxZ)/2};resize();},focusLevel(){scale=1;pan={x:(CityPlan.activeBounds.minX+CityPlan.activeBounds.maxX)/2,z:(CityPlan.activeBounds.minZ+CityPlan.activeBounds.maxZ)/2};resize();},toggleView(mode){tilt=mode==='3d'?true:mode==='top'?false:!tilt;elevationAngle=tilt?Math.PI*.3:Math.PI/2-.001;if(!tilt)azimuth=0;resize();return tilt;},get is3D(){return tilt;}};
  }
  window.CityWorld={mount};
})();
