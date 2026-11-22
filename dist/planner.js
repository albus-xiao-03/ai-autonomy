// Continuous map geometry, player-built roads and directed routing.
window.CityPlan = (() => {
  const geo=BOSTON_GEOGRAPHY;
  const polygons=geo.polygons.map(poly=>poly.map(([x,z])=>({x,z})));
  const holes=geo.holes.map(group=>group.map(poly=>poly.map(([x,z])=>({x,z}))));
  const point=([lon,lat])=>({x:(lon-geo.origin.lon)*geo.metersPerDegree.x,z:(geo.origin.lat-lat)*geo.metersPerDegree.z});
  // Meter-sized landmark envelopes. Models are simplified representations.
  const landmarks = [
    {name:'City Hall',site:'hall',...point([-71.0577,42.3603]),radius:60,scale:12},
    {name:'TD Garden',site:'garden',...point([-71.0621,42.3663]),radius:95,scale:20},
    {name:'Mass General',site:'hospital',...point([-71.0688,42.3625]),radius:55,scale:13},
    {name:'Old North Church',site:'church',...point([-71.0545,42.3663]),radius:25,scale:5},
    {name:'Quincy Market',site:'market',...point([-71.0542,42.3600]),radius:45,scale:15},
    {name:'Boston Common',site:'common',...point([-71.0665,42.3550]),radius:75,scale:20},
    {name:'State House',site:'statehouse',...point([-71.0638,42.3588]),radius:55,scale:13}
  ];
  landmarks.forEach(l=>{l.scale*=geo.scale;l.radius*=geo.scale;});
  const widths={highway:14,oneway:5,twoway:8};
  const buildingScale=type=>({residential:2.2,office:5,shop:3,social:3.8,park:5,parking:5}[type]||1)*geo.scale;
  const plan={buildings:[],roads:[],controls:[]};
  const controlTypes={signal:'Traffic lights',stop:'Stop sign',yield:'Yield sign'};
  let revision=0,graph=null,junctionCache=null,level=1;
  const stages=[{minX:-500,maxX:850,minZ:200,maxZ:1050},{minX:-650,maxX:1200,minZ:-250,maxZ:1100},{minX:-1650,maxX:1450,minZ:-450,maxZ:1335},{minX:-1650,maxX:1650,minZ:-1335,maxZ:1335}];
  const dist=(a,b)=>Math.hypot(a.x-b.x,a.z-b.z);
  function inside(p,poly) {
    let yes=false;
    for(let i=0,j=poly.length-1;i<poly.length;j=i++) {
      const a=poly[i],b=poly[j];
      if((a.z>p.z)!==(b.z>p.z)&&p.x<(b.x-a.x)*(p.z-a.z)/(b.z-a.z)+a.x)yes=!yes;
    }
    return yes;
  }
  const land=p=>polygons.some((poly,i)=>inside(p,poly)&&!holes[i].some(h=>inside(p,h)));
  function projection(p,a,b) {
    const dx=b.x-a.x,dz=b.z-a.z;
    const t=Math.max(0,Math.min(1,((p.x-a.x)*dx+(p.z-a.z)*dz)/(dx*dx+dz*dz||1)));
    return {x:a.x+dx*t,z:a.z+dz*t,t};
  }
  function changed() {revision++;graph=null;junctionCache=null;}
  function buildingError(p,ignore) {
    const radius=buildingScale(p.type||'residential')*4.2;
    if(!land(p)||[[-radius,-radius],[radius,-radius],[radius,radius],[-radius,radius]].some(([x,z])=>!land({x:p.x+x,z:p.z+z})))return 'Choose dry land with room for the whole building.';
    if(landmarks.some(l=>dist(p,l)<l.radius+radius))return 'This historical landmark and its grounds are protected.';
    if(plan.buildings.some(b=>b.id!==ignore&&dist(b,p)<(b.radius||buildingScale(b.type)*4.2)+radius))return 'Leave room between buildings.';
    if(plan.roads.some(r=>dist(p,projection(p,r.a,r.b))<widths[r.type]/2+radius))return 'This position overlaps a road.';
    return '';
  }
  function roadError(a,b,type,bridge=false,tunnel=false) {
    const bounds=stages[level-1];if([a,b].some(p=>p.x<bounds.minX||p.x>bounds.maxX||p.z<bounds.minZ||p.z>bounds.maxZ))return 'Complete this level to unlock that part of Boston.';
    if(!land(a)||!land(b))return 'Both road ends must be on dry land.';
    let crossesWater=false;
    if(dist(a,b)<10)return 'Draw a longer road.';
    for(let i=0,n=Math.ceil(dist(a,b)/3);i<=n;i++){
      const p={x:a.x+(b.x-a.x)*i/n,z:a.z+(b.z-a.z)*i/n};
      if(!land(p)){crossesWater=true;if(!bridge&&!tunnel)return 'Choose bridge or tunnel mode to cross water.';}
      if(!bridge&&!tunnel){const dx=(b.z-a.z)/dist(a,b)*widths[type]/2,dz=(a.x-b.x)/dist(a,b)*widths[type]/2;if(!land({x:p.x+dx,z:p.z+dz})||!land({x:p.x-dx,z:p.z-dz}))return 'Leave room for the full road width along the shore.';}
    }
    if(landmarks.some(l=>dist(l,projection(l,a,b))<l.radius+widths[type]/2&&(!tunnel||Math.min(dist(l,a),dist(l,b))<l.radius+50)))return 'Route the road around the protected landmark.';
    if(plan.buildings.some(p=>dist(p,projection(p,a,b))<(p.radius?p.radius-12:buildingScale(p.type)*4.2)+widths[type]/2&&(!tunnel||Math.min(dist(p,a),dist(p,b))<(p.radius||30)+50)))return 'This road crosses a building.';
    if(plan.roads.some(r=>!!r.bridge===bridge&&!!r.tunnel===tunnel&&dist(a,projection(a,r.a,r.b))<.5&&dist(b,projection(b,r.a,r.b))<.5))return 'A road already follows this section.';
    return '';
  }
  function snap(p) {
    let best=p,limit=12;
    for(const b of plan.buildings){if(!b.area)continue;const p2={x:b.x+Math.sin(b.rotation||0)*b.radius,z:b.z+Math.cos(b.rotation||0)*b.radius};if(dist(p,p2)<12)return p2;}
    for(const r of plan.roads) {
      const q=projection(p,r.a,r.b),d=dist(p,q);
      if(d<limit&&Math.abs(heightAt(q,r))<.75){best=q;limit=d;}
      for(const end of [r.a,r.b])if(dist(p,end)<12){best=end;limit=0;}
    }
    return {x:best.x,z:best.z};
  }
  function heightAt(p,r) {
    const q=projection(p,r.a,r.b);
    const rise=Math.min(12,dist(r.a,q)/3,dist(r.b,q)/3);return r.tunnel?-rise:r.bridge?rise:0;
  }
  function buildGraph() {
    const cuts=plan.roads.map(()=>[0,1]);
    // Split every crossing, including T junctions, before adding directed edges.
    for(let i=0;i<plan.roads.length;i++)for(let j=i+1;j<plan.roads.length;j++){
      const a=plan.roads[i],b=plan.roads[j],u={x:a.b.x-a.a.x,z:a.b.z-a.a.z},v={x:b.b.x-b.a.x,z:b.b.z-b.a.z};
      const cross=(p,q)=>p.x*q.z-p.z*q.x,den=cross(u,v),w={x:b.a.x-a.a.x,z:b.a.z-a.a.z};
      if(Math.abs(den)>.0001) {
        const t=cross(w,v)/den,s=cross(w,u)/den;
        if(t>=0&&t<=1&&s>=0&&s<=1){const p={x:a.a.x+u.x*t,z:a.a.z+u.z*t};if(Math.abs(heightAt(p,a)-heightAt(p,b))<.75){cuts[i].push(t);cuts[j].push(s);}}
      } else {
        for(const end of [b.a,b.b]){const p=projection(end,a.a,a.b);if(dist(p,end)<.05)cuts[i].push(p.t);}
        for(const end of [a.a,a.b]){const p=projection(end,b.a,b.b);if(dist(p,end)<.05)cuts[j].push(p.t);}
      }
    }
    const nodes=new Map(),edges=[];
    const node=p=>{const key=p.x.toFixed(3)+','+p.z.toFixed(3)+','+(p.height||0).toFixed(3);if(!nodes.has(key))nodes.set(key,{...p,key,edges:[]});return nodes.get(key);};
    plan.roads.forEach((r,i)=>{
      const ts=[...new Set(cuts[i])].sort((a,b)=>a-b);
      for(let j=1;j<ts.length;j++){
        const at=t=>{const p={x:r.a.x+(r.b.x-r.a.x)*t,z:r.a.z+(r.b.z-r.a.z)*t};return {...p,height:heightAt(p,r)};};
        const a=node(at(ts[j-1])),b=node(at(ts[j]));
        const weight=dist(a,b)/(r.type==='highway'?2:1);
        a.edges.push({to:b,weight});if(r.type!=='oneway')b.edges.push({to:a,weight});
        edges.push({a,b,type:r.type,weight,road:r});
      }
    });
    graph={nodes:[...nodes.values()],edges};return graph;
  }
  function junctions() {
    if(junctionCache)return junctionCache;
    const g=graph||buildGraph(),points=new Map();
    for(const edge of g.edges)for(const [node,other] of [[edge.a,edge.b],[edge.b,edge.a]]) {
      if(!points.has(node.key))points.set(node.key,{x:node.x,z:node.z,arms:[]});
      const length=dist(node,other);if(length<.01)continue;
      const direction={x:(other.x-node.x)/length,z:(other.z-node.z)/length};
      const junction=points.get(node.key);
      if(!junction.arms.some(arm=>Math.abs(arm.x-direction.x)<.001&&Math.abs(arm.z-direction.z)<.001))junction.arms.push({...direction,road:edge.road});
    }
    junctionCache=[...points.values()].filter(j=>j.arms.length>=2);return junctionCache;
  }
  function controlPlacement(p,kind) {
    const junction=junctions().filter(j=>dist(p,j)<(kind==='signal'?28:65)).sort((a,b)=>dist(p,a)-dist(p,b))[0];
    if(!junction)return null;
    if(kind==='signal')return {x:junction.x,z:junction.z,approach:null};
    const arm=junction.arms.map(arm=>{
      const along=(p.x-junction.x)*arm.x+(p.z-junction.z)*arm.z;
      const side=Math.abs((p.x-junction.x)*arm.z-(p.z-junction.z)*arm.x);
      return {arm,along,side};
    }).filter(v=>v.along>3&&v.side<widths[v.arm.road.type]/2+8).sort((a,b)=>a.side-b.side)[0]?.arm;
    return arm?{x:junction.x,z:junction.z,approach:{x:arm.x,z:arm.z}}:null;
  }
  function roadSurfaces(margin=0) {
    const shapes=[];
    for(const road of plan.roads.filter(r=>!r.bridge&&!r.tunnel)){
      const length=dist(road.a,road.b),nx=-(road.b.z-road.a.z)/length,nz=(road.b.x-road.a.x)/length,radius=widths[road.type]/2+margin;
      const p=(base,sign)=>[base.x+nx*radius*sign,base.z+nz*radius*sign];
      const a=p(road.a,1),b=p(road.b,1),c=p(road.b,-1),d=p(road.a,-1);
      shapes.push([[a,b,c,d,a]]);
      for(const end of [road.a,road.b]) {
        const ring=Array.from({length:25},(_,i)=>[end.x+Math.cos(i*Math.PI/12)*radius,end.z+Math.sin(i*Math.PI/12)*radius]);
        shapes.push([ring]);
      }
    }
    return shapes.length?polygonClipping.union(...shapes):[];
  }
  function signalState(control,time,horizontal) {
    const phase=((time*60)%40+40)%40;
    return horizontal?(phase<17?'green':phase<20?'amber':'red'):(phase>=20&&phase<37?'green':phase>=37?'amber':'red');
  }
  function waitAt(control,time,direction) {
    if(control.kind==='signal') {
      const horizontal=Math.abs(direction.x)>=Math.abs(direction.z);
      for(let seconds=0;seconds<=40;seconds++)if(signalState(control,time+seconds/60,horizontal)==='green')return seconds/60;
      return 0;
    }
    if(control.approach&&direction.x*control.approach.x+direction.z*control.approach.z>-.8)return 0;
    return control.kind==='stop'?3/60:1/60;
  }
  function access(building) {
    const scale=building.scale||buildingScale(building.type);
    const rotation=building.rotation||0;
    const facing={x:Math.sin(rotation),z:Math.cos(rotation)};
    const entrance={x:building.x+facing.x*(building.radius||scale*2.5),z:building.z+facing.z*(building.radius||scale*2.5)};
    const options=plan.roads.map(road=>{
      const p=projection(entrance,road.a,road.b),length=dist(entrance,p);
      const forward=(p.x-entrance.x)*facing.x+(p.z-entrance.z)*facing.z;
      return {road,p,entrance,length,forward};
    }).sort((a,b)=>a.length-b.length);
    return options.find(option=>{
      if(option.length-widths[option.road.type]/2>20*geo.scale||option.forward<.5*option.length)return false;
      for(let i=0,n=Math.max(1,Math.ceil(option.length/2));i<=n;i++){
        const p={x:entrance.x+(option.p.x-entrance.x)*i/n,z:entrance.z+(option.p.z-entrance.z)*i/n};
        if(!land(p))return false;
        if(plan.buildings.some(b=>b.id!==building.id&&dist(b,p)<(b.radius||buildingScale(b.type)*3.5)))return false;
      }
      return true;
    })||null;
  }
  function route(a,b) {
    const g=graph||buildGraph();
    if(!g.edges.length)return null;
    const attach=p=>{
      const building=[...plan.buildings,...landmarks].find(b=>dist(b,p)<.01);
      const connection=building?access(building):null;
      if(building&&!connection)return null;
      const target=connection?.p||p;
      const edge=g.edges.map(e=>({...e,p:projection(target,e.a,e.b)})).sort((x,y)=>dist(target,x.p)-dist(target,y.p))[0];
      return {...edge,entrance:connection?.entrance};
    };
    const start=attach(a),end=attach(b);
    if(!start||!end)return null;
    if(dist(a,start.p)>100||dist(b,end.p)>100)return null;
    const values=new Map(),previous=new Map(),open=new Set();
    const seed=(n,c)=>{if(c<(values.get(n)??Infinity)){values.set(n,c);open.add(n);}};
    seed(start.b,dist(start.p,start.b));if(start.type!=='oneway')seed(start.a,dist(start.p,start.a));
    while(open.size){
      const n=[...open].sort((x,y)=>values.get(x)-values.get(y))[0];open.delete(n);
      for(const e of n.edges)if(values.get(n)+e.weight<(values.get(e.to)??Infinity)){
        values.set(e.to,values.get(n)+e.weight);previous.set(e.to,n);open.add(e.to);
      }
    }
    const choices=[end.a];if(end.type!=='oneway')choices.push(end.b);
    const last=choices.filter(n=>values.has(n)).sort((x,y)=>(values.get(x)??Infinity)+dist(x,end.p)-(values.get(y)??Infinity)-dist(y,end.p))[0];
    let best=null,cost=Infinity;
    if(last&&values.has(last)) {
      const path=[];for(let n=last;n;n=previous.get(n))path.unshift({x:n.x,z:n.z,height:n.height||0});
      best=[a,...(start.entrance?[start.entrance]:[]),start.p,...path,end.p,...(end.entrance?[end.entrance]:[]),b];cost=values.get(last)+dist(last,end.p);
    }
    if(start.a===end.a&&start.b===end.b&&(start.type!=='oneway'||start.p.t<=end.p.t)&&dist(start.p,end.p)<cost)best=[a,...(start.entrance?[start.entrance]:[]),start.p,end.p,...(end.entrance?[end.entrance]:[]),b];
    if(!best)return null;
    const graded=[{...best[0],height:best[0].height||0}];
    for(let i=1;i<best.length;i++){
      const a=best[i-1],b=best[i],road=plan.roads.find(r=>dist(a,projection(a,r.a,r.b))<.05&&dist(b,projection(b,r.a,r.b))<.05);
      const count=road&&(road.bridge||road.tunnel)?Math.max(1,Math.ceil(dist(a,b)/8)):1;
      for(let j=1;j<=count;j++){const t=j/count,p={x:a.x+(b.x-a.x)*t,z:a.z+(b.z-a.z)*t};graded.push({...p,height:road?heightAt(p,road):b.height||0});}
    }
    return graded;
  }
  return {plan,polygons,holes,bounds:geo.bounds,scale:geo.scale,buildingScale,access,landmarks,widths,land,dist,projection,buildingError,roadError,snap,route,junctions,controlTypes,controlPlacement,roadSurfaces,signalState,waitAt,
    heightAt,
    elevationAt(p){for(const r of plan.roads)if((r.bridge||r.tunnel)&&dist(p,projection(p,r.a,r.b))<widths[r.type])return this.heightAt(p,r);for(const b of plan.buildings){const c=access(b);if(c?.road.bridge){const q=projection(p,c.entrance,c.p);if(dist(p,q)<3)return this.heightAt(c.p,c.road)*q.t;}}return 0;},
    seedArcade(next=1){
      level=Math.max(1,Math.min(4,next));
      const areas=[
        ['beacon','Beacon Hill','residential',-71.0678,42.3598,Math.PI],
        ['north','North End','residential',-71.0540,42.3646,Math.PI*1.5],
        ['charles','Charlestown','residential',-71.0615,42.3750,0],
        ['west','West End','residential',-71.0670,42.3648,Math.PI*.5],
        ['kendall','Kendall Square','office',-71.0818,42.3656,Math.PI*.5],
        ['financial','Financial District','office',-71.0555,42.3570,Math.PI],
        ['government','Government Center','office',-71.0600,42.3617,Math.PI*1.5],
        ['waterfront','Waterfront','social',-71.0519,42.3624,Math.PI*1.5]
      ];
      const unlocked=[['beacon','government'],['beacon','government','west','north'],['beacon','government','west','north','kendall','financial','waterfront'],areas.map(a=>a[0])][level-1];
      plan.buildings=areas.filter(a=>unlocked.includes(a[0])).map(([id,label,type,lon,lat,rotation])=>({id,label,type,...point([lon,lat]),rotation,radius:70,area:true}));
      if(!plan.roads.some(r=>r.fixed))plan.roads.unshift({id:'through-highway',a:{x:-430,z:275},b:{x:800,z:275},type:'highway',fixed:true});
      changed();
    },
    get level(){return level;},
    get activeBounds(){return stages[level-1];},
    get revision(){return revision;},changed,
    district:p=>p.x>300&&p.z<400?'North End':p.z<400?'West End':'Downtown',
    control(p,kind){
      const location=controlPlacement(p,kind);
      if(!location)return kind==='signal'?'Choose a connected road junction.':'Click the incoming street near a junction. The arrow points toward the junction.';
      const existing=plan.controls.find(c=>dist(c,location)<.1&&(kind==='signal'?c.kind==='signal':c.approach&&c.approach.x*location.approach.x+c.approach.z*location.approach.z>.99));
      if(existing){existing.kind=kind;existing.approach=location.approach;}
      else plan.controls.push({id:Date.now()+Math.random(),kind,...location});
      changed();return '';
    },
    place(p,type,rotation=0){const error=buildingError({...p,type});if(error)return error;plan.buildings.push({id:Date.now()+Math.random(),x:p.x,z:p.z,type,rotation});changed();return '';},
    road(a,b,type,bridge=false,tunnel=false){a=snap(a);b=snap(b);const error=roadError(a,b,type,bridge,tunnel);if(error)return error;plan.roads.push({id:Date.now()+Math.random(),a,b,type,bridge,tunnel});changed();return '';},
    remove(p){const control=plan.controls.find(c=>dist(p,{x:c.x+(c.approach?.x||0)*20,z:c.z+(c.approach?.z||0)*20})<9);if(control){plan.controls.splice(plan.controls.indexOf(control),1);changed();return '';}const b=plan.buildings.find(b=>dist(b,p)<(b.radius||buildingScale(b.type)*4.2));if(b?.area)return 'This district is fixed. Connect its gold access point with roads.';if(b)plan.buildings.splice(plan.buildings.indexOf(b),1);else{const r=plan.roads.find(r=>dist(p,projection(p,r.a,r.b))<widths[r.type]/2+1);if(!r)return 'Select a building or road to remove.';if(r.fixed)return 'The through highway is the fixed entry route. Connect local roads to it.';plan.roads.splice(plan.roads.indexOf(r),1);}changed();const live=junctions();plan.controls=plan.controls.filter(c=>live.some(j=>dist(c,j)<.1));return '';},
    load(saved){if(saved?.version!==2)return;for(const b of saved.buildings||[])if(['residential','office','shop','social','park','parking'].includes(b.type)&&Number.isFinite(b.rotation)&&!buildingError(b))plan.buildings.push(b);for(const r of saved.roads||[])if(widths[r.type]&&r.a&&r.b&&!roadError(r.a,r.b,r.type,!!r.bridge,!!r.tunnel))plan.roads.push(r);changed();}
  };
})();
window.CITY_LOTS=[];
window.CITY_HALL={...CityPlan.landmarks[0],radius:165};
window.CITY_HOSPITAL=CityPlan.landmarks[2];
window.CITY_DISTRICTS=['West End','North End','Downtown'];
window.CITY_PATH=(x,z,tx,tz)=>CityPlan.route({x,z},{x:tx,z:tz});
