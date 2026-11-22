// One simulated Boston day. The map supplies street paths and fixed landmarks.
window.CitySim = (() => {
  const OPEN = 360;
  const CLOSE = 1320;
  const clamp = (n, min, max) => Math.min(max, Math.max(min, n));
  const distance = (a, b) => Math.hypot(a.x - b.x, a.z - b.z);
  const round = n => Math.round(n);

  function route(a, b) {
    const points = window.CITY_PATH?.(a.x, a.z, b.x, b.z);
    if (!points) return null;
    const stops = points.length ? points : [a, b];
    const lengths = stops.slice(1).map((p, i) => distance(p, stops[i]));
    return {stops, lengths, length: lengths.reduce((total, n) => total + n, 0)};
  }

  function position(path, progress) {
    let offset = path.length * clamp(progress, 0, 1);
    for (let i = 0; i < path.lengths.length; i++) {
      const length = path.lengths[i];
      if (length && offset <= length) {
        const a = path.stops[i], b = path.stops[i + 1], t = offset / length;
        return {x: a.x + (b.x - a.x) * t, z: a.z + (b.z - a.z) * t};
      }
      offset -= length;
    }
    return path.stops[path.stops.length - 1];
  }

  function start(lots, config = {}) {
    const hall = window.CITY_HALL || {x:0, z:0, radius:12};
    const hospital = window.CITY_HOSPITAL || {x:-20,z:0};
    const sites = window.CITY_LOTS.map(l => ({...l, type:lots[l.id]}));
    const districts = (window.CITY_DISTRICTS || [...new Set(sites.map(l => l.district))]).map(name => ({
      name, authority:90, status:'Stable'
    }));
    const ofType = t => sites.filter(l => l.type === t);
    const workplaces = ofType('office');
    const leisure = sites.filter(l => ['park','shop','social'].includes(l.type));
    const parking = ofType('parking');
    const residents=ofType('residential').flatMap((home,h)=>{
      const reachableWork=workplaces.filter(work=>route(home,work)&&route(work,home));
      return Array.from({length:6},(_,j)=>{
        const id=6*h+j,work=reachableWork[id%Math.max(1,reachableWork.length)]||null;
        const reachableLeisure=leisure.filter(venue=>route(work||home,venue)&&route(venue,home));
        return {id,home,work,venue:reachableLeisure[id%Math.max(1,reachableLeisure.length)]||null,
          depart:430+(id*13)%65,leave:975+(id*11)%56,place:home,
          activity:'home',trip:null,routeMinutes:0,jobsDone:0,visits:0,carAt:null};
      });
    });
    const outside = sites.filter(l => distance(l, hall) > hall.radius);
    const focal = outside.find(l => l.district === 'North End' && l.type)
      || outside.find(l => l.district === 'North End') || outside[0];
    const target = districts.find(d => d.name === focal?.district) || districts[0];
    let minute = OPEN, elapsed = 0, hallProtected = true, strain = 0, relief = 0;
    let service = null, refuseCount = 0, dispatchCount = 0;
    let ended = false, disposed = false, controller = null, pending = false, modelOffline = false;
    let mayorMode = config.modelEndpoint ? 'Qwen ready' : 'Civic controller';
    const events = [];
    const record = (thought, action, status, outcome = '', district = '') => {
      const event = {minute, thought, action, status, outcome, district};
      events.push(event);
      return event;
    };
    record('The city is waking up. I’ll watch the morning commute from City Hall.',
      'Opened City Hall', 'Applied', 'Morning service is active.', 'Downtown');

    function setAuthority(d, delta) {
      d.authority = clamp(d.authority+delta,0,100);
      d.status = d.authority < 40 ? 'Contested' : d.authority < 65 ? 'Strained' : 'Stable';
    }

    function addTrip(p, to, activity, mode) {
      const legs = [];
      let from = p.place;
      const add = (dest, kind) => {
        if (distance(from, dest) > 0) legs.push({path:route(from,dest),kind});
        from = dest;
      };
      // Drivers return to their parked cars first, then park close to the next destination.
      if (p.id % 3 === 0 && parking.length && mode !== 'walk') {
        const lot = parking.reduce((best,l) => distance(l,to)<distance(best,to) ? l : best);
        if (p.carAt) add(p.carAt,'resident');
        add(lot,'car');
        p.carAt = lot;
      }
      add(to,'resident');
      if (legs.some(leg => !leg.path)) { p.activity = 'stranded'; return; }
      const peak = minute < 570 || (minute > 970 && minute < 1060);
      let duration = 0;
      for (const leg of legs) {
        const speed = leg.kind === 'car' ? (peak ? 230 : 320) : 88;
        duration += Math.max(1,leg.path.length/speed);
        leg.end = duration;
      }
      p.trip = {start:minute, legs, duration, to, activity};
      p.activity = 'commuting';
    }

    function residentTick(p) {
      if (p.trip) {
        const t = p.trip;
        if (minute - t.start < t.duration) return;
        p.place = t.to;
        p.activity = t.activity;
        p.routeMinutes += t.duration;
        p.jobsDone += t.activity === 'work' ? 1 : 0;
        p.visits += t.activity === 'social' ? 1 : 0;
        p.trip = null;
      }
      if (minute === p.depart) {if(p.work)addTrip(p,p.work,'work');else p.activity='stranded';}
      else if (minute >= p.leave && p.activity === 'work') {
        if (p.venue && p.id % 3 !== 1) addTrip(p,p.venue,'social');
        else addTrip(p,p.home,'home');
      } else if (p.activity === 'social' && minute >= 1155 + p.id % 30) addTrip(p,p.home,'home');
      else if (!p.work && minute === p.leave && p.venue) addTrip(p,p.venue,'social');
    }

    // Freeze the simulation clock while a request is in flight. Real-world request
    // latency should not change which event or district a mayor's decision affects.
    async function decide(fallback, question) {
      const enact = (order, statement) => {
        const count = events.length;
        if (order === 'outreach') outreach(statement);
        else if (order === 'dispatch') dispatch(statement);
        if (events.length > count) events.at(-1).source = mayorMode === 'Qwen' ? 'Qwen 3 · 8B' : 'Civic controller';
      };
      if (!config.modelEndpoint || modelOffline || !target || typeof fetch !== 'function') {
        enact(fallback);
        return;
      }
      pending = true;
      mayorMode = 'Qwen deciding';
      controller = new AbortController();
      const active = controller;
      const timeout = setTimeout(() => active.abort(), 30000);
      try {
        const url = new URL(config.modelEndpoint);
        if (!['http:', 'https:'].includes(url.protocol)) throw Error('Unsupported endpoint');
        const prompt = {
          minute, district:target.name, authority:target.authority,
          actionRules:'Dispatch arrives only with authority of at least 40. Outreach can restore 14–29 authority.',
          previousOrder:events.filter(e => ['Ambulance dispatched','Dispatch refused','Community outreach'].includes(e.action)).at(-1),
          question
        };
        const messages = [
          {role:'system',content:'You are the mayor in a fictional Boston city simulator. Return only JSON with order ("dispatch" or "outreach") and statement (one short public announcement, no analysis).'},
          {role:'user',content:JSON.stringify(prompt)+' /no_think'}
        ];
        const model = config.model || 'qwen3:8b';
        // Ollama's native API can disable reasoning explicitly. Its compatible
        // API can consume the entire response budget before emitting JSON.
        const localOllama = ['localhost','127.0.0.1','[::1]'].includes(url.hostname) && url.port === '11434';
        const schema = {type:'object',properties:{order:{type:'string',enum:['dispatch','outreach']},
          statement:{type:'string'}},required:['order','statement']};
        const body = localOllama ? {model,messages,stream:false,think:false,format:schema,
          options:{temperature:0,num_predict:100,num_ctx:2048}} :
          {model,messages,temperature:0,stream:false,response_format:{type:'json_object'},max_tokens:160};
        if (localOllama) url.pathname = '/api/chat';
        const reply = await fetch(url.href, {method:'POST',signal:active.signal,
          headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        if (!reply.ok) throw Error('Model unavailable');
        const data = await reply.json();
        const choice = JSON.parse((localOllama ? data.message.content : data.choices[0].message.content).trim());
        if (!['dispatch','outreach'].includes(choice.order)) throw Error('Unknown order');
        if (!disposed) {
          mayorMode = 'Qwen';
          enact(choice.order,typeof choice.statement === 'string' ? choice.statement.slice(0,180) : '');
        }
      } catch {
        if (!disposed) {
          modelOffline = true;
          mayorMode = 'Civic controller · model offline';
          enact(fallback);
        }
      } finally {
        clearTimeout(timeout);
        pending = false;
      }
    }

    function dispatch(statement) {
      if (!target || !focal) return;
      dispatchCount++;
      const thought = statement || 'Residents need emergency coverage. I’m requesting an ambulance.';
      if (target.authority < 40) {
        refuseCount++;
        record(thought, 'Dispatch refused', 'Refused', 'District control declined the order. The ambulance remains at the hospital.',target.name);
        return;
      }
      const path=route(hospital,focal);
      if(!path){record(thought,'Dispatch blocked','Blocked','No connected road route from Mass General to this district.',target.name);return;}
      const log = record(thought, 'Ambulance dispatched', 'Applied','En route from Massachusetts General Hospital.',target.name);
      service = {path,start:minute, log};
    }

    function outreach(statement) {
      const amenities = leisure.filter(l => l.district === target.name).length;
      setAuthority(target, 14 + Math.min(3,amenities)*5);
      record(statement || 'I’m asking local community leaders to reopen access for emergency crews.',
        'Community outreach', 'Applied', 'District authority is now '+round(target.authority)+'%.',target.name);
    }

    function tick() {
      minute++;
      residents.forEach(residentTick);
      if (minute === 540) record('The morning rush is underway. I’m checking who made it to work.',
        'Reviewed commute', 'Applied', residents.filter(p => p.activity === 'work').length+' residents have arrived.');
      if (target && minute === 720) {
        const localAmenities = leisure.filter(l => l.district === target.name).length;
        setAuthority(target, -62+Math.min(4,localAmenities)*6);
        record('A corruption report just reached City Hall. Local crews are questioning our authority.',
          'District incident opened','Reported',target.status+' · '+round(target.authority)+'% authority.',target.name);
      }
      if (target && minute === 800) decide('dispatch', 'How will you respond to the first district service request?');
      if (target && minute === 900) {
        decide(refuseCount ? 'outreach' : !dispatchCount ? 'dispatch' : 'outreach',
          'Review the outcome of your last order. How will you improve service for the afternoon?');
      }
      if (target && minute === 960 && !service && !relief && target.authority >= 40) dispatch();
      if (target && minute === 1020 && CityPlan.level>=3 && !leisure.length) {
        for (const d of districts) setAuthority(d,-40);
        record('Unresolved complaints are spreading as workers head home. I’m checking every district.',
          'Citywide service alert','Reported','District authority fell across the city.');
      }
      if (service && minute-service.start >= Math.max(5,service.path.length/440)) {
        service.log.outcome = 'Ambulance arrived after '+(minute-service.start)+' minutes.';
        setAuthority(target,8); relief++; service=null;
      }
      strain = districts.filter(d => d.authority < 60).length > districts.length / 2 ? strain+1 : 0;
      if (hallProtected && strain === 1) record('Service is breaking down across Boston. City Hall’s protected radius is under pressure.',
        'City Hall warning','Reported','Protection will fail after an hour of sustained citywide disruption.','Downtown');
      if (hallProtected && strain >= 60) {
        hallProtected=false;
        record('The disruption has reached City Hall. The protected zone can no longer hold.',
          'Protection lost','Reported','City Hall now shares the surrounding district’s risk.','Downtown');
      }
      if (minute >= CLOSE) {
        ended=true;
        record('The day is complete. I’ve recorded the outcomes for the next planning session.',
          'Daily report closed','Applied', residents.filter(p => p.activity === 'home').length+' residents are home.');
      }
    }

    function getState() {
      const agents = [];
      const rush=(minute>=390&&minute<=570)||(minute>=990&&minute<=1170);
      const highway=CityPlan.plan.roads.find(r=>r.fixed);
      if(rush&&highway){
        for(let i=0;i<20;i++){
          const t=((minute*0.028+i/20)%1);
          const east=i%2===0,progress=east?t:1-t;
          agents.push({x:highway.a.x+(highway.b.x-highway.a.x)*progress,z:highway.a.z+(east?2.5:-2.5),kind:'car',id:'through-'+i});
        }
      }
      for (const p of residents) {
        if (!p.trip) continue;
        const age = minute + elapsed - p.trip.start;
        let prev = 0;
        for (const leg of p.trip.legs) {
          if (age <= leg.end) {
            agents.push({...position(leg.path,(age-prev)/(leg.end-prev)), kind:leg.kind,id:p.id});
            break;
          }
          prev = leg.end;
        }
      }
      if (service) agents.push({...position(service.path,(minute+elapsed-service.start)/Math.max(5,service.path.length/440)),kind:'ambulance',id:-1});
      const n = residents.length;
      const workRate = minute < 540 ? 1 : residents.filter(p => p.jobsDone).length / Math.max(1,n);
      const avgTravel = residents.reduce((sum,p) => sum+p.routeMinutes,0)/Math.max(n,1);
      const satisfaction = n ? round(clamp(70+12*workRate + Math.min(6,leisure.length*2)
        - Math.min(24,avgTravel/7) - 7*refuseCount + 4*relief - (hallProtected?0:8),0,100)) : 0;
      const count = type => residents.filter(p => p.activity === type).length;
      return {minute, finished:ended, agents,population:n, satisfaction, hallProtected, districts,
        authority:round(districts.reduce((sum,d) => sum+d.authority,0)/Math.max(1,districts.length)),
        events,mayorMode,pending,throughTraffic:rush?20:0,workersArrived:residents.filter(p=>p.jobsDone).length,commuting:count('commuting'),socializing:count('social'),atHome:count('home'),atWork:count('work'),stranded:count('stranded')};
    }
    return {getState,step(minutes) {
      if (Number.isFinite(minutes) && minutes > 0 && !disposed && !ended && !pending) {
        elapsed = Math.min(CLOSE-minute, elapsed+minutes);
        while (elapsed >= 1 && !ended && !pending) { elapsed--; tick(); }
        if (pending) elapsed = 0;
      }
      return getState();
    },dispose() {disposed=true; controller?.abort();}};
  }
  return {start};
})();
