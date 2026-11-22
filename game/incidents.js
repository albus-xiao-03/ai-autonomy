// Arcade incident state and municipal response logistics.
window.CityIncidents = (() => {
  const types={
    flood:{label:'Flood',radius:100,severity:65,damage:25,duration:180,fallback:'repair'},
    storm:{label:'Severe storm',radius:125,severity:55,damage:15,duration:120,fallback:'repair'},
    earthquake:{label:'Earthquake',radius:145,severity:75,damage:45,duration:0,fallback:'repair'},
    fire:{label:'Building fire',radius:90,severity:65,damage:35,duration:0,fallback:'dispatch'},
    protest:{label:'Protest',radius:80,severity:50,damage:0,duration:180,fallback:'mediate'}
  };
  function create(options){
    const incidents=[],units=[];
    const accessCache=new Map();
    let serial=0,scheduled=options.automatic!==false,lastDamageKey='';
    const now=()=>options.minute();
    const active=()=>incidents.filter(i=>i.status!=='resolved'&&i.status!=='averted');
    const damage=()=>{
      const result={};
      for(const incident of active())for(const id of incident.affectedSites)result[id]=Math.min(100,(result[id]||0)+incident.damage);
      return result;
    };
    function updateNetwork(){
      const changed=CityPlan.setClosures(incidents,options.protected()?CITY_HALL:null);
      const key=Object.entries(damage()).filter(([,value])=>value>=75).map(([id])=>id).sort().join('|');
      if(changed||key!==lastDamageKey){lastDamageKey=key;options.reroute();}
    }
    function resolve(incident,outcome){
      incident.status='resolved';incident.severity=0;incident.resolvedAt=now();incident.response='Complete';
      options.record('The '+incident.label.toLowerCase()+' response is complete. Local routes can reopen.','Incident resolved','Applied',outcome,incident.district);
      updateNetwork();
    }
    function spawn(kind,p){
      const spec=types[kind],bounds=CityPlan.activeBounds;
      if(!spec)return 'Choose a valid incident.';
      if(!CityPlan.land(p)||p.x<bounds.minX||p.x>bounds.maxX||p.z<bounds.minZ||p.z>bounds.maxZ)return 'Choose unlocked dry land.';
      const protectedPoint=options.protected()&&CityPlan.dist(p,CITY_HALL)<CITY_HALL.radius;
      const incident={id:'incident-'+(++serial),kind,label:spec.label,x:p.x,z:p.z,radius:spec.radius,severity:spec.severity,
        damage:spec.damage,startedAt:now(),duration:spec.duration,status:protectedPoint?'averted':'active',
        district:CityPlan.district(p),response:protectedPoint?'Protected by City Hall':'Awaiting mayor',nextReview:now(),
        affectedSites:options.sites().filter(site=>CityPlan.dist(site,p)<spec.radius+(site.radius||10)&&!(options.protected()&&CityPlan.dist(site,CITY_HALL)<CITY_HALL.radius)).map(site=>site.id)};
      incidents.push(incident);
      if(protectedPoint){options.record('City Hall’s protected zone is holding.','Incident averted','Applied',spec.label+' stayed outside the protected core.',incident.district);return '';}
      const district=options.districts().find(d=>d.name===incident.district);
      if(district){district.authority=Math.max(0,district.authority-(kind==='protest'?18:8));district.status=district.authority<40?'Contested':district.authority<65?'Strained':'Stable';}
      options.record(spec.label+' reported in '+incident.district+'. I’m reviewing the blocked routes and local needs.','Incident reported','Reported',incident.affectedSites.length+' sites affected.',incident.district);
      updateNetwork();return '';
    }
    function stagingRoute(incident,source){
      for(const point of CityPlan.responsePoints(incident).filter(p=>CityPlan.dist(p,incident)<incident.radius+160)){
        const path=options.route(source,point);
        if(path)return {point,path};
      }
      return null;
    }
    function accessFor(incident){
      const cached=accessCache.get(incident.id);
      if(cached?.revision===CityPlan.revision)return cached.value;
      const value={cityHall:!!stagingRoute(incident,CITY_HALL),massGeneral:!!stagingRoute(incident,CITY_HOSPITAL)};
      accessCache.set(incident.id,{revision:CityPlan.revision,value});return value;
    }
    function respond(incident,action,statement){
      if(!active().includes(incident))return;
      incident.nextReview=now()+30;
      const thought=statement||'I’m coordinating a response to the '+incident.label.toLowerCase()+'.';
      if(action==='monitor'){
        incident.response='Monitoring';options.record(thought,'Monitoring incident','Applied','Next review in 30 minutes.',incident.district);return;
      }
      if(action==='outreach'){
        const district=options.districts().find(d=>d.name===incident.district);
        if(district){district.authority=Math.min(100,district.authority+20);district.status=district.authority<40?'Contested':district.authority<65?'Strained':'Stable';}
        incident.nextReview=now()+10;options.record(thought,'Community outreach','Applied','Local authority improved. Physical hazards still need a response.',incident.district);return;
      }
      if(action==='mediate'&&incident.kind!=='protest')action=types[incident.kind].fallback;
      if(action==='mediate'){
        if(!incident.mediationEnds){incident.mediationEnds=now()+35;incident.response='Community mediation';options.record(thought,'Mediation started','Applied','Community representatives are meeting with the mayor.',incident.district);}
        return;
      }
      if(units.some(unit=>unit.incidentId===incident.id&&unit.action===action&&unit.status!=='blocked')){
        incident.response='Response in progress';return;
      }
      const district=options.districts().find(d=>d.name===incident.district);
      if(district?.authority<40){incident.response='Dispatch refused';options.record(thought,'Dispatch refused','Refused','District crews declined the order. Rebuild authority with outreach.',incident.district);return;}
      const source=action==='dispatch'&&incident.kind==='flood'?CITY_HOSPITAL:CITY_HALL;
      const staged=stagingRoute(incident,source);
      if(!staged){incident.response='Needs road access';options.record(thought,'Response blocked','Blocked','Connect '+(source===CITY_HALL?'City Hall’s service point':'Mass General’s EMS point')+' to an open road near the incident.',incident.district);return;}
      const kind=action==='evacuate'?'bus':action==='repair'?'repair':incident.kind==='fire'?'firetruck':incident.kind==='protest'?'police':'ambulance';
      const log=options.record(thought,'Emergency response dispatched','Applied',kind+' traveling to a safe staging point.',incident.district);
      units.push({id:'unit-'+(++serial),incidentId:incident.id,action,kind,status:'enroute',path:staged.path,point:staged.point,startedAt:now(),log});
      incident.response='Response en route';
    }
    function refreshUnits(){
      for(const unit of units.filter(u=>u.status==='enroute')){
        const incident=incidents.find(i=>i.id===unit.incidentId);
        const point=options.position(unit.path,(now()-unit.startedAt)/Math.max(2,unit.path.length/360));
        const road=CityPlan.nearestRoad(point,3);
        const atService=CityPlan.landmarks.some(site=>['hall','hospital'].includes(site.site)&&CityPlan.dist(point,site)<site.radius&&CityPlan.access(site));
        const canLeave=atService||(road&&!CityPlan.roadBlocked(road)&&Math.abs(CityPlan.heightAt(point,road)-(point.height||0))<1);
        const replacement=canLeave?stagingRoute(incident,point):null;
        if(replacement){unit.path=replacement.path;unit.point=replacement.point;unit.startedAt=now();}
        else{unit.status='blocked';unit.log.outcome='Road changes interrupted this response.';incident.response='Needs an open route';incident.nextReview=now()+5;}
      }
    }
    function tick(){
      if(scheduled&&now()===585){
        const site=options.sites().find(s=>s.type==='office')||options.sites()[0];
        if(site)spawn('protest',site);
      }
      if(scheduled&&now()===675){
        const site=options.sites().find(s=>s.type==='residential')||options.sites()[0];
        if(site)spawn(CityPlan.level%2?'flood':'storm',site);
      }
      for(const incident of active()){
        if(incident.mediationEnds&&now()>=incident.mediationEnds){resolve(incident,'The protest dispersed after mediation.');continue;}
        if(incident.status==='active'&&incident.duration&&now()-incident.startedAt>=incident.duration){
          if(incident.kind==='protest'){resolve(incident,'The protest dispersed. Local authority remains affected.');continue;}
          incident.status='recovering';incident.response='Weather eased · repairs needed';
          options.record('Weather conditions are improving. Crews still need to repair affected sites.','Weather eased','Reported','Road closures lifted; building damage remains.',incident.district);updateNetwork();
        }
        if(incident.status==='active'&&incident.kind==='fire'&&(now()-incident.startedAt)%15===0){incident.damage=Math.min(100,incident.damage+8);updateNetwork();}
      }
      for(const unit of units){
        const incident=incidents.find(i=>i.id===unit.incidentId);
        if(!active().includes(incident)){unit.status='complete';continue;}
        if(unit.status==='enroute'&&now()-unit.startedAt>=Math.max(2,unit.path.length/360)){
          unit.status='onsite';unit.arrivedAt=now();incident.response='Crews working';
          unit.log.outcome='Response arrived at a safe staging point.';
        }
        const work=unit.action==='evacuate'?20:unit.action==='repair'?60:45;
        if(unit.status==='onsite'&&now()-unit.arrivedAt>=work){
          unit.status='complete';
          if(unit.action==='evacuate'){
            incident.evacuated=true;incident.response='Residents sheltered';incident.nextReview=now();
            options.record('Residents have reached shelter. Repair work still needs to continue.','Evacuation completed','Applied','Affected households are sheltered.',incident.district);options.reroute();
          }else resolve(incident,'Crews restored road access and repaired affected sites.');
        }
      }
      if(!options.deciding()){
        const incident=active().find(i=>i.nextReview<=now()&&!i.mediationEnds&&!units.some(u=>u.incidentId===i.id&&['enroute','onsite'].includes(u.status)));
        if(incident){incident.nextReview=now()+30;options.review(incident,types[incident.kind].fallback);}
      }
    }
    return {spawn,respond,tick,refreshUnits,damage,active,
      accessFor,
      automatic(value){scheduled=!!value;},
      isSheltered(id){return active().some(i=>i.evacuated&&i.affectedSites.includes(id));},
      request(id){const incident=active().find(i=>i.id===id);if(incident){incident.nextReview=now();if(!options.deciding())options.review(incident,types[incident.kind].fallback);}},
      state(time=now()){
        return {incidents:incidents.map(incident=>({...incident,responseAccess:active().includes(incident)?accessFor(incident):null})),damage:damage(),automatic:scheduled,responders:units.filter(u=>u.status==='enroute').map(u=>({...options.position(u.path,(time-u.startedAt)/Math.max(2,u.path.length/360)),id:u.id,kind:u.kind})),
          affectedResidents:active().filter(i=>i.evacuated).flatMap(i=>i.affectedSites)};
      }};
  }
  return {types,create};
})();
