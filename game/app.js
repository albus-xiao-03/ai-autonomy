(() => {
  const $ = id => document.getElementById(id);
  const stock = {residential:6, office:4, shop:3, social:3, park:4, parking:3};
  const labels = {residential:'Residences', office:'Offices', shop:'Shops', social:'Social venues', park:'Parks', parking:'Parking'};
  const lots = {};
  let selection=null,sim=null,paused=false,speed=1,lastEntry=null,settings='qwen',rotation=0,roadStart=null,curveControl=null,hoverPoint=null;
  const undo=[];
  const time=value=>String(Math.floor(value/60)).padStart(2,'0')+':'+String(Math.floor(value%60)).padStart(2,'0');
  const left=type=>stock[type]-CityPlan.plan.buildings.filter(b=>!b.area&&b.type===type).length;
  const notice=message=>{$('notice').textContent=message;};
  let legacySave=null,legacyImported=false,importUndoDepth=-1;
  // Saved items that do not fit the current map (another layout, a restored street or building on top
  // of them) are kept aside in the save and retried on every load instead of being deleted.
  let dormant={roads:[],buildings:[],controls:[]};
  const SAVE_KEY=CityPlan.layout==='arcade'?'borough-boston-v1-arcade':'borough-boston-v1';
  const anchorIds=()=>new Set(CityPlan.plan.buildings.filter(b=>b.anchor).map(b=>b.cityId));
  // Adds saved player roads, buildings and junction controls that fit the current map.
  function loadPlayerPlan(saved){
    const kept={roads:[],buildings:[],controls:[]};
    for(const r of [...(saved?.roads||[]),...(saved?.dormant?.roads||[])]){
      if(r.fixed||r.real||!CityPlan.widths[r.type]||!r.a||!r.b)continue;
      if(CityPlan.plan.roads.some(o=>o.id===r.id))continue;
      if(CityPlan.roadError(r.a,r.b,r.type,!!r.bridge,!!r.tunnel,.01,!r.pathId))kept.roads.push(r);else CityPlan.plan.roads.push(r);
    }
    CityPlan.changed();
    for(const b of [...(saved?.buildings||[]),...(saved?.dormant?.buildings||[])]){
      const valid=Object.hasOwn(stock,b.type)&&Number.isFinite(b.x)&&Number.isFinite(b.z)&&Number.isFinite(b.rotation)&&b.id!=null&&!CityPlan.plan.buildings.some(existing=>existing.id===b.id);
      if(!valid)continue;
      if(left(b.type)>0&&!CityPlan.buildingError(b))CityPlan.plan.buildings.push({...b,area:false});else kept.buildings.push(b);
    }
    CityPlan.changed();
    for(const c of [...(saved?.controls||[]),...(saved?.dormant?.controls||[])]){
      if(!CityPlan.controlTypes[c.kind]||(c.approach&&!(Number.isFinite(c.approach.x)&&Number.isFinite(c.approach.z))))continue;
      if(CityPlan.plan.controls.some(o=>o.kind===c.kind&&CityPlan.dist(o,c)<.1&&(!c.approach||o.approach&&o.approach.x*c.approach.x+o.approach.z*c.approach.z>.95)))continue;
      if(CityPlan.junctions().some(j=>CityPlan.dist(c,j)<.1))CityPlan.plan.controls.push(c);else if(!c.real)kept.controls.push(c);
    }
    return kept;
  }
  // Opt-in import of a level-era save. Each old road or building is tried on its own: the unlocked Boston
  // buildings under it are bulldozed only if it then fits; otherwise it is skipped and nothing is cleared.
  function importLegacy(legacy){
    const anchors=anchorIds();let placed=0,skipped=0;
    const under=(p,r,ids)=>CityPlan.cityNear(p,r).forEach(b=>{if(!b.locked&&!anchors.has(b.id)&&CityPlan.inCityRect(b,p,r))ids.add(b.id);});
    const tryClear=(ids,fits)=>{const before=CityPlan.plan.removedCity;CityPlan.plan.removedCity=[...new Set([...before,...ids])];CityPlan.changed();if(fits())return true;CityPlan.plan.removedCity=before;CityPlan.changed();return false;};
    for(const r of legacy.roads||[]){
      if(r.fixed||!CityPlan.widths[r.type]||!r.a||!r.b)continue;
      const ids=new Set();if(!r.tunnel){const n=Math.ceil(CityPlan.dist(r.a,r.b)/4);for(let i=0;i<=n;i++)under({x:r.a.x+(r.b.x-r.a.x)*i/n,z:r.a.z+(r.b.z-r.a.z)*i/n},(CityPlan.widths[r.type]||8)/2,ids);}
      if(tryClear(ids,()=>!CityPlan.roadError(r.a,r.b,r.type,!!r.bridge,!!r.tunnel,.01,!r.pathId))){CityPlan.plan.roads.push(r);CityPlan.changed();placed++;}else skipped++;
    }
    for(const b of legacy.buildings||[]){
      if(!Object.hasOwn(stock,b.type)||!Number.isFinite(b.x)||!Number.isFinite(b.z)||!Number.isFinite(b.rotation)||b.id==null||CityPlan.plan.buildings.some(o=>o.id===b.id))continue;
      const ids=new Set();under(b,CityPlan.buildingScale(b.type)*4.2*.7,ids);
      if(left(b.type)>0&&tryClear(ids,()=>!CityPlan.buildingError(b))){CityPlan.plan.buildings.push({...b,area:false});CityPlan.changed();placed++;}else skipped++;
    }
    loadPlayerPlan({controls:legacy.controls||[]});CityPlan.subdividePlayerRoads();CityPlan.changed();CityPlan.pruneControls();
    return {placed,skipped};
  }
  try{
    // Current saves use borough-boston-v1. An older level-based save (borough-levels-v1) is NOT loaded
    // automatically: its roads were drawn on the old arcade map and would cut through real Boston.
    // The City tab offers "Import old level save" instead.
    const current=JSON.parse(localStorage.getItem(SAVE_KEY)||'null')||(SAVE_KEY!=='borough-boston-v1'?JSON.parse(localStorage.getItem('borough-boston-v1')||'null'):null);
    legacyImported=!!current?.legacyImported;
    legacySave=legacyImported?null:JSON.parse(localStorage.getItem('borough-levels-v1')||'null');
    CityPlan.seedArcade();
    if(current?.version>=2){if(current.streets===false)CityPlan.plan.roads=CityPlan.plan.roads.filter(r=>!r.real);else CityPlan.setRealStreets(current.removedStreets||[],current.modifiedStreets||[]);}
    if(Array.isArray(current?.removedCity)){const removable=new Set(CityPlan.city.filter(b=>!b.locked).map(b=>b.id));const anchors=anchorIds();CityPlan.plan.removedCity=current.removedCity.filter(id=>removable.has(id)&&!anchors.has(id));}
    // Version 3 saves store every junction control, including real signals the player kept or removed.
    if(current?.version>=3)CityPlan.plan.controls=[];
    dormant=loadPlayerPlan(current);
    const aside=dormant.roads.length+dormant.buildings.length;
    if(aside)setTimeout(()=>notice(aside+' saved road or building piece'+(aside===1?' does':'s do')+' not fit this map right now; '+(aside===1?'it is':'they are')+' kept in your save and will return when there is room.'),0);
    settings=localStorage.getItem('borough-mayor')||'local';if(settings==='qwen')settings='local';else if(!['local','baseline','api'].includes(settings))settings='baseline';$('mayorBrain').value=settings;$('autonomy').value=localStorage.getItem('borough-autonomy')??'30';$('autoIncidents').checked=localStorage.getItem('borough-auto-incidents')!=='false';
  }catch{CityPlan.seedArcade();}
  CityPlan.subdividePlayerRoads();CityPlan.changed();CityPlan.pruneControls();
  function save(){try{const snap=JSON.parse(CityPlan.snapshot());localStorage.setItem(SAVE_KEY,JSON.stringify({version:3,dormant,legacyImported,roads:snap.roads.filter(r=>!r.fixed),controls:snap.controls,buildings:snap.buildings.filter(b=>!b.area),removedCity:snap.removedCity,streets:snap.streets,removedStreets:snap.removedStreets,modifiedStreets:snap.modifiedStreets}));}catch{notice('Browser storage is unavailable. Keep this page open to preserve your plan.');}}
  const world=CityWorld.mount($('world'),{
    onPoint:place,
    getTool:()=>({pan:!selection,dragRoad:!!CityPlan.widths[selection]&&$('roadMode').value==='drag'&&$('roadShape').value==='straight'&&$('roadAction').value==='build'}),
    onRoadStart:p=>{if(!topDownOnly())return;roadStart=draftPoint(p);curveControl=null;},
    onRoadEnd:p=>{const placed=place(p);roadStart=curveControl=null;world.ghost(null);if(placed)notice('Road placed. Drag to draw another segment.');},
    onRoadCancel:()=>{roadStart=curveControl=null;world.ghost(null);$('buildHint').textContent='';notice('Road draft cancelled. Choose a new start point.');},
    onHover:hover
  });
  function draftPoint(p) {
    return CityPlan.draftPoint(p,$('roadShape').value==='straight'?roadStart:null,$('snapping').checked,world.snapTolerance());
  }
  function draftPath(p) {
    const end=draftPoint(p);
    return curveControl?CityPlan.curve(roadStart,curveControl,end):[roadStart,end];
  }
  function hover(p){
    hoverPoint=p;
    if(!selection)return;
    if(world.is3D&&!selection.startsWith('incident:')){world.ghost(null);return;}
    const roadTool=!!CityPlan.widths[selection];
    if(selection.startsWith('incident:')){world.incidentPreview(p,selection.split(':')[1]);return;}
    if(selection==='remove'||selection==='reverse'||(roadTool&&$('roadAction').value==='upgrade')){
      if(selection==='remove'){
        const building=CityPlan.plan.buildings.find(b=>!b.area&&CityPlan.dist(p,b)<CityPlan.buildingScale(b.type)*4.2);
        if(building){world.ghost(building,building.type,building.rotation);return;}
      }
      const road=CityPlan.nearestRoad(p,world.snapTolerance());
      if(!road){world.ghost(null);return;}
      const group=CityPlan.plan.roads.filter(r=>road.pathId?r.pathId===road.pathId:r===road).sort((a,b)=>(a.pathStart||0)-(b.pathStart||0));
      world.roadPreview([group[0].a,...group.map(r=>r.b)],road.type,!!road.bridge,!!road.tunnel,'',selection==='remove'?0xea765e:0x75b9df);
      return;
    }
    if(roadTool&&roadStart){
      const points=draftPath(p),bridge=$('elevation').value==='bridge',tunnel=$('elevation').value==='tunnel';
      const error=CityPlan.pathError(points,selection,bridge,tunnel);
      world.roadPreview(points,selection,bridge,tunnel,error);
      const length=points.slice(1).reduce((sum,point,i)=>sum+CityPlan.dist(points[i],point),0);
      $('buildHint').textContent=error||Math.round(length)+' m · '+($('roadShape').value==='curve'&&!curveControl?'Click to set bend':'Click to build');
      return;
    }
    if(Object.hasOwn(stock,selection)){
      world.ghost(p,selection,rotation);
      const error=CityPlan.buildingError({...p,type:selection});
      const candidate={...p,type:selection,rotation,id:'preview'};
      $('buildHint').textContent=error||(CityPlan.access(candidate)?'Road access available · click to place':'Click to place · connect the entrance to a road');
      return;
    }
    world.ghost(roadTool?draftPoint(p):p,selection,rotation);
    $('buildHint').textContent=roadTool?'Choose start point':CityPlan.controlTypes[selection]||'';
  }
  function networkEdited(){
    syncSites();sim?.refreshNetwork();
    save();drawPalette();render();
  }
  function syncSites(){CITY_LOTS.splice(0,CITY_LOTS.length,...CityPlan.plan.buildings.map(b=>({...b,district:CityPlan.district(b)})));for(const key of Object.keys(lots))delete lots[key];for(const b of CITY_LOTS)lots[b.id]=b.type;}
  function choose(type){selection=selection===type?null:type;if(selection&&!selection.startsWith('incident:')&&world.is3D){world.toggleView('top');syncViewButton();}roadStart=curveControl=null;world.ghost(null);$('buildHint').textContent='';drawPalette();render();notice(selection?.startsWith('incident:')?'Click unlocked land to trigger '+CityIncidents.types[selection.split(':')[1]].label.toLowerCase()+'.':CityPlan.controlTypes[selection]?(selection==='signal'?'Click a road junction to install traffic lights.':'Click the incoming street near a junction. The preview arrow shows which traffic must obey the sign.'):!selection?'Drag anywhere on the map to move. Wheel to zoom at the pointer.':CityPlan.widths[type]?($('roadAction').value==='upgrade'?'Click a player road to upgrade it.':$('roadMode').value==='drag'?'Drag from the road start to its end.':'Click the start and end of a road. Continue clicking to extend it. Escape ends the road.'):'Click open land to place a building. R rotates it.');}
  function drawPalette(){
    $('palette').replaceChildren();
    for(const type of Object.keys(stock)){
      const button=document.createElement('button');button.className='tile';button.disabled=left(type)<=0&&selection!==type;button.setAttribute('aria-pressed',selection===type);
      button.innerHTML='<img alt="" src="art/'+type+'.png"><span>'+labels[type]+'</span><b>×'+left(type)+'</b>';
      button.onclick=()=>choose(type);$('palette').append(button);
    }
    for(const button of document.querySelectorAll('[data-control]')){button.disabled=false;button.setAttribute('aria-pressed',selection===button.dataset.control);}
    for(const button of document.querySelectorAll('[data-road]')){button.disabled=false;button.setAttribute('aria-pressed',selection===button.dataset.road);}
    for(const button of document.querySelectorAll('[data-event]')){
      button.disabled=!sim||sim.getState().finished;button.setAttribute('aria-pressed',selection==='incident:'+button.dataset.event);
    }
    $('pan').setAttribute('aria-pressed',!selection);
    $('clearRoads').disabled=!CityPlan.plan.roads.some(r=>!r.fixed&&!r.real);
    $('remove').classList.toggle('active',selection==='remove');$('remove').disabled=false;$('undo').disabled=!undo.length;
    $('rotate').textContent='Rotate · '+Math.round(rotation*180/Math.PI)+'°';
  }
  function place(p){
    if(!selection)return;
    if(selection.startsWith('incident:')){
      if(!sim||sim.getState().finished){notice('Run the day before triggering an incident.');return;}
      const kind=selection.split(':')[1],error=sim.triggerIncident(kind,p);
      notice(error||(kind==='traffic'?'Traffic collision triggered. 911 is sending police and an ambulance; cars queue behind the crash until it is cleared.':CityIncidents.types[kind].label+' triggered. The mayor will review the response.'));render();return;
    }
    if(!topDownOnly())return;
    let error='';
    const snapshot=CityPlan.snapshot();
    if(selection==='remove')error=CityPlan.remove(p);
    else if(CityPlan.controlTypes[selection]){error=CityPlan.control(p,selection);if(!error)notice(CityPlan.controlTypes[selection]+' installed.');}
    else if(selection==='reverse'){error=CityPlan.upgrade(p,'oneway',false,false,true);if(!error)notice('One-way direction reversed.');}
    else if(CityPlan.widths[selection]){
      const bridge=$('elevation').value==='bridge',tunnel=$('elevation').value==='tunnel';
      if($('roadAction').value==='upgrade'){error=CityPlan.upgrade(p,selection,bridge,tunnel);if(!error)notice('Road upgraded. Traffic is being rerouted.');}
      else{
        p=draftPoint(p);
        if(!roadStart){if(!CityPlan.land(p)){notice('Start the road on dry land.');return;}roadStart=p;notice($('roadShape').value==='curve'?'Choose the curve bend.':'Choose the road end.');return;}
        if($('roadShape').value==='curve'&&!curveControl){curveControl={...p};notice('Choose the endpoint. The preview shows the full curve.');return;}
        error=CityPlan.roadPath(draftPath(p),selection,bridge,tunnel);
        if(!error){roadStart=p;curveControl=null;notice('Road built. Continue the road or right-click to cancel.');}
      }
    }else{
      if(!left(selection)){notice('All buildings of this type have been placed.');return;}
      error=CityPlan.place(p,selection,rotation);if(!error)notice(labels[selection]+' placed.');
    }
    if(error){notice(error);return;}
    undo.push(snapshot);world.ghost(null);$('buildHint').textContent='';networkEdited();return true;
  }
  document.querySelectorAll('[data-road]').forEach(button=>button.onclick=()=>choose(button.dataset.road));
  document.querySelectorAll('[data-event]').forEach(button=>button.onclick=()=>choose('incident:'+button.dataset.event));
  $('mayorBrain').onchange=()=>{settings=$('mayorBrain').value;try{localStorage.setItem('borough-mayor',settings);}catch{}notice('Mayor brain changes apply on the next run.');render();};
  $('autonomy').oninput=()=>{$('mixValue').textContent=$('autonomy').value+'%';try{localStorage.setItem('borough-autonomy',$('autonomy').value);}catch{}};
  let engineInfo=null;
  async function pollEngine(){
    try{const r=await fetch('http://127.0.0.1:8787/api/brain/status');engineInfo=await r.json();}catch{engineInfo=null;}
    // Show the models the engine is configured with (the teammate's engine owns model choice).
    const localOption=[...$('mayorBrain').options].find(o=>o.value==='local');if(localOption)localOption.textContent='Local mayor · '+(engineInfo?.mayor_local_model||'engine model');
    $('mixHelp').textContent='Routine ← → think for themselves ('+(engineInfo?.resident_model||'engine resident model')+')';
    if(!sim)render();
    $('engineStatus').textContent=engineInfo?'Engine online · Ollama '+(engineInfo.ollama?'ready':'offline')+(engineInfo.api_available?' · cloud API enabled':' · cloud API off'):'Engine offline · civic controller fallback';
  }
  pollEngine();setInterval(pollEngine,5000);
  let scoreHistory=[];
  function drawScore(s){
    const c=$('scoreGraph'),g=c.getContext('2d');
    if(s&&(!scoreHistory.length||scoreHistory.at(-1).minute!==s.minute))scoreHistory.push({minute:s.minute,score:s.satisfaction});
    if(scoreHistory.length>400)scoreHistory=scoreHistory.filter((_,i)=>i%2===0);
    g.clearRect(0,0,c.width,c.height);
    g.strokeStyle='#3b4b40';g.beginPath();g.moveTo(0,c.height/2);g.lineTo(c.width,c.height/2);g.stroke();
    if(scoreHistory.length<2)return;
    const t0=360,t1=1320;g.strokeStyle='#f4cf6a';g.lineWidth=2;g.beginPath();
    scoreHistory.forEach((p,i)=>{const x=(p.minute-t0)/(t1-t0)*c.width,y=c.height-2-(p.score/100)*(c.height-4);i?g.lineTo(x,y):g.moveTo(x,y);});
    g.stroke();
  }
  $('autoIncidents').onchange=()=>{sim?.setAutoIncidents($('autoIncidents').checked);try{localStorage.setItem('borough-auto-incidents',$('autoIncidents').checked);}catch{}};
  document.querySelectorAll('[data-control]').forEach(button=>button.onclick=()=>choose(button.dataset.control));
  $('undo').onclick=()=>{const depth=undo.length,snapshot=undo.pop();if(!snapshot)return;CityPlan.restore(snapshot);if(depth===importUndoDepth){legacyImported=false;importUndoDepth=-1;legacySave=JSON.parse(localStorage.getItem('borough-levels-v1')||'null');$('importLegacy').hidden=!legacySave;}roadStart=curveControl=null;world.ghost(null);networkEdited();notice('Last edit undone.');};
  $('clearRoads').onclick=()=>{
    undo.push(CityPlan.snapshot());CityPlan.plan.roads=CityPlan.plan.roads.filter(r=>r.fixed||r.real);CityPlan.changed();CityPlan.pruneControls();roadStart=curveControl=null;world.ghost(null);networkEdited();notice('Player roads cleared. Real Boston streets stay. Undo restores them.');
  };
  // Back to real Boston: removes player roads and junction controls and restores every real street.
  $('realStreets').onclick=()=>{
    if(!topDownOnly())return;
    undo.push(CityPlan.snapshot());CityPlan.plan.roads=CityPlan.plan.roads.filter(r=>r.fixed);CityPlan.plan.controls=[];CityPlan.setRealStreets();
    // A real street that would run through one of your buildings stays removed so the building keeps fitting.
    const players=CityPlan.plan.buildings.filter(b=>!b.area),blocked=new Set(CityPlan.plan.roads.filter(r=>r.real&&players.some(b=>{const q=CityPlan.projection(b,r.a,r.b);return Math.abs(CityPlan.heightAt(q,r))<3&&CityPlan.dist(b,q)<CityPlan.roadWidth(r)/2+CityPlan.buildingScale(b.type)*4.2;})).map(r=>r.pathId));
    if(blocked.size)CityPlan.setRealStreets([...blocked]);
    const signals=CityPlan.setRealSignals();roadStart=curveControl=null;world.ghost(null);networkEdited();notice('Real Boston streets restored ('+CityPlan.realStreetCount+' street pieces, '+signals+' real traffic signals and stop signs). Your own roads were removed. Undo brings them back.');
  };
  // Map layout switch (needs a reload because the land shapes are chosen before the planner loads).
  $('mapLayout').value=CityPlan.layout;
  $('mapLayout').onchange=()=>{save();try{localStorage.setItem('borough-layout',$('mapLayout').value);}catch{}location.reload();};
  $('restoreBuildings').onclick=()=>{
    if(!topDownOnly())return;
    undo.push(CityPlan.snapshot());
    // Buildings under your own roads or buildings stay bulldozed so your plan still fits.
    const was=new Set(CityPlan.plan.removedCity),keep=new Set(),hit=(p,r)=>CityPlan.cityNear(p,r).forEach(c=>{if(was.has(c.id)&&CityPlan.inCityRect(c,p,r))keep.add(c.id);});
    CityPlan.plan.removedCity=[];CityPlan.changed();
    for(const r of CityPlan.plan.roads)if(!r.fixed&&!r.real&&!r.tunnel){const n=Math.max(1,Math.ceil(CityPlan.dist(r.a,r.b)/4));for(let i=0;i<=n;i++)hit({x:r.a.x+(r.b.x-r.a.x)*i/n,z:r.a.z+(r.b.z-r.a.z)*i/n},CityPlan.roadWidth(r)/2);}
    for(const b of CityPlan.plan.buildings)if(!b.area)hit(b,CityPlan.buildingScale(b.type)*4.2*.7);
    CityPlan.plan.removedCity=[...keep];CityPlan.changed();networkEdited();
    notice((was.size-keep.size)+' bulldozed Boston buildings are back'+(keep.size?'; '+keep.size+' stay removed because your roads or buildings stand there':'')+'. Undo removes them again.');
  };
  $('importLegacy').hidden=!legacySave;
  $('importLegacy').onclick=()=>{
    if(!legacySave)return;
    undo.push(CityPlan.snapshot());importUndoDepth=undo.length;const result=importLegacy(legacySave);legacyImported=true;$('importLegacy').hidden=true;networkEdited();notice('Old level save imported: '+result.placed+' roads or buildings placed'+(result.skipped?', '+result.skipped+' skipped because they cross protected Boston buildings':'')+'. Undo reverses the import.');
  };
  function rotate(){rotation=(rotation+Math.PI/4)%(Math.PI*2);drawPalette();if(hoverPoint&&Object.hasOwn(stock,selection))hover(hoverPoint);}
  $('rotate').onclick=rotate;
  document.querySelectorAll('[role="tab"]').forEach(tab=>{
    tab.onclick=()=>{
      document.querySelectorAll('[role="tab"]').forEach(other=>{
        const selected=tab===other;other.setAttribute('aria-selected',selected);
        document.getElementById(other.getAttribute('aria-controls')).hidden=!selected;
      });
      choose(null);
    };
  });
  $('reverse').onclick=()=>{choose('reverse');notice('Click a one-way road to reverse its traffic direction.');};
  $('roadShape').onchange=()=>{roadStart=curveControl=null;world.ghost(null);$('roadMode').disabled=$('roadShape').value==='curve';if($('roadShape').value==='curve')$('roadMode').value='click';notice($('roadShape').value==='curve'?'Click start, bend, then end to build a curved road.':'Click or drag to build a straight road.');};
  $('roadAction').onchange=()=>{roadStart=curveControl=null;world.ghost(null);notice($('roadAction').value==='upgrade'?'Choose a road type and elevation, then click a player road to replace it.':'Choose a start point for the road.');};
  $('pan').onclick=()=>choose(null);
  $('roadMode').onchange=()=>{roadStart=curveControl=null;world.ghost(null);notice($('roadMode').value==='drag'?'Drag from one road endpoint to the other.':'Click each road endpoint. Escape switches to moving the map.');};
  $('elevation').onchange=()=>{
    roadStart=curveControl=null;world.ghost(null);
    const descriptions={ground:'Ground roads join at crossings.',bridge:'Draw a bridge or overpass between dry-land endpoints. Traffic passes above roads underneath.',tunnel:'Draw a tunnel between dry-land endpoints. Traffic enters at the portals and passes underground.'};
    notice(descriptions[$('elevation').value]);
  };
  document.addEventListener('keydown',e=>{if(e.target.matches('input,select,textarea'))return;if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();if(undo.length)$('undo').click();return;}if(e.key==='PageUp'||e.key==='PageDown'){e.preventDefault();const levels=['ground','bridge','tunnel'],current=levels.indexOf($('elevation').value);$('elevation').value=levels[(current+(e.key==='PageUp'?1:2))%3];$('elevation').onchange();}if(e.key===' '&&!e.repeat){e.preventDefault();$('run').click();}if(e.key==='Escape'){selection=null;roadStart=curveControl=null;world.ghost(null);$('buildHint').textContent='';drawPalette();render();notice('Move map selected. Drag to explore the city.');}if(e.key.toLowerCase()==='r')rotate();});
  function history(state) {
    const pane=$('historyPane');pane.replaceChildren();
    const back=document.createElement('button');back.className='secondary';back.textContent='Back to live';back.onclick=()=>pane.hidden=true;pane.append(back);
    const title=document.createElement('h2');title.textContent='Decision history';pane.append(title);
    const events=state?.events||[];
    if(!events.length){const p=document.createElement('p');p.textContent='The mayor’s decisions appear here when the day begins.';pane.append(p);}
    for(const e of [...events].reverse()){
      const item=document.createElement('div');item.className='entry';
      for(const [tag,txt] of [['small',[time(e.minute),e.status,e.source||'City report'].join(' · ')],['p',e.thought],['strong',e.action],['p',e.outcome]]){
        const el=document.createElement(tag);el.textContent=txt||'';item.append(el);
      }
      pane.append(item);
    }
  }
  function render() {
    const s=sim?.getState(), e=s?.events.at(-1);
    $('planningTools').hidden=false;
    $('cityLife').hidden=!s||s.finished;
    document.querySelectorAll('[data-event]').forEach(button=>button.disabled=!s||s.finished);
    $('levelTitle').textContent='Boston · 1:1 scale';

    const homes=CityPlan.plan.buildings.filter(b=>b.type==='residential');

    const allConnected=CityPlan.plan.buildings.every(b=>CityPlan.access(b));
    const complete=!!s?.finished&&s.workersArrived===s.population&&s.atHome===s.population&&allConnected&&!(s.incidents||[]).some(i=>i.status!=='resolved');
        $('levelGoal').textContent=complete?'Day objective complete: every resident commuted home and every incident is closed.':'Connect homes and offices. Keep residents safe and restore roads after incidents.';
    $('engine').textContent=s?.mayorMode || ({local:'Local mayor · '+(engineInfo?.mayor_local_model||'engine model'),baseline:'Rule-based mayor',api:'Claude API mayor'}[settings]);
    $('mixValue').textContent=$('autonomy').value+'%';$('autonomy').disabled=!!s&&!s.finished;$('mayorBrain').disabled=!!s&&!s.finished;
    $('crimes').textContent=s?s.crimes:0;drawScore(s);
    if(s?.residentThoughts?.length){$('residentThoughts').replaceChildren(...s.residentThoughts.slice(-5).reverse().map(t=>{const row=document.createElement('div');row.className='thoughtRow'+(['speeding','vandalism','road_blockade'].includes(t.action)?' crime':'');const b=document.createElement('b');b.textContent='#'+t.id+' · '+t.action.replace('_',' ')+' · '+time(t.minute);const p=document.createElement('div');p.textContent='“'+t.thought+'”';row.append(b,p);return row;}));}
    else if(s)$('residentThoughts').replaceChildren(Object.assign(document.createElement('small'),{textContent:s.autonomousCount?s.autonomousCount+' autonomous residents · first thoughts arrive within the hour':'All residents follow routines (slider at 0%).'}));
    if(s) {
      const rows=(items)=>items.map(([key,value])=>{const row=document.createElement('div');row.className='statrow';const name=document.createElement('span');name.textContent=key;const val=document.createElement('b');val.textContent=value;row.append(name,val);return row;});
      $('routines').replaceChildren(...rows([['Simulated agents',s.population],['Street traffic (visual)',world.trafficCount+' cars'],['At home',s.atHome],['In transit',s.commuting],['At work',s.atWork],['Socializing',s.socializing],['No route',s.stranded||0],['Sheltered',s.sheltered||0],['Active incidents',(s.incidents||[]).filter(i=>!['resolved','averted'].includes(i.status)).length]]));
      $('districts').replaceChildren(...rows(s.districts.map(d=>[d.name,d.status])));
    }
    $('serviceAccess').textContent=CityPlan.landmarks.filter(l=>['hall','hospital'].includes(l.site)).map(l=>l.name+' · '+(CityPlan.access(l)?'road access connected':'needs road access')).join(' / ');
    $('incidentCards').replaceChildren(...(s?.incidents||[]).filter(i=>!['resolved','averted'].includes(i.status)).map(incident=>{
      const card=document.createElement('article');card.className='incidentCard';
      const title=document.createElement('strong');title.textContent=incident.label+' · '+incident.district;
      const text=document.createElement('p');text.textContent=incident.response+' · '+incident.severity+'% severity'+(incident.responseAccess?' · City Hall route '+(incident.responseAccess.cityHall?'open':'missing')+' · EMS route '+(incident.responseAccess.massGeneral?'open':'missing'):'');
      const button=document.createElement('button');button.className='secondary';button.textContent='Request mayor response';
      button.onclick=()=>{sim?.requestResponse(incident.id);render();};
      card.append(title,text,button);return card;
    }));
    const disconnected=CityPlan.plan.buildings.filter(b=>!CityPlan.access(b));
    $('areas').replaceChildren(...CityPlan.plan.buildings.map(b=>{const row=document.createElement('div');row.className='areaRow';const name=document.createElement('span');name.textContent=b.label||labels[b.type]||'Building';const status=document.createElement('small');status.textContent=(labels[b.type]||b.type)+' · '+(CityPlan.access(b)?'Connected':'Needs road')+((s?.damage?.[b.id]||0)>0?' · Damage '+s.damage[b.id]+'%':'');row.append(name,status);return row;}));
    $('accessSummary').textContent=disconnected.length?(CityPlan.plan.buildings.length-disconnected.length)+' / '+CityPlan.plan.buildings.length+' sites connected':'All sites connected';
    $('time').textContent=time(s?.minute??360);$('pop').textContent=(CityPlan.cityPopulation()+CityPlan.plan.buildings.filter(b=>!b.area&&b.type==='residential').length*Math.round((window.BOSTON_BUILDINGS?.population||0)/Math.max(1,CityPlan.city.filter(b=>b.k==='res').length))).toLocaleString();
    $('happy').textContent=s?Math.round(s.satisfaction)+'%':'—';$('authority').textContent=s?Math.round(s.authority)+'%':'—';
    $('hall').textContent=s?.hallProtected===false?'Exposed':'Protected';
    $('phase').textContent=!s?'Planning':s.finished?'Day complete':paused?'Paused':'Day running';
    $('run').textContent=!s?'▶  Run day':s.finished?'↻  Replay day':paused?'▶  Resume':'Ⅱ  Pause';
    $('plan').disabled=!s;$('speed').disabled=!s||s.finished;
    $('thought').textContent='“'+(e?.thought||'Where we put homes and workplaces will shape the morning commute.')+'”';
    $('action').textContent=e?e.action:'Awaiting your city plan.';
    $('outcome').textContent=e?[e.district,e.status,e.outcome].filter(Boolean).join(' · '):'';
    if(!$('historyPane').hidden && lastEntry!==JSON.stringify(e))history(s);
    lastEntry=JSON.stringify(e);world.update(lots,s?.agents||[],s||{});
  }
  function start() {
    syncSites();
    if(!Object.values(lots).includes('residential')||!Object.values(lots).includes('office')) {
      notice('Place at least one residence and one office to run the day.');return;
    }

    const homes=CITY_LOTS.filter(b=>b.type==='residential'),offices=CITY_LOTS.filter(b=>b.type==='office');
    if(!CityPlan.plan.roads.length){notice('Draw roads to connect your homes and workplaces.');return;}
    if(!homes.some(h=>offices.some(o=>CityPlan.route(h,o)&&CityPlan.route(o,h)))){notice('Connect at least one residential area to an office area with a route in both directions.');return;}
    roadStart=curveControl=null;world.ghost(null);
    sim?.dispose();scoreHistory=[];sim=CitySim.start(lots,{engine:'http://127.0.0.1:8787',mayorBackend:settings,autonomy:Number($('autonomy').value),mayorModelName:engineInfo?.mayor_local_model,residentModelName:engineInfo?.resident_model,autoIncidents:$('autoIncidents').checked});
    paused=false;selection=null;drawPalette();notice('The city is running. Watch the mayor’s orders and their outcomes.');render();
  }
  $('run').onclick=()=>{if(!sim||sim.getState().finished)start();else{paused=!paused;render();}};
  $('plan').onclick=()=>{sim?.dispose();sim=null;paused=false;speed=1;$('speed').textContent='1×';notice('Day reset. Your road plan is preserved.');drawPalette();render();};
  $('speed').onclick=()=>{speed=speed===1?3:speed===3?8:1;$('speed').textContent=speed+'×';};
  $('remove').onclick=()=>{choose('remove');notice('Click a building, road or traffic control to remove it. Historical landmarks, locked services and neighbourhood anchors are protected.');};
  $('history').onclick=$('bubble').onclick=()=>{history(sim?.getState());$('historyPane').hidden=false;};
  $('in').onclick=()=>world.zoom(1);$('out').onclick=()=>world.zoom(-1);$('reset').onclick=()=>world.resetView();
  function dialog(title) {
    const body=$('dialogBody');body.replaceChildren();const h=document.createElement('h2');h.textContent=title;body.append(h);$('dialog').showModal();return body;
  }
  $('accessHelp').onclick=()=>{
    const body=dialog('Neighborhood road access');
    const p=document.createElement('p');p.className='muted';p.textContent='Fixed neighborhoods have gold access points. Player buildings have a gold entrance on their front side. Connect a road to that point, or pass within 20 meters with a clear connection on land. A light driveway confirms access. Roads snap to access points. Use R or Rotate before placement to face a building entrance toward the road. Player buildings can be bulldozed and placed again. Homes need a road route to an office and back, following one-way directions. Use bridges across the river. You can run a partially connected city and watch which residents reach work.';body.append(p);
  };
  // Editing is only allowed in the top-down view; 3D is for looking around.
  function syncViewButton(){$('view').textContent=world.is3D?'Top-down (edit)':'3D view';}
  function topDownOnly(){if(!world.is3D)return true;world.toggleView('top');syncViewButton();notice('Editing works in the top-down view, so the map switched to top-down. Use 3D view to look around.');return false;}
  $('view').onclick=()=>{world.toggleView();syncViewButton();if(world.is3D){roadStart=curveControl=null;world.ghost(null);}};
  syncViewButton();
  $('settings').onclick=()=>{
    const body=dialog('Mayor settings'),label=document.createElement('label');label.textContent='Decision engine ';const select=document.createElement('select');
    select.add(new Option('Local mayor · '+(engineInfo?.mayor_local_model||'engine model')+' (Ollama)','local'));select.add(new Option('Rule-based (no model)','baseline'));select.add(new Option('Claude API (cloud)','api'));select.value=settings;label.append(select);body.append(label);
    const p=document.createElement('p');p.className='muted';p.textContent='Changes apply on the next run. Decisions come from the Python engine (uv run aia serve, port 8787), which chooses the models from config/engine.yaml (local mayor: '+(engineInfo?.mayor_local_model||'engine offline')+'; residents: '+(engineInfo?.resident_model||'engine offline')+'). The Claude API needs AIA_ALLOW_PAID_API=1 and ANTHROPIC_API_KEY set where the engine runs. If the engine is offline, the civic controller takes over.';body.append(p);
    if(sim){const info=document.createElement('p');info.textContent='Current engine · '+sim.getState().mayorMode;body.append(info);}
    select.onchange=()=>{settings=select.value;$('mayorBrain').value=settings;try{localStorage.setItem('borough-mayor',settings);}catch{}render();};
  };
  syncSites();drawPalette();render();
  let previousFrame=performance.now(),lastUI=0;
  function frame(now){
    const delta=Math.min(.1,(now-previousFrame)/1000);previousFrame=now;
    world.setTrafficPaused(!!sim&&(paused||sim.getState().finished));
    if(sim&&!paused&&!sim.getState().finished){
      sim.step(delta*4*speed);
      if(now-lastUI>=120){render();lastUI=now;}
      else{const state=sim.getState();world.update(lots,state.agents,state);}
    }
    else if(sim&&now-lastUI>=250){render();lastUI=now;}
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
