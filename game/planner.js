// Continuous map geometry, player-built roads and directed routing.
window.CityPlan = (() => {
  // Map layout: 'real' (default) uses real Boston buildings as neighbourhood anchors and drops the old
  // arcade pads/envelopes; 'arcade' keeps the old layout. Chosen in index.html before this file loads.
  const LAYOUT=window.BOROUGH_LAYOUT==='arcade'?'arcade':'real';
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
  const plan={buildings:[],roads:[],controls:[],removedCity:[]};
  let closures=[],closureSignature='',protectedRegion=null;
  const roadWidth=road=>road.width||widths[road.type];
  const controlTypes={signal:'Traffic lights',stop:'Stop sign',yield:'Yield sign'};
  let revision=0,graph=null,junctionCache=null;
  // One fixed map: the Boston area of the reference screenshot (no levels).
  const BOUNDS={minX:-1127,maxX:1415,minZ:-1135,maxZ:1102};
  // Real Boston buildings (OpenStreetMap). Historical/unique ones are permanently protected;
  // fire, police and medical sites carry an author-set lock. Everything else can be bulldozed.
  const city=(window.BOSTON_BUILDINGS?.buildings||[]).map(b=>({...b,locked:b.k==='unique'?'permanent':['fire','police','medical'].includes(b.k)?'author':null}));
  const cityGrid=new Map(),CELL=100;
  for(const b of city){const r=Math.hypot(b.w,b.d)/2;for(let gx=Math.floor((b.x-r)/CELL);gx<=Math.floor((b.x+r)/CELL);gx++)for(let gz=Math.floor((b.z-r)/CELL);gz<=Math.floor((b.z+r)/CELL);gz++){const k=gx+','+gz;if(!cityGrid.has(k))cityGrid.set(k,[]);cityGrid.get(k).push(b);}}
  // Bulldozed buildings (saved) plus buildings cleared under the neighbourhood hubs (derived, not saved).
  let removedSet=new Set(),removedKey='',hubCleared=new Set(),hubVersion=0;
  function removed(){const key=plan.removedCity.join(',')+'|'+hubVersion;if(key!==removedKey){removedKey=key;removedSet=new Set([...plan.removedCity,...hubCleared]);}return removedSet;}
  function cityNear(p,r=0){const out=new Set(),gone=removed();for(let gx=Math.floor((p.x-r)/CELL);gx<=Math.floor((p.x+r)/CELL);gx++)for(let gz=Math.floor((p.z-r)/CELL);gz<=Math.floor((p.z+r)/CELL);gz++)for(const b of cityGrid.get(gx+','+gz)||[])if(!gone.has(b.id))out.add(b);return [...out];}
  // Oriented-rectangle test in the building's own frame (r is the footprint edge angle).
  function inCityRect(b,p,pad=0){const dx=p.x-b.x,dz=p.z-b.z,c=Math.cos(b.r),s=Math.sin(b.r);return Math.abs(dx*c+dz*s)<=b.w/2+pad&&Math.abs(-dx*s+dz*c)<=b.d/2+pad;}
  function cityAt(p){return cityNear(p,0).find(b=>inCityRect(b,p,1))||null;}
  function cityBlocks(p,radius){return cityNear(p,radius).some(b=>inCityRect(b,p,radius*.7));}
  function cityCrossed(a,b,width){const n=Math.ceil(dist(a,b)/4);for(let i=0;i<=n;i++){const p={x:a.x+(b.x-a.x)*i/n,z:a.z+(b.z-a.z)*i/n};if(cityNear(p,width).some(c=>inCityRect(c,p,width/2-.5)))return true;}return false;}
  const stages=[BOUNDS];
  // Real neighbourhood centres; a point belongs to the nearest one (replaces the old two-line rule).
  const NEIGHBOURHOODS=[['North End',-71.0542,42.3647],['West End',-71.0655,42.3645],['Beacon Hill',-71.0680,42.3585],['Government Center',-71.0590,42.3600],['Financial District',-71.0560,42.3565],['Waterfront',-71.0510,42.3605],['North Station',-71.0615,42.3660],['Charlestown',-71.0610,42.3735],['East Cambridge',-71.0770,42.3680]].map(([name,lon,lat])=>({name,x:(lon-geo.origin.lon)*geo.metersPerDegree.x,z:(geo.origin.lat-lat)*geo.metersPerDegree.z}));
  // Real Boston streets (OpenStreetMap), split at intersections. Players can bulldoze, upgrade or
  // restore them. I-93 stays in highway-data.js as fixed roads.
  const realStreetRoads=(()=>{const out=[];for(const piece of (window.BOSTON_STREETS?.pieces||[])){const span=(a,b)=>Math.hypot(a.x-b.x,a.z-b.z),pts=piece.p.map(([x,z])=>({x,z})),total=pts.slice(1).reduce((sum,q,i)=>sum+span(pts[i],q),0);let offset=0;for(let i=1;i<pts.length;i++){const a=pts[i-1],b=pts[i],length=span(a,b);if(length<.05)continue;out.push({id:'osm-'+piece.id+'-'+i,pathId:'osm-'+piece.id,pathStart:offset,pathEnd:offset+length,pathLength:total,a,b,type:piece.t,width:piece.w,oneway:piece.t==='oneway',bridge:!!piece.b,tunnel:!!piece.u,real:true,name:piece.n||''});offset+=length;}}return out;})();
  const realStreetById=new Map(realStreetRoads.map(r=>[r.id,r])),realPathIds=[...new Set(realStreetRoads.map(r=>r.pathId))];
  function setRealStreets(removedPaths=[],modified=[]){const gone=new Set(removedPaths),mods=new Map(modified.map(r=>[r.id,r]));plan.roads=plan.roads.filter(r=>!r.real).concat(realStreetRoads.filter(r=>!gone.has(r.pathId)).map(r=>{const m=mods.get(r.id);return m?{...m,oneway:m.type==='oneway'}:{...r};}));changed();}
  // Real traffic signals and stop signs (OpenStreetMap), snapped to the real junctions they control.
  function setRealSignals(){
    const data=window.BOSTON_SIGNALS;plan.controls=plan.controls.filter(c=>!c.real);if(!data)return 0;
    const js=openJunctions(),taken=new Set();
    const nearestJunction=(p,limit)=>{let best=null;for(const j of js){const d=dist(p,j);if(d<limit&&(!best||d<best.d))best={j,d};}return best;};
    for(const [x,z] of data.signals){
      const hit=nearestJunction({x,z},22);if(!hit)continue;
      const key=hit.j.x.toFixed(2)+','+hit.j.z.toFixed(2);if(taken.has(key))continue;taken.add(key);
      plan.controls.push({id:'osm-signal-'+key,kind:'signal',x:hit.j.x,z:hit.j.z,approach:null,real:true});
    }
    for(const [x,z] of data.stops){
      const p={x,z},hit=nearestJunction(p,30);if(!hit||hit.d<.5)continue;
      const key=hit.j.x.toFixed(2)+','+hit.j.z.toFixed(2);if(taken.has(key))continue;
      const toward={x:(p.x-hit.j.x)/hit.d,z:(p.z-hit.j.z)/hit.d};
      const arm=hit.j.arms.filter(incomingArm).sort((a,b)=>(b.x*toward.x+b.z*toward.z)-(a.x*toward.x+a.z*toward.z))[0];
      if(!arm||arm.x*toward.x+arm.z*toward.z<.5)continue;
      if(plan.controls.some(c=>c.kind==='stop'&&dist(c,hit.j)<.1&&c.approach.x*arm.x+c.approach.z*arm.z>.95))continue;
      plan.controls.push({id:'osm-stop-'+key+'-'+arm.x.toFixed(2),kind:'stop',x:hit.j.x,z:hit.j.z,approach:{x:arm.x,z:arm.z},real:true});
    }
    return plan.controls.filter(c=>c.real).length;
  }
  function removedRealStreets(){const present=new Set(plan.roads.filter(r=>r.real).map(r=>r.pathId));return realPathIds.filter(id=>!present.has(id));}
  function realOriginal(r){const o=r.real&&realStreetById.get(r.id);return !!o&&o.type===r.type&&!!o.oneway===!!r.oneway&&!!o.bridge===!!r.bridge&&!!o.tunnel===!!r.tunnel&&o.a.x===r.a.x&&o.a.z===r.a.z;}
  function modifiedRealStreets(){return plan.roads.filter(r=>r.real&&!realOriginal(r));}
  // Spatial grids keep routing, junctions and lane lookups fast with thousands of road segments.
  const GRID=60;let roadGridCache=null,junctionGridCache=null;
  function cellsFor(minX,maxX,minZ,maxZ,visit){for(let gx=Math.floor(minX/GRID);gx<=Math.floor(maxX/GRID);gx++)for(let gz=Math.floor(minZ/GRID);gz<=Math.floor(maxZ/GRID);gz++)visit(gx+','+gz);}
  function roadGrid(){if(roadGridCache?.revision===revision&&roadGridCache.count===plan.roads.length)return roadGridCache.grid;const grid=new Map();for(const r of plan.roads){const pad=roadWidth(r)/2+1;cellsFor(Math.min(r.a.x,r.b.x)-pad,Math.max(r.a.x,r.b.x)+pad,Math.min(r.a.z,r.b.z)-pad,Math.max(r.a.z,r.b.z)+pad,k=>{if(!grid.has(k))grid.set(k,[]);grid.get(k).push(r);});}roadGridCache={revision,count:plan.roads.length,grid};return grid;}
  function roadsNear(p,radius=0){const grid=roadGrid(),out=new Set();cellsFor(p.x-radius,p.x+radius,p.z-radius,p.z+radius,k=>{for(const r of grid.get(k)||[])out.add(r);});return [...out];}
  function closestRoad(p,maxDistance){let best=null,bestDistance=maxDistance;for(const r of roadsNear(p,maxDistance)){const d=dist(p,projection(p,r.a,r.b));if(d<=bestDistance){best=r;bestDistance=d;}}return best?{road:best,p:projection(p,best.a,best.b)}:null;}
  function junctionDistance(p,maxDistance=24){if(junctionGridCache?.revision!==revision){const grid=new Map();for(const j of junctions())cellsFor(j.x,j.x,j.z,j.z,k=>{if(!grid.has(k))grid.set(k,[]);grid.get(k).push(j);});junctionGridCache={revision,grid};}let best=Infinity;cellsFor(p.x-maxDistance,p.x+maxDistance,p.z-maxDistance,p.z+maxDistance,k=>{for(const j of junctionGridCache.grid.get(k)||[])best=Math.min(best,dist(p,j));});return best;}
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
    const bounds=BOUNDS;
    if(p.x-radius<bounds.minX||p.x+radius>bounds.maxX||p.z-radius<bounds.minZ||p.z+radius>bounds.maxZ)return 'That land is outside the Boston map.';
    if(!land(p)||[[-radius,-radius],[radius,-radius],[radius,radius],[-radius,radius]].some(([x,z])=>!land({x:p.x+x,z:p.z+z})))return 'Choose dry land with room for the whole building.';
    if(!(protectedRegion&&dist(p,protectedRegion)<protectedRegion.radius)&&closures.some(c=>dist(p,c)<c.radius+radius))return 'This land is affected by an active incident.';
    if(LAYOUT==='arcade'&&landmarks.some(l=>dist(p,l)<l.radius+radius))return 'This historical landmark and its grounds are protected.';
    if(cityBlocks(p,radius))return 'A Boston building stands here. Bulldoze it first.';
    if(plan.buildings.some(b=>b.id!==ignore&&dist(b,p)<(b.radius||buildingScale(b.type)*4.2)+radius))return 'Leave room between buildings.';
    if(plan.roads.some(r=>Math.abs(heightAt(projection(p,r.a,r.b),r))<3&&dist(p,projection(p,r.a,r.b))<roadWidth(r)/2+radius))return 'This position overlaps a road.';
    return '';
  }
  function roadError(a,b,type,bridge=false,tunnel=false,minimumLength=10,checkEndpoints=true) {
    const bounds=BOUNDS;if([a,b].some(p=>p.x<bounds.minX||p.x>bounds.maxX||p.z<bounds.minZ||p.z>bounds.maxZ))return 'That part of the road is outside the Boston map.';
    if(roadBlocked({a,b,type,bridge,tunnel}))return 'Route around the active incident area.';
    if(checkEndpoints&&(!land(a)||!land(b)))return 'Both road ends must be on dry land.';
    let crossesWater=false;
    if(dist(a,b)<minimumLength)return 'Draw a longer road.';
    for(let i=0,n=Math.ceil(dist(a,b)/3);i<=n;i++){
      const p={x:a.x+(b.x-a.x)*i/n,z:a.z+(b.z-a.z)*i/n};
      if(!land(p)){crossesWater=true;if(!bridge&&!tunnel)return 'Choose bridge or tunnel mode to cross water.';}
      if(!bridge&&!tunnel){const dx=(b.z-a.z)/dist(a,b)*widths[type]/2,dz=(a.x-b.x)/dist(a,b)*widths[type]/2;if(!land({x:p.x+dx,z:p.z+dz})||!land({x:p.x-dx,z:p.z-dz}))return 'Leave room for the full road width along the shore.';}
    }
    if(LAYOUT==='arcade'&&landmarks.some(l=>l.entranceDistance==null&&dist(l,projection(l,a,b))<l.radius+widths[type]/2&&(!tunnel||Math.min(dist(l,a),dist(l,b))<l.radius+50)))return 'Route the road around the protected landmark.';
    if(plan.buildings.some(p=>dist(p,projection(p,a,b))<(p.radius?p.radius-12:buildingScale(p.type)*4.2)+widths[type]/2&&(!tunnel||Math.min(dist(p,a),dist(p,b))<(p.radius||30)+50)))return 'This road crosses a building.';
    if(!tunnel&&cityCrossed(a,b,widths[type]))return 'This road crosses a Boston building. Bulldoze it first or route around it.';
    if(plan.roads.some(r=>!!r.bridge===bridge&&!!r.tunnel===tunnel&&dist(a,projection(a,r.a,r.b))<.5&&dist(b,projection(b,r.a,r.b))<.5))return 'A road already follows this section.';
    return '';
  }
  function snap(p,tolerance=12) {
    const nodes=servicePoints(),edges=[];
    for(const b of plan.buildings){
      if(b.area)nodes.push({x:b.x+Math.sin(b.rotation||0)*b.radius,z:b.z+Math.cos(b.rotation||0)*b.radius});
    }
    for(const road of plan.roads){
      if(!road.pathId||road.pathStart===0)nodes.push(road.a);
      if(!road.pathId||Math.abs(road.pathEnd-road.pathLength)<.01)nodes.push(road.b);
      const q=projection(p,road.a,road.b);
      if(Math.abs(heightAt(q,road))<.75)edges.push(q);
    }
    const closest=list=>list.filter(q=>dist(p,q)<=tolerance).sort((a,b)=>dist(p,a)-dist(p,b))[0];
    const chosen=closest(nodes)||closest(edges)||p;
    return {x:chosen.x,z:chosen.z};
  }
  function draftPoint(p,start,enabled=true,tolerance=12) {
    if(!enabled)return {x:p.x,z:p.z};
    const anchor=snap(p,tolerance);
    if(dist(anchor,p)>.001||!start)return anchor;
    const angle=Math.round(Math.atan2(p.z-start.z,p.x-start.x)/(Math.PI/12))*Math.PI/12;
    const length=dist(start,p);
    return {x:start.x+Math.cos(angle)*length,z:start.z+Math.sin(angle)*length};
  }
  function curve(a,bend,b) {
    const count=Math.max(6,Math.min(100,Math.ceil((dist(a,bend)+dist(bend,b))/12)));
    return Array.from({length:count+1},(_,i)=>{
      const t=i/count,u=1-t;
      return {x:u*u*a.x+2*u*t*bend.x+t*t*b.x,z:u*u*a.z+2*u*t*bend.z+t*t*b.z};
    });
  }
  function pathError(points,type,bridge=false,tunnel=false) {
    if(!land(points[0])||!land(points.at(-1)))return 'Both road ends must be on dry land.';
    const length=points.slice(1).reduce((sum,p,i)=>sum+dist(points[i],p),0);
    if(length<10)return 'Draw a road at least 10 meters long.';
    for(let i=1;i<points.length;i++){
      if(dist(points[i-1],points[i])<.01)continue;
      const error=roadError(points[i-1],points[i],type,bridge,tunnel,.01,false);
      if(error)return error;
    }
    return '';
  }
  function roadPath(points,type,bridge=false,tunnel=false) {
    const error=pathError(points,type,bridge,tunnel);
    if(error)return error;
    const pathId=Date.now()+Math.random();
    const pathLength=points.slice(1).reduce((sum,p,i)=>sum+dist(points[i],p),0);
    let offset=0;
    for(let i=1;i<points.length;i++){
      const length=dist(points[i-1],points[i]);if(length<.01)continue;
      plan.roads.push({id:Date.now()+Math.random(),pathId,pathStart:offset,pathEnd:offset+length,pathLength,a:{...points[i-1]},b:{...points[i]},type,bridge,tunnel});
      offset+=length;
    }
    subdividePlayerRoads();changed();return '';
  }
  function subdividePlayerRoads(){
    let split=false;
    plan.roads=plan.roads.flatMap(road=>{
      const length=dist(road.a,road.b);
      if(road.fixed||road.real||length<=20)return [road];
      split=true;
      const count=Math.ceil(length/20),pathId=road.pathId||'road-'+road.id;
      return Array.from({length:count},(_,i)=>{
        const at=t=>({x:road.a.x+(road.b.x-road.a.x)*t,z:road.a.z+(road.b.z-road.a.z)*t});
        return {...road,id:road.id+'-'+i,pathId,pathStart:(road.pathStart||0)+length*i/count,pathEnd:(road.pathStart||0)+length*(i+1)/count,pathLength:road.pathLength||length,a:at(i/count),b:at((i+1)/count)};
      });
    });
    if(split)changed();
  }
  function nearestRoad(p,tolerance=6) {
    return plan.roads.filter(r=>dist(p,projection(p,r.a,r.b))<=roadWidth(r)/2+tolerance).sort((a,b)=>dist(p,projection(p,a.a,a.b))-dist(p,projection(p,b.a,b.b)))[0]||null;
  }
  function upgrade(p,type,bridge=false,tunnel=false,reverse=false) {
    const selected=nearestRoad(p);
    if(!selected)return 'Choose an existing road.';
    if(selected.fixed)return 'The entry highway stays fixed. Upgrade your local roads.';
    if(reverse&&selected.type!=='oneway')return 'Choose a one-way road to reverse.';
    const group=plan.roads.filter(r=>selected.pathId?r.pathId===selected.pathId:r===selected);
    const previous=plan.roads;
    plan.roads=previous.filter(r=>!group.includes(r));
    const updated=group.map(r=>{
      const next={...r,type:reverse?r.type:type,bridge:reverse?!!r.bridge:bridge,tunnel:reverse?!!r.tunnel:tunnel};
      if(!reverse&&!r.fixed)next.oneway=type==='oneway'; // a real one-way upgraded to two-way must lose its one-way flag
      if(reverse){
        if(r.type!=='oneway')return next;
        next.a=r.b;next.b=r.a;
        if(r.pathId){next.pathStart=r.pathLength-r.pathEnd;next.pathEnd=r.pathLength-r.pathStart;}
      }
      return next;
    });
    for(const r of updated){
      if(r.real)continue; // real streets already exist in Boston; only the new type is applied
      const error=roadError(r.a,r.b,r.type,!!r.bridge,!!r.tunnel,.01,!r.pathId);
      if(error){plan.roads=previous;return error;}
    }
    plan.roads=previous.map(r=>group.includes(r)?updated[group.indexOf(r)]:r);
    changed();pruneControls();return '';
  }
  function roadBlocked(road) {
    return closures.some(incident=>{
      const nearest=projection(incident,road.a,road.b),height=heightAt(nearest,road);
      if(protectedRegion&&dist(nearest,protectedRegion)<protectedRegion.radius)return false;
      if(incident.kind==='protest'&&Math.abs(height)>1)return false;
      if(incident.kind==='flood'&&Math.abs(height)>3)return false;
      if(['storm','fire'].includes(incident.kind)&&height<-.75)return false;
      if(incident.kind==='traffic'&&Math.abs(height)>1)return false;
      return dist(incident,nearest)<incident.radius+roadWidth(road)/2;
    });
  }
  function setClosures(incidents,safeRegion=null) {
    const next=incidents.filter(i=>i.status==='active').map(i=>({id:i.id,kind:i.kind,x:i.x,z:i.z,radius:i.radius}));
    const signature=JSON.stringify([next,safeRegion]);
    if(signature===closureSignature)return false;
    closures=next;protectedRegion=safeRegion;closureSignature=signature;changed();return true;
  }
  function highwaySeed(){
    const data=window.BOSTON_HIGHWAY_DATA;
    if(!data)throw Error('Boston highway geometry has not loaded.');
    plan.roads=plan.roads.filter(r=>!r.fixed);
    const add=(id,name,points,width)=>{
      const projected=points.map(([lon,lat,height])=>({...point([lon,lat]),height}));
      const total=projected.slice(1).reduce((sum,p,i)=>sum+dist(projected[i],p),0);
      let offset=0;
      for(let i=1;i<projected.length;i++){
        const a=projected[i-1],b=projected[i],length=dist(a,b);if(length<1e-6)continue;
        plan.roads.push({id:id+'-'+i,pathId:id,pathStart:offset,pathEnd:offset+length,pathLength:total,
          a,b,type:width>6?'highway':'oneway',width,oneway:true,fixed:true,name,
          tunnel:Math.min(a.height,b.height)<-.75,bridge:Math.max(a.height,b.height)>.75});
        offset+=length;
      }
    };
    add('i93-north','I-93 North · O’Neill Tunnel',data.mainline,7.5);
    add('i93-south','I-93 South · O’Neill Tunnel',data.southbound,7.5);
    for(const ramp of data.ramps)add(ramp.id,ramp.name,ramp.points,5);
  }
  function highwayRamps(){
    return BOSTON_HIGHWAY_DATA.ramps.map(r=>({id:r.id,name:r.name,direction:r.direction,flow:r.flow,...point(r.surfaceEndpoint),height:0}));
  }
  function servicePoints(){
    return landmarks.filter(l=>['hall','hospital'].includes(l.site)).map(l=>{const reach=l.entranceDistance??l.radius+10,r=l.rotation||0;return {name:l.site==='hall'?'City Hall · emergency crews':'Mass General · EMS',x:l.x+Math.sin(r)*reach,z:l.z+Math.cos(r)*reach};});
  }
  function highwayGates(){
    const bounds=BOUNDS,result=[];
    for(const road of plan.roads.filter(r=>['i93-north','i93-south'].includes(r.pathId))){
      const a=road.a,b=road.b,dx=b.x-a.x,dz=b.z-a.z;
      const candidates=[];
      if(Math.abs(dx)>.001)for(const x of [bounds.minX,bounds.maxX])candidates.push((x-a.x)/dx);
      if(Math.abs(dz)>.001)for(const z of [bounds.minZ,bounds.maxZ])candidates.push((z-a.z)/dz);
      for(const t of candidates){
        if(t<0||t>1)continue;
        const point={x:a.x+dx*t,z:a.z+dz*t};
        if(point.x<bounds.minX-.01||point.x>bounds.maxX+.01||point.z<bounds.minZ-.01||point.z>bounds.maxZ+.01)continue;
        if(result.some(p=>p.route===road.pathId&&dist(p,point)<1))continue;
        result.push({...point,height:heightAt(point,road),route:road.pathId,name:(road.pathId==='i93-north'?'I-93 North':'I-93 South')+' · map boundary'});
      }
    }
    return result;
  }
  function responsePoints(center) {
    return plan.roads.filter(r=>!roadBlocked(r)&&!r.tunnel).map(r=>{
      const p=projection(center,r.a,r.b);return {...p,height:heightAt(p,r)};
    }).filter(p=>Math.abs(p.height)<.75).sort((a,b)=>dist(center,a)-dist(center,b)).slice(0,40);
  }
  function heightAt(p,r) {
    const q=projection(p,r.a,r.b);
    // Fixed GIS segments already carry their shared portal/deck elevations.
    // Reusing the player-road ramp profile here creates jumps at segment joins.
    if(r.fixed&&Number.isFinite(r.a.height)&&Number.isFinite(r.b.height))return r.a.height+(r.b.height-r.a.height)*q.t;
    const along=(r.pathStart||0)+dist(r.a,q),length=r.pathLength||dist(r.a,r.b);
    const rise=Math.min(12,along/3,(length-along)/3);return r.tunnel?-rise:r.bridge?rise:0;
  }
  function buildGraph() {
    const cuts=plan.roads.map(()=>[0,1]);
    // Split every crossing, including T junctions, before adding directed edges.
    // Only segments sharing a grid cell can touch, so test those pairs instead of all pairs.
    const cellIndex=new Map(),tested=new Set(),count=plan.roads.length,candidatePairs=[];
    plan.roads.forEach((r,i)=>cellsFor(Math.min(r.a.x,r.b.x)-.1,Math.max(r.a.x,r.b.x)+.1,Math.min(r.a.z,r.b.z)-.1,Math.max(r.a.z,r.b.z)+.1,k=>{if(!cellIndex.has(k))cellIndex.set(k,[]);cellIndex.get(k).push(i);}));
    for(const list of cellIndex.values())for(let x=0;x<list.length;x++)for(let y=x+1;y<list.length;y++){const i=Math.min(list[x],list[y]),j=Math.max(list[x],list[y]),key=i*count+j;if(!tested.has(key)){tested.add(key);candidatePairs.push([i,j]);}}
    for(const [i,j] of candidatePairs){
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
      if(roadBlocked(r))return;
      const ts=[...new Set(cuts[i])].sort((a,b)=>a-b);
      for(let j=1;j<ts.length;j++){
        const at=t=>{const p={x:r.a.x+(r.b.x-r.a.x)*t,z:r.a.z+(r.b.z-r.a.z)*t};return {...p,height:heightAt(p,r)};};
        const a=node(at(ts[j-1])),b=node(at(ts[j]));
        const weight=dist(a,b)/(r.type==='highway'?2:1);
        a.edges.push({to:b,weight});if(r.type!=='oneway'&&!r.oneway)b.edges.push({to:a,weight});
        edges.push({a,b,type:r.oneway?'oneway':r.type,weight,road:r});
      }
    });
    const edgeGrid=new Map();for(const e of edges)cellsFor(Math.min(e.a.x,e.b.x),Math.max(e.a.x,e.b.x),Math.min(e.a.z,e.b.z),Math.max(e.a.z,e.b.z),k=>{if(!edgeGrid.has(k))edgeGrid.set(k,[]);edgeGrid.get(k).push(e);});
    graph={nodes:[...nodes.values()],edges,edgeGrid,routes:new Map()};return graph;
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
    junctionCache=[...points.values()].filter(j=>j.arms.length>=2&&!(j.arms.length===2&&j.arms[0].road.pathId&&j.arms[0].road.pathId===j.arms[1].road.pathId));return junctionCache;
  }
  function incomingArm(arm) {
    if(arm.road.type!=='oneway'&&!arm.road.oneway)return true;
    const road=arm.road,length=dist(road.a,road.b);
    return ((road.b.x-road.a.x)*arm.x+(road.b.z-road.a.z)*arm.z)/length<-.9;
  }
  // Junctions with incident closures ignored, so a temporary closure never deletes real signals.
  function openJunctions(){if(!closures.length)return junctions();const saved=closures;closures=[];graph=null;junctionCache=null;const js=junctions();closures=saved;graph=null;junctionCache=null;return js;}
  function pruneControls(){
    const live=openJunctions();
    plan.controls=plan.controls.filter(control=>live.some(j=>dist(control,j)<.1&&(!control.approach||j.arms.some(arm=>incomingArm(arm)&&arm.x*control.approach.x+arm.z*control.approach.z>.95))));
  }
  function controlPlacement(p,kind) {
    const junction=junctions().filter(j=>dist(p,j)<(kind==='signal'?28:65)).sort((a,b)=>dist(p,a)-dist(p,b))[0];
    if(!junction)return null;
    if(kind==='signal')return {x:junction.x,z:junction.z,approach:null};
    const arm=junction.arms.filter(incomingArm).map(arm=>{
      const along=(p.x-junction.x)*arm.x+(p.z-junction.z)*arm.z;
      const side=Math.abs((p.x-junction.x)*arm.z-(p.z-junction.z)*arm.x);
      return {arm,along,side};
    }).filter(v=>v.along>3&&v.side<roadWidth(v.arm.road)/2+8).sort((a,b)=>a.side-b.side)[0]?.arm;
    return arm?{x:junction.x,z:junction.z,approach:{x:arm.x,z:arm.z}}:null;
  }
  function roadSurfaces(margin=0) {
    const shapes=[];
    for(const road of plan.roads.filter(r=>!r.bridge&&!r.tunnel&&(!r.real||!realOriginal(r)))){
      const length=dist(road.a,road.b),nx=-(road.b.z-road.a.z)/length,nz=(road.b.x-road.a.x)/length,radius=roadWidth(road)/2+margin;
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
    const reach=building.entranceDistance??(building.radius||scale*2.5);
    const entrance={x:building.x+facing.x*reach,z:building.z+facing.z*reach};
    const options=roadsNear(entrance,20*geo.scale+8).filter(road=>!roadBlocked(road)).map(road=>{
      const p=projection(entrance,road.a,road.b),length=dist(entrance,p);
      const forward=(p.x-entrance.x)*facing.x+(p.z-entrance.z)*facing.z;
      return {road,p,entrance,length,forward};
    }).sort((a,b)=>a.length-b.length);
    return options.find(option=>{
      if(option.length-roadWidth(option.road)/2>20*geo.scale||option.forward<.5*option.length)return false;
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
      let nearby=[];for(const radius of [30,110]){const found=new Set();cellsFor(target.x-radius,target.x+radius,target.z-radius,target.z+radius,k=>{for(const e of g.edgeGrid.get(k)||[])found.add(e);});nearby=[...found];if(nearby.length&&Math.min(...nearby.map(e=>dist(target,projection(target,e.a,e.b))))<=radius)break;}
      if(!nearby.length)nearby=g.edges;
      const edge=nearby.map(e=>({...e,p:projection(target,e.a,e.b)})).sort((x,y)=>(dist(target,x.p)+Math.abs((target.height||0)-heightAt(x.p,x.road))*2)-(dist(target,y.p)+Math.abs((target.height||0)-heightAt(y.p,y.road))*2))[0];
      return {...edge,entrance:connection?.entrance};
    };
    const cacheKey=[a.x,a.z,a.height||0,b.x,b.z,b.height||0].map(v=>(+v).toFixed(2)).join(',');
    if(g.routes.has(cacheKey)){const cached=g.routes.get(cacheKey);return cached&&cached.map(q=>({...q}));}
    const result=routeUncached(g,a,b,attach);g.routes.set(cacheKey,result);return result&&result.map(q=>({...q}));
  }
  function routeUncached(g,a,b,attach) {
    const start=attach(a),end=attach(b);
    if(!start||!end)return null;
    if(dist(a,start.p)>100||dist(b,end.p)>100)return null;
    // Dijkstra with a binary heap (same result as before, much faster on the real street network).
    const values=new Map(),previous=new Map(),heap=[];
    const push=(c,n)=>{heap.push([c,n]);let i=heap.length-1;while(i>0){const parent=(i-1)>>1;if(heap[parent][0]<=heap[i][0])break;[heap[parent],heap[i]]=[heap[i],heap[parent]];i=parent;}};
    const pop=()=>{const top=heap[0],last=heap.pop();if(heap.length){heap[0]=last;let i=0;for(;;){const l=2*i+1,r=l+1;let m=i;if(l<heap.length&&heap[l][0]<heap[m][0])m=l;if(r<heap.length&&heap[r][0]<heap[m][0])m=r;if(m===i)break;[heap[m],heap[i]]=[heap[i],heap[m]];i=m;}}return top;};
    const seed=(n,c)=>{if(c<(values.get(n)??Infinity)){values.set(n,c);push(c,n);}};
    seed(start.b,dist(start.p,start.b));if(start.type!=='oneway')seed(start.a,dist(start.p,start.a));
    while(heap.length){
      const [c,n]=pop();if(c>values.get(n))continue;
      for(const e of n.edges)if(c+e.weight<(values.get(e.to)??Infinity)){
        values.set(e.to,c+e.weight);previous.set(e.to,n);push(c+e.weight,e.to);
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
      const a=best[i-1],b=best[i],road=roadsNear(a,1).find(r=>dist(a,projection(a,r.a,r.b))<.05&&dist(b,projection(b,r.a,r.b))<.05);
      const count=road&&(road.bridge||road.tunnel)?Math.max(1,Math.ceil(dist(a,b)/8)):1;
      for(let j=1;j<=count;j++){const t=j/count,p={x:a.x+(b.x-a.x)*t,z:a.z+(b.z-a.z)*t};graded.push({...p,height:road?heightAt(p,road):b.height||0});}
    }
    return graded;
  }
  return {plan,polygons,holes,bounds:geo.bounds,scale:geo.scale,buildingScale,access,landmarks,widths,roadWidth,land,dist,projection,buildingError,roadError,snap,draftPoint,curve,pathError,roadPath,subdividePlayerRoads,nearestRoad,upgrade,route,junctions,controlTypes,controlPlacement,roadSurfaces,signalState,waitAt,pruneControls,roadBlocked,setClosures,highwayRamps,highwayGates,servicePoints,responsePoints,
    heightAt,
    elevationAt(p){for(const r of plan.roads)if((r.bridge||r.tunnel)&&dist(p,projection(p,r.a,r.b))<roadWidth(r))return this.heightAt(p,r);for(const b of plan.buildings){const c=access(b);if(c?.road.bridge){const q=projection(p,c.entrance,c.p);if(dist(p,q)<3)return this.heightAt(c.p,c.road)*q.t;}}return 0;},
    seedArcade(next=1){
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
      const playerBuildings=plan.buildings.filter(b=>!b.area);
      plan.buildings=areas.filter(a=>{const p=point([a[3],a[4]]);return p.x-20>BOUNDS.minX&&p.x+20<BOUNDS.maxX&&p.z-20>BOUNDS.minZ&&p.z+20<BOUNDS.maxZ;}).map(([id,label,type,lon,lat,rotation])=>({id,label,type,...point([lon,lat]),rotation,radius:14,area:true}));
      // Grid over real ground streets so the anchor search stays fast.
      const streetGrid=new Map();for(const r of realStreetRoads){if(r.bridge||r.tunnel)continue;cellsFor(Math.min(r.a.x,r.b.x),Math.max(r.a.x,r.b.x),Math.min(r.a.z,r.b.z),Math.max(r.a.z,r.b.z),k=>{if(!streetGrid.has(k))streetGrid.set(k,[]);streetGrid.get(k).push(r);});}
      const nearestStreet=(p,limit)=>{let best=null;cellsFor(p.x-limit,p.x+limit,p.z-limit,p.z+limit,k=>{for(const r of streetGrid.get(k)||[]){const q=projection(p,r.a,r.b),d=dist(p,q);if(d<limit&&(!best||d<best.d))best={r,q,d};}});return best;};
      if(LAYOUT==='real'){
        // Real layout: each neighbourhood is anchored to a real Boston building of the right kind
        // near its old spot, with its door facing the nearest real street. No pads, nothing cleared.
        hubCleared=new Set();hubVersion++;
        const used=new Set();
        for(const hub of plan.buildings.filter(b=>b.area)){
          const kinds=hub.type==='residential'?['res']:hub.type==='office'?['office']:['shop','office'];
          let pick=null;
          for(const c of city){
            if(!kinds.includes(c.k)||c.locked||used.has(c.id)||dist(c,hub)>400)continue;
            const street=nearestStreet(c,40);if(!street||street.d<.5)continue;
            const u={x:(street.q.x-c.x)/street.d,z:(street.q.z-c.z)/street.d},cos=Math.cos(c.r),sin=Math.sin(c.r);
            const half=Math.abs(u.x*cos+u.z*sin)*c.w/2+Math.abs(-u.x*sin+u.z*cos)*c.d/2;
            const gap=street.d-half-roadWidth(street.r)/2;if(gap<.5||gap>12)continue;
            const score=dist(c,hub);if(!pick||score<pick.score)pick={c,u,half,score};
          }
          if(!pick)continue;
          used.add(pick.c.id);
          Object.assign(hub,{x:pick.c.x,z:pick.c.z,rotation:Math.atan2(pick.u.x,pick.u.z),radius:pick.half+.5,anchor:true,cityId:pick.c.id});
        }
      }else{
      // Snap each neighbourhood hub to face its nearest real ground street (old arcade spots were not on streets).
        for(const hub of plan.buildings.filter(b=>b.area)){
          let best=null;for(const r of realStreetRoads){if(r.bridge||r.tunnel)continue;const q=projection(hub,r.a,r.b),d=dist(hub,q);if(d<150&&(!best||d<best.d))best={r,q,d};}
          if(!best)continue;
          const length=dist(best.r.a,best.r.b),normal={x:-(best.r.b.z-best.r.a.z)/length,z:(best.r.b.x-best.r.a.x)/length};
          const away=best.d>.5?{x:(hub.x-best.q.x)/best.d,z:(hub.z-best.q.z)/best.d}:normal;
          for(const dir of [away,{x:-away.x,z:-away.z}]){
            const offset=hub.radius+roadWidth(best.r)/2+6,center={x:best.q.x+dir.x*offset,z:best.q.z+dir.z*offset};
            if(!land(center)||cityNear(center,hub.radius).some(c=>c.locked&&inCityRect(c,center,hub.radius)))continue;
            hub.x=center.x;hub.z=center.z;hub.rotation=Math.atan2(-dir.x,-dir.z);break;
          }
        }
        // Each neighbourhood is a small connection hub; clear the unlocked buildings under the hub and its entrance.
        hubVersion++;hubCleared=new Set(city.filter(c=>!c.locked&&plan.buildings.some(a=>a.area&&(inCityRect(c,a,a.radius)||inCityRect(c,{x:a.x+Math.sin(a.rotation)*a.radius*1.6,z:a.z+Math.cos(a.rotation)*a.radius*1.6},6)))).map(c=>c.id));
      }
      // City Hall and Mass General dispatch points face their nearest real street (both layouts).
      for(const l of landmarks.filter(l=>['hall','hospital'].includes(l.site))){
        const street=nearestStreet(l,200);if(!street)continue;
        const u={x:(street.q.x-l.x)/street.d,z:(street.q.z-l.z)/street.d};
        l.rotation=Math.atan2(u.x,u.z);l.entranceDistance=Math.max(0,street.d-roadWidth(street.r)/2-4);
      }
      plan.buildings.push(...playerBuildings);
      if(!plan.roads.some(r=>r.fixed&&String(r.pathId).startsWith('i93-')))highwaySeed();
      if(!plan.roads.some(r=>r.real))setRealStreets();
      changed();
      if(!plan.controls.some(c=>c.real))setRealSignals();
    },
    get activeBounds(){return BOUNDS;},
    city,cityAt,cityNear,inCityRect,roadsNear,closestRoad,junctionDistance,
    realStreetCount:realPathIds.length,setRealSignals,streetOriginal:realOriginal,realStreetRoads,setRealStreets,removedRealStreets,modifiedRealStreets,
    // Compact plan snapshots: real streets are stored as removals/edits, not as thousands of roads.
    snapshot(){return JSON.stringify({buildings:plan.buildings,roads:plan.roads.filter(r=>!r.real),controls:plan.controls,removedCity:plan.removedCity,streets:plan.roads.some(r=>r.real)||!realPathIds.length,removedStreets:removedRealStreets(),modifiedStreets:modifiedRealStreets()});},
    restore(text){const saved=typeof text==='string'?JSON.parse(text):text;plan.buildings=saved.buildings||[];plan.controls=saved.controls||[];plan.removedCity=saved.removedCity||[];plan.roads=(saved.roads||[]).filter(r=>!r.real);if(saved.streets!==false)setRealStreets(saved.removedStreets||[],saved.modifiedStreets||[]);changed();},
    get removedCity(){return removed();},
    cityPopulation(){const gone=new Set(plan.removedCity);return city.reduce((n,b)=>n+(b.k==='res'&&!gone.has(b.id)?b.p||0:0),0);},
    get revision(){return revision;},changed,
    district:p=>NEIGHBOURHOODS.reduce((best,n)=>dist(p,n)<dist(p,best)?n:best).name,
    get layout(){return LAYOUT;},
    neighbourhoods:NEIGHBOURHOODS.map(n=>n.name),
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
    remove(p){const control=plan.controls.find(c=>dist(p,{x:c.x+(c.approach?.x||0)*20,z:c.z+(c.approach?.z||0)*20})<9);if(control){plan.controls.splice(plan.controls.indexOf(control),1);changed();return '';}const b=plan.buildings.find(b=>dist(b,p)<(b.radius||buildingScale(b.type)*4.2));if(b?.area)return 'This district is fixed. Connect its gold access point with roads.';const cb=b?null:cityAt(p);const anchorOf=cb&&plan.buildings.find(a=>a.anchor&&a.cityId===cb.id);if(anchorOf)return 'This building anchors the '+anchorOf.label+' residents and workers in the simulation.';if(cb?.locked==='permanent')return (cb.n||'This building')+' is a permanently protected historical landmark.';if(cb?.locked==='author')return (cb.n||'This service building')+' has an author-set lock. Only the scenario author can lift it.';if(b)plan.buildings.splice(plan.buildings.indexOf(b),1);else if(cb){plan.removedCity=[...plan.removedCity,cb.id];}else{const near=plan.roads.filter(r=>dist(p,projection(p,r.a,r.b))<roadWidth(r)/2+1).sort((x,y)=>(dist(p,projection(p,x.a,x.b))+(Math.abs(heightAt(projection(p,x.a,x.b),x))>.75?50:0))-(dist(p,projection(p,y.a,y.b))+(Math.abs(heightAt(projection(p,y.a,y.b),y))>.75?50:0)));const r=near.find(r=>!r.fixed)||near[0];if(!r)return 'Select a building or road to remove.';if(r.fixed)return 'The through highway is the fixed entry route. Connect local roads to it.';plan.roads=plan.roads.filter(road=>r.pathId?road.pathId!==r.pathId:road!==r);}changed();const live=openJunctions();plan.controls=plan.controls.filter(c=>live.some(j=>dist(c,j)<.1));return '';},
    load(saved){if(saved?.version!==2)return;if(Array.isArray(saved.removedCity)){const known=new Set(city.filter(b=>!b.locked).map(b=>b.id));plan.removedCity=saved.removedCity.filter(id=>known.has(id));}for(const b of saved.buildings||[])if(['residential','office','shop','social','park','parking'].includes(b.type)&&Number.isFinite(b.rotation)&&!buildingError(b))plan.buildings.push(b);for(const r of saved.roads||[])if(roadWidth(r)&&r.a&&r.b&&!roadError(r.a,r.b,r.type,!!r.bridge,!!r.tunnel,.01,!r.pathId))plan.roads.push(r);changed();}
  };
})();
window.CITY_LOTS=[];
window.CITY_HALL={...CityPlan.landmarks[0],radius:165};
window.CITY_HOSPITAL=CityPlan.landmarks[2];
window.CITY_DISTRICTS=CityPlan.neighbourhoods;
window.CITY_PATH=(x,z,tx,tz)=>CityPlan.route({x,z},{x:tx,z:tz});
