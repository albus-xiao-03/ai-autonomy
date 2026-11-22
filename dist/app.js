(() => {
  const $ = id => document.getElementById(id);
  const stock = {residential:6, office:4, shop:3, social:3, park:4, parking:3};
  const labels = {residential:'Residences', office:'Offices', shop:'Shops', social:'Social venues', park:'Parks', parking:'Parking'};
  const lots = {};
  let selection=null,sim=null,paused=false,speed=1,lastEntry=null,settings='qwen',rotation=0,roadStart=null,startingLevel=1;
  const undo=[];
  const time=value=>String(Math.floor(value/60)).padStart(2,'0')+':'+String(Math.floor(value%60)).padStart(2,'0');
  const left=type=>stock[type]-CityPlan.plan.buildings.filter(b=>b.type===type).length;
  const notice=message=>{$('notice').textContent=message;};
  try{
    const saved=JSON.parse(localStorage.getItem('borough-levels-v1')||'null');
    startingLevel=Number.isInteger(saved?.level)?saved.level:1;
    CityPlan.seedArcade(startingLevel);
    if(saved?.roads)for(const r of saved.roads)if(!r.fixed&&CityPlan.widths[r.type]&&r.a&&r.b&&!CityPlan.roadError(r.a,r.b,r.type,!!r.bridge))CityPlan.plan.roads.push(r);
    settings=localStorage.getItem('borough-mayor')||'qwen';
  }catch{CityPlan.seedArcade();}
  CityPlan.changed();
  function save(){try{localStorage.setItem('borough-levels-v1',JSON.stringify({level:CityPlan.level,roads:CityPlan.plan.roads}));}catch{notice('Browser storage is unavailable. Keep this page open to preserve your plan.');}}
  const world=CityWorld.mount($('world'),{
    onPoint:place,
    getTool:()=>({pan:!selection||!!sim,dragRoad:!!CityPlan.widths[selection]&&$('roadMode').value==='drag'&&!sim}),
    onRoadStart:p=>{roadStart=CityPlan.snap(p);},
    onRoadEnd:p=>{const placed=place(p);roadStart=null;world.ghost(null);if(placed)notice('Road placed. Drag to draw another segment.');},
    onRoadCancel:()=>{roadStart=null;world.ghost(null);},
    onHover:p=>{if(!sim&&selection&&selection!=='remove')world.ghost(p,selection,rotation,roadStart,$('bridge').checked);}
  });
  function syncSites(){CITY_LOTS.splice(0,CITY_LOTS.length,...CityPlan.plan.buildings.map(b=>({...b,district:CityPlan.district(b)})));for(const key of Object.keys(lots))delete lots[key];for(const b of CITY_LOTS)lots[b.id]=b.type;}
  function choose(type){selection=selection===type?null:type;roadStart=null;world.ghost(null);drawPalette();render();notice(!selection?'Drag anywhere on the map to move. Wheel to zoom at the pointer.':CityPlan.widths[type]?($('roadMode').value==='drag'?'Drag from the road start to its end.':'Click the start and end of a road. Continue clicking to extend it. Escape ends the road.'):'Click open land to place a building. R rotates it.');}
  function drawPalette(){
    $('palette').replaceChildren();
    for(const type of Object.keys(stock)){
      const button=document.createElement('button');button.className='tile';button.disabled=!!sim;button.setAttribute('aria-pressed',selection===type);
      button.innerHTML='<img alt="" src="art/'+type+'.png"><span>'+labels[type]+'</span><b>×'+left(type)+'</b>';
      button.onclick=()=>choose(type);$('palette').append(button);
    }
    for(const button of document.querySelectorAll('[data-road]')){button.disabled=!!sim;button.setAttribute('aria-pressed',selection===button.dataset.road);}
    $('pan').setAttribute('aria-pressed',!selection);
    $('clearRoads').disabled=!!sim||!CityPlan.plan.roads.some(r=>!r.fixed);
    $('remove').classList.toggle('active',selection==='remove');$('remove').disabled=!!sim;$('undo').disabled=!!sim||!undo.length;
    $('rotate').textContent='Rotate · '+Math.round(rotation*180/Math.PI)+'°';
  }
  function place(p){
    if(sim||!selection)return;
    let error='';
    const snapshot=JSON.stringify(CityPlan.plan);
    if(selection==='remove')error=CityPlan.remove(p);
    else if(CityPlan.widths[selection]){
      p=CityPlan.snap(p);
      if(!roadStart){if(!CityPlan.land(p)){notice('Start the road on dry land.');return;}roadStart=p;notice('Choose the road end. One-way traffic follows your drawing direction.');return;}
      error=CityPlan.road(roadStart,p,selection,$('bridge').checked);
      if(!error){roadStart=p;notice('Road placed. Click to extend it or press Escape to finish.');}
    }else{
      if(!left(selection)){notice('All buildings of this type have been placed.');return;}
      error=CityPlan.place(p,selection,rotation);
    }
    if(error){notice(error);return;}
    undo.push(snapshot);save();syncSites();drawPalette();render();return true;
  }
  document.querySelectorAll('[data-road]').forEach(button=>button.onclick=()=>choose(button.dataset.road));
  $('undo').onclick=()=>{const snapshot=undo.pop();if(!snapshot)return;const old=JSON.parse(snapshot);CityPlan.plan.buildings=old.buildings;CityPlan.plan.roads=old.roads;CityPlan.changed();roadStart=null;world.ghost(null);save();syncSites();drawPalette();render();notice('Last edit undone.');};
  $('clearRoads').onclick=()=>{
    undo.push(JSON.stringify(CityPlan.plan));CityPlan.plan.roads=CityPlan.plan.roads.filter(r=>r.fixed);CityPlan.changed();roadStart=null;world.ghost(null);save();drawPalette();render();notice('Player roads cleared. Undo restores them.');
  };
  function rotate(){if(sim)return;rotation=(rotation+Math.PI/4)%(Math.PI*2);drawPalette();}
  $('rotate').onclick=rotate;
  $('nextLevel').onclick=()=>{
    sim?.dispose();sim=null;paused=false;
    CityPlan.seedArcade(CityPlan.level+1);undo.length=0;
    selection=null;roadStart=null;syncSites();save();drawPalette();world.focusLevel();render();
    notice('New neighborhoods unlocked. Your existing roads remain in place.');
  };
  $('pan').onclick=()=>choose(null);
  $('roadMode').onchange=()=>{roadStart=null;world.ghost(null);notice($('roadMode').value==='drag'?'Drag from one road endpoint to the other.':'Click each road endpoint. Escape switches to moving the map.');};
  $('bridge').onchange=()=>{roadStart=null;world.ghost(null);notice($('bridge').checked?'Bridge mode enabled. Choose a road type, then connect two dry-land banks.':'Land road mode enabled.');};
  document.addEventListener('keydown',e=>{if(e.target.matches('input,select,textarea'))return;if(e.key==='Escape'){selection=null;roadStart=null;world.ghost(null);drawPalette();render();notice('Move map selected. Drag to explore the city.');}if(e.key.toLowerCase()==='r')rotate();});
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
    $('planningTools').hidden=!!s&&!s.finished;
    $('cityLife').hidden=!s||s.finished;
    $('levelTitle').textContent='Level '+CityPlan.level+' / 4';
    const entry=CityPlan.plan.roads.find(r=>r.fixed);
    const homes=CityPlan.plan.buildings.filter(b=>b.type==='residential');
    const entryConnected=homes.every(h=>CityPlan.route(h,entry.a)&&CityPlan.route(entry.a,h));
    const allConnected=CityPlan.plan.buildings.every(b=>CityPlan.access(b));
    const complete=!!s?.finished&&s.workersArrived===s.population&&s.atHome===s.population&&entryConnected&&allConnected;
    $('nextLevel').hidden=!complete||CityPlan.level===4;
    $('levelGoal').textContent=complete?(CityPlan.level===4?'Boston is connected. All levels complete.':'Level complete. Expand the map when you’re ready.'):'Connect homes, offices and the entry highway. Get every resident to work and home.';
    $('engine').textContent=s?.mayorMode || (settings==='qwen'?'Local Qwen · 8B':'Civic controller');
    if(s) {
      const rows=(items)=>items.map(([key,value])=>{const row=document.createElement('div');row.className='statrow';const name=document.createElement('span');name.textContent=key;const val=document.createElement('b');val.textContent=value;row.append(name,val);return row;});
      $('routines').replaceChildren(...rows([['At home',s.atHome],['In transit',s.commuting],['At work',s.atWork],['Socializing',s.socializing],['No route',s.stranded||0],['Through traffic',s.throughTraffic||0]]));
      $('districts').replaceChildren(...rows(s.districts.map(d=>[d.name,d.status])));
    }
    const disconnected=CityPlan.plan.buildings.filter(b=>!CityPlan.access(b));
    $('areas').replaceChildren(...CityPlan.plan.buildings.map(b=>{const row=document.createElement('div');row.className='areaRow';const name=document.createElement('span');name.textContent=b.label;const status=document.createElement('small');status.textContent=(b.type==='residential'?'Homes':b.type==='office'?'Offices':'Social')+' · '+(CityPlan.access(b)?'Connected':'Needs road');row.append(name,status);return row;}));
    $('accessSummary').textContent=disconnected.length?(CityPlan.plan.buildings.length-disconnected.length)+' / '+CityPlan.plan.buildings.length+' areas connected':'All areas connected';
    $('time').textContent=time(s?.minute??360);$('pop').textContent=s?.population??0;
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
    roadStart=null;world.ghost(null);
    sim?.dispose();sim=CitySim.start(lots,settings==='qwen'?{modelEndpoint:'http://localhost:11434/api/chat',model:'qwen3:8b'}:{});
    paused=false;drawPalette();notice('The city is running. Watch the mayor’s orders and their outcomes.');render();
  }
  $('run').onclick=()=>{if(!sim||sim.getState().finished)start();else{paused=!paused;render();}};
  $('plan').onclick=()=>{sim?.dispose();sim=null;paused=false;speed=1;$('speed').textContent='1×';notice('Road planning reopened. Connect the fixed neighborhood access points.');drawPalette();render();};
  $('speed').onclick=()=>{speed=speed===1?3:speed===3?8:1;$('speed').textContent=speed+'×';};
  $('remove').onclick=()=>{choose('remove');notice('Click a road to remove it. Neighborhoods and landmarks are fixed.');};
  $('history').onclick=$('bubble').onclick=()=>{history(sim?.getState());$('historyPane').hidden=false;};
  $('in').onclick=()=>world.zoom(1);$('out').onclick=()=>world.zoom(-1);$('reset').onclick=()=>world.resetView();
  function dialog(title) {
    const body=$('dialogBody');body.replaceChildren();const h=document.createElement('h2');h.textContent=title;body.append(h);$('dialog').showModal();return body;
  }
  $('accessHelp').onclick=()=>{
    const body=dialog('Neighborhood road access');
    const p=document.createElement('p');p.className='muted';p.textContent='Each neighborhood has a gold access point on its boundary. Connect a road to that point, or pass within 20 meters with a clear connection on land. A light driveway confirms access. Roads snap to access points. Neighborhoods are fixed for this arcade level. Homes need a road route to an office and back, following one-way directions. Use bridges across the river. You can run a partially connected city and watch which residents reach work.';body.append(p);
  };
  $('view').onclick=()=>world.toggleView();
  $('settings').onclick=()=>{
    const body=dialog('Mayor settings'),label=document.createElement('label');label.textContent='Decision engine ';const select=document.createElement('select');
    select.add(new Option('Built-in civic controller','local'));select.add(new Option('Qwen 3 · local Ollama','qwen'));select.value=settings;label.append(select);body.append(label);
    const p=document.createElement('p');p.className='muted';p.textContent='Changes apply on the next run. Qwen uses qwen3:8b through Ollama on localhost:11434. The civic controller takes over when the model is unavailable.';body.append(p);
    if(sim){const info=document.createElement('p');info.textContent='Current engine · '+sim.getState().mayorMode;body.append(info);}
    select.onchange=()=>{settings=select.value;try{localStorage.setItem('borough-mayor',settings);}catch{}render();};
  };
  syncSites();drawPalette();render();
  setInterval(()=>{if(sim&&!paused&&!sim.getState().finished){sim.step(speed);render();}},120);
})();
