/* Embervale Atlas. No runtime dependencies or build step. */
'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const icon = (name, cls = '') => `<svg class="${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const escapeHTML = value => String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const ROMAN = ['','I','II','III','IV'];
  const COLORS = ['','#e8c78c','#e0aa63','#ed9153','#d96d51'];
  const STORAGE_KEY = 'embervale-atlas-v1';
  const TILE_URL = 'https://tiles.mapgenie.io/games/enshrouded/embervale/default-v7';
  const WORLD_SIZE = 2 ** 16 * 256;
  const ORIGIN = 32512 * 256;
  const MAP_SIZE = 65536;
  const DEFAULT_MPP = .5; // Approximation, explicitly labelled until the user calibrates.
  const MIN_ZOOM = 9, MAX_ZOOM = 18;
  const clamp = (v, min, max) => Math.max(min, Math.min(max, v));
  const project = (lat, lng) => ({x:(lng + 180) / 360 * WORLD_SIZE - ORIGIN, y:(1 - Math.log(Math.tan(lat * Math.PI / 180) + 1 / Math.cos(lat * Math.PI / 180)) / Math.PI) / 2 * WORLD_SIZE - ORIGIN});
  const locations = (window.EMBERVALE_LOCATIONS || []).map(([name, lat, lng, type]) => ({name, type, ...project(lat,lng)}));
  const kelvin = project(.59582999150221,-.79203182243009);
  const defaultState = () => ({version:1,altars:[{id:'first-flame',name:'Fort Kelvin base',x:kelvin.x,y:kelvin.y,level:3,visible:true}],selected:'first-flame',center:{...kelvin},zoom:14.7,metersPerPixel:DEFAULT_MPP,calibrated:false,compare:true,boundaries:true,landmarks:true,grid:false});
  const validNumber = value => typeof value === 'number' && Number.isFinite(value);
  function validate(data) {
    if(!data || data.version !== 1 || !Array.isArray(data.altars) || data.altars.length > 100) throw Error('Invalid plan');
    const ids = new Set();
    const altars = data.altars.map(a => {
      if(!a || typeof a.id !== 'string' || a.id.length > 80 || ids.has(a.id) || !validNumber(a.x) || !validNumber(a.y) || a.x < 0 || a.x > MAP_SIZE || a.y < 0 || a.y > MAP_SIZE || !Number.isInteger(a.level) || a.level < 1 || a.level > 4 || typeof a.name !== 'string') throw Error('Invalid altar');
      ids.add(a.id);
      return {id:a.id,name:a.name.slice(0,60) || 'Unnamed altar',x:a.x,y:a.y,level:a.level,visible:a.visible !== false};
    });
    const base = defaultState();
    return {...base,altars,selected:altars.some(a=>a.id===data.selected)?data.selected:altars[0]?.id||null,center: data.center && validNumber(data.center.x) && validNumber(data.center.y) ? {x:clamp(data.center.x,0,MAP_SIZE),y:clamp(data.center.y,0,MAP_SIZE)} : {...kelvin},zoom:validNumber(data.zoom)?clamp(data.zoom,MIN_ZOOM,MAX_ZOOM):base.zoom,metersPerPixel:validNumber(data.metersPerPixel)&&data.metersPerPixel>=.0001&&data.metersPerPixel<=1000?data.metersPerPixel:DEFAULT_MPP,calibrated:data.calibrated===true,compare:data.compare!==false,boundaries:data.boundaries!==false,landmarks:data.landmarks!==false,grid:data.grid===true};
  }
  let state=defaultState(), startMessage='';
  let imported=false;
  if(location.hash.startsWith('#plan=')) {
    try {
      const encoded=location.hash.slice(6);
      if(encoded.length>50000) throw Error('Plan too large');
      const bytes=Uint8Array.from(atob(encoded.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0));
      state=validate(JSON.parse(new TextDecoder().decode(bytes))); imported=true;
      startMessage='Shared plan opened. Saved on this device.';
    } catch {startMessage='This plan link is invalid. Your saved plan is still available.';}
  }
  if(!imported) {try { const stored=localStorage.getItem(STORAGE_KEY); if(stored) state=validate(JSON.parse(stored)); }catch {startMessage='Saved plan could not be read. Starting a new plan.';}}
  const history=[];
  let width=0,height=0,frame=0,mode=null,calibrationPoints=[],gesture=null,toastTimer,saveTimer,loadedTiles=0,searchItems=[];
  const pointers=new Map(), tileCache=new Map();
  const map=$('map'),tiles=$('tiles'),overlay=$('overlay'),markers=$('markers');
  const selected=()=>state.altars.find(a=>a.id===state.selected);
  const factor=()=>2**(state.zoom-16);
  const screen=p=>({x:(p.x-state.center.x)*factor()+width/2,y:(p.y-state.center.y)*factor()+height/2});
  const world=p=>({x:(p.x-width/2)/factor()+state.center.x,y:(p.y-height/2)/factor()+state.center.y});
  const localPoint=e=>{const b=map.getBoundingClientRect();return{x:e.clientX-b.left,y:e.clientY-b.top};};
  const snapshot=()=>JSON.stringify(state);
  function checkpoint(before=snapshot()) {history.push(before);if(history.length>50)history.shift();$('undo').disabled=false;}
  function persist() {
    clearTimeout(saveTimer);
    saveTimer=setTimeout(()=>{
      try {localStorage.setItem(STORAGE_KEY,JSON.stringify(state));$('save-state').innerHTML='<i></i>Saved on this device';}
      catch {$('save-state').textContent='Storage unavailable';toast('Browser storage is unavailable. Use Share plan to keep your work.');}
    },150);
  }
  function commit(change,message) {checkpoint();change();updateControls();draw();persist();if(message)toast(message);}
  function toast(message) {$('toast').textContent=message;$('toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('visible'),3500);}
  function clampCenter() {state.center.x=clamp(state.center.x,0,MAP_SIZE);state.center.y=clamp(state.center.y,0,MAP_SIZE);}
  function zoomAt(next,point={x:width/2,y:height/2}) {const before=world(point);state.zoom=clamp(next,MIN_ZOOM,MAX_ZOOM);const f=factor();state.center={x:before.x-(point.x-width/2)/f,y:before.y-(point.y-height/2)/f};clampCenter();draw();persist();}
  function focusAltar() {const a=selected();if(!a)return;state.center={x:a.x,y:a.y};state.zoom=Math.max(state.zoom,14.7);if(!a.visible){a.visible=true;updateControls();}draw();persist();}
  function updateControls() {
    $('altar-count').textContent=state.altars.length;
    $('altar-list').innerHTML=state.altars.length ? state.altars.map(a=>`<div class="altar-row ${a.id===state.selected?'selected':''}" data-altar="${escapeHTML(a.id)}" role="button" tabindex="0" aria-label="Select ${escapeHTML(a.name)}" aria-pressed="${a.id===state.selected}">${a.id===state.selected?'<span class="selection-dot"></span>':''}<span class="altar-symbol">${icon('flame')}</span><span class="altar-description"><strong>${escapeHTML(a.name)}</strong><small>Level ${ROMAN[a.level]} <span>·</span> ${a.level*40} × ${a.level*40} m</small></span><button class="visibility" data-visibility="${escapeHTML(a.id)}" aria-label="${a.visible?'Hide':'Show'} ${escapeHTML(a.name)}" aria-pressed="${a.visible}" title="${a.visible?'Hide':'Show'} altar">${icon('eye')}</button></div>`).join('') : '<div class="no-altars">A world of possibilities.<br>Place your first altar on the map.</div>';
    const a=selected();$('editor').hidden=!a;
    if(a) {
      document.querySelectorAll('[data-level]').forEach(b=>{b.classList.toggle('active',+b.dataset.level===a.level);b.setAttribute('aria-pressed',String(+b.dataset.level===a.level));});
      const side=a.level*40;$('dimensions').innerHTML=`${side} <span>×</span> ${side} <small>m</small>`;$('area-value').textContent=`${(side*side).toLocaleString('en-US')} m²`;$('height-value').textContent=`${side} m vertical`;$('level-badge').textContent=`LEVEL ${a.level}`;
      if(document.activeElement!==$('altar-name'))$('altar-name').value=a.name;
    }
    for(const key of ['compare','boundaries','landmarks','grid'])$(key).checked=state[key];
    $('compare-legend').hidden=!state.compare;
    $('scale-status').innerHTML=`${state.calibrated?'Calibrated':'Approximate'} scale ${icon('ruler')}`;
    $('locate').disabled=!a;
    $('undo').disabled=!history.length;
  }
  function draw() {if(!frame)frame=requestAnimationFrame(render);}
  function render() {
    frame=0; if(!width||!height)return;
    const f=factor(),z=clamp(Math.floor(state.zoom),MIN_ZOOM,16),tileFactor=2**(state.zoom-z),tileSize=256*tileFactor;
    const sourceFactor=2**(16-z),tl=world({x:0,y:0}),br=world({x:width,y:height});
    const minTile=2**(z-1)-2**(z-8),maxTile=2**(z-1)-1;
    const x1=Math.max(minTile,Math.floor((tl.x+ORIGIN)/sourceFactor/256)-1),x2=Math.min(maxTile,Math.floor((br.x+ORIGIN)/sourceFactor/256)+1);
    const y1=Math.max(minTile,Math.floor((tl.y+ORIGIN)/sourceFactor/256)-1),y2=Math.min(maxTile,Math.floor((br.y+ORIGIN)/sourceFactor/256)+1);
    const visible=new Set();let errors=0;
    for(let y=y1;y<=y2;y++)for(let x=x1;x<=x2;x++) {
      const key=`${z}/${y}/${x}`;visible.add(key);
      let entry=tileCache.get(key);
      if(!entry) {
        const img=new Image();img.className='map-tile';img.alt='';img.draggable=false;img.decoding='async';
        entry={img,status:'loading'};tileCache.set(key,entry);
        img.onload=()=>{entry.status='loaded';loadedTiles++;$('map-loading').hidden=true;draw();};
        img.onerror=()=>{entry.status='error';draw();};
        img.src=`${TILE_URL}/${key}.jpg`;
      }
      const p=screen({x:x*256*sourceFactor-ORIGIN,y:y*256*sourceFactor-ORIGIN});
      Object.assign(entry.img.style,{left:`${p.x}px`,top:`${p.y}px`,width:`${tileSize+.5}px`,height:`${tileSize+.5}px`});
      if(!entry.img.parentNode)tiles.append(entry.img);
      if(entry.status==='error')errors++;
    }
    for(const [key,entry] of tileCache)if(!visible.has(key)){entry.img.remove();if(tileCache.size>240)tileCache.delete(key);}
    $('tile-error').hidden=!errors;
    if(errors)$('map-loading').hidden=true;
    let svg='';const markerHTML=[];
    // Building areas stay aligned to the world and retain the same scale as terrain.
    for(const a of state.altars) {
      if(!a.visible)continue;
      const p=screen(a),active=a.id===state.selected;
      const maxSize=(state.compare&&active?160:a.level*40)/state.metersPerPixel*f;
      if(p.x+maxSize/2 < -200 || p.x-maxSize/2>width+200 || p.y+maxSize/2 < -200 || p.y-maxSize/2>height+200)continue;
      if(state.boundaries) {
        const levels=state.compare&&active?[4,3,2,1]:[a.level];
        for(const level of levels) {
          const size=level*40/state.metersPerPixel*f,color=COLORS[level],isCurrent=level===a.level;
          svg+=`<rect class="boundary" x="${p.x-size/2}" y="${p.y-size/2}" width="${size}" height="${size}" fill="${color}" fill-opacity="${active?(isCurrent?.11:.035):.07}" stroke="${color}" stroke-opacity="${active?(isCurrent?1:.7):.65}" stroke-width="${isCurrent&&active?1.8:1}" ${isCurrent?'':'stroke-dasharray="5 4"'}/>`;
          if(active&&size>60)svg+=`<text class="map-dimension" text-anchor="end" x="${p.x+size/2-4}" y="${p.y-size/2-6}">${level*40} m${isCurrent?' · LVL '+ROMAN[level]:''}</text>`;
          if(isCurrent&&active&&size>30) {
            const h=size/2,c=Math.min(8,size/8);svg+=`<path d="M${p.x-h} ${p.y-h+c}v-${c}h${c} M${p.x+h-c} ${p.y-h}h${c}v${c} M${p.x+h} ${p.y+h-c}v${c}h-${c} M${p.x-h+c} ${p.y+h}h-${c}v-${c}" fill="none" stroke="${color}" stroke-width="2.6"/>`;
          }
        }
        if(state.grid&&active) {
          const side=a.level*40,step=10/state.metersPerPixel*f,size=side/state.metersPerPixel*f;
          if(step>=4)for(let i=1;i<side/10;i++){const offset=i*step;svg+=`<path class="grid-line" d="M${p.x-size/2+offset} ${p.y-size/2}v${size} M${p.x-size/2} ${p.y-size/2+offset}h${size}"/>`;}
        }
      }
      const top=state.boundaries?Math.max(34,maxSize/2+25):42;
      markerHTML.push(`<div class="altar-label" style="left:${p.x}px;top:${p.y-top}px">${escapeHTML(a.name)}<small>FLAME ALTAR · ${ROMAN[a.level]}</small></div><button class="altar-marker ${active?'selected':''}" data-map-altar="${escapeHTML(a.id)}" style="left:${p.x}px;top:${p.y}px" aria-label="Move ${escapeHTML(a.name)}" title="Drag to move ${escapeHTML(a.name)}">${icon('flame')}</button>`);
    }
    if(state.landmarks)for(const l of locations) {
      const p=screen(l);if(p.x < -50||p.x>width+50||p.y < -40||p.y>height+40)continue;
      // Keep the altar handle unobstructed and the overview readable.
      if(state.altars.some(a=>a.visible&&Math.hypot(screen(a).x-p.x,screen(a).y-p.y)<90))continue;
      if(state.zoom<12.5&&l.type!=='spire')continue;
      markerHTML.unshift(`<button class="landmark ${l.type}" data-landmark="${locations.indexOf(l)}" style="left:${p.x}px;top:${p.y}px" aria-label="Go to ${escapeHTML(l.name)}" title="${escapeHTML(l.name)}">${icon(l.type==='spire'?'pin':'home')}<span>${state.zoom>12?escapeHTML(l.name):''}</span></button>`);
    }
    if(calibrationPoints.length) {
      const p=screen(calibrationPoints[0]);svg+=`<circle class="calibration-point" cx="${p.x}" cy="${p.y}" r="5"/><text class="map-dimension" x="${p.x+10}" y="${p.y-10}">A</text>`;
      if(calibrationPoints.length===2){const q=screen(calibrationPoints[1]);svg+=`<path class="calibration-line" d="M${p.x} ${p.y}L${q.x} ${q.y}"/><circle class="calibration-point" cx="${q.x}" cy="${q.y}" r="5"/><text class="map-dimension" x="${q.x+10}" y="${q.y-10}">B</text>`;}
    }
    overlay.innerHTML=svg;markers.innerHTML=markerHTML.join('');
    const metersAt90=90/f*state.metersPerPixel,base=10**Math.floor(Math.log10(metersAt90));
    const scaleMeters=[1,2,5,10].map(v=>v*base).filter(v=>v<=metersAt90).pop()||base;
    $('scale-line').style.width=`${scaleMeters/state.metersPerPixel*f}px`;$('scale-label').textContent=scaleMeters>=1000?`${scaleMeters/1000} km`:`${+scaleMeters.toPrecision(3)} m`;
    $('zoom-in').disabled=state.zoom>=MAX_ZOOM;$('zoom-out').disabled=state.zoom<=MIN_ZOOM;
  }
  function setMode(next) {
    mode=next;calibrationPoints=[];
    map.classList.toggle('placing',next==='place');map.classList.toggle('calibrating',next==='calibrate');
    $('placement-banner').hidden=!next;$('map-instruction').hidden=true;$('calibrate').classList.toggle('active',next==='calibrate');
    $('placement-text').textContent=next==='calibrate'?'Choose the first point of a known distance':'Click the map to place your altar';
    if(next){$('sidebar').classList.remove('open');$('mobile-panel').setAttribute('aria-expanded','false');map.focus({preventScroll:true});}draw();
  }
  function addAltar(p) {
    if(state.altars.length>=100){toast('This plan can hold up to 100 altars.');return;}
    commit(()=>{const id=crypto.randomUUID?crypto.randomUUID():`altar-${Date.now()}-${Math.random().toString(36).slice(2)}`;state.altars.push({id,name:`Flame altar ${state.altars.length+1}`,x:clamp(p.x,0,MAP_SIZE),y:clamp(p.y,0,MAP_SIZE),level:selected()?.level||1,visible:true});state.selected=id;state.boundaries=true;},'Flame altar placed. Drag its flame to move it.');setMode(null);
  }
  function onMapClick(p,target) {
    if(mode==='place'){addAltar(world(p));return;}
    if(mode==='calibrate') {
      calibrationPoints.push(world(p));
      if(calibrationPoints.length===1)$('placement-text').textContent='Choose the second point of the known distance';
      else if(Math.hypot(calibrationPoints[1].x-calibrationPoints[0].x,calibrationPoints[1].y-calibrationPoints[0].y)<1){calibrationPoints.pop();toast('Choose a second point farther away.');}
      else {$('calibration-dialog').showModal();$('known-distance').focus();$('known-distance').select();}
      draw();return;
    }
    const landmark=target.closest?.('[data-landmark]');if(landmark)goToLocation(locations[+landmark.dataset.landmark]);
  }
  map.addEventListener('pointerdown',e=>{
    if(e.button!==0)return;
    const p=localPoint(e);pointers.set(e.pointerId,p);map.setPointerCapture(e.pointerId);
    if(pointers.size===2) {
      if(gesture?.type==='altar') {persist();}
      const [a,b]=[...pointers.values()],mid={x:(a.x+b.x)/2,y:(a.y+b.y)/2};
      gesture={type:'pinch',distance:Math.hypot(a.x-b.x,a.y-b.y),zoom:state.zoom,anchor:world(mid),moved:true};return;
    }
    if(pointers.size>2)return;
    const handle=e.target.closest('[data-map-altar]');
    if(handle&&!mode) {
      state.selected=handle.dataset.mapAltar;updateControls();const a=selected();
      gesture={type:'altar',start:p,origin:{x:a.x,y:a.y},before:snapshot(),target:e.target,moved:false};draw();
    }else gesture={type:'pan',start:p,origin:{...state.center},target:e.target,moved:false};
    map.classList.add('dragging');
  });
  map.addEventListener('pointermove',e=>{
    if(!pointers.has(e.pointerId)||!gesture)return;
    const p=localPoint(e);pointers.set(e.pointerId,p);
    if(gesture.type==='pinch') {
      if(pointers.size<2)return;
      const [a,b]=[...pointers.values()],distance=Math.hypot(a.x-b.x,a.y-b.y),mid={x:(a.x+b.x)/2,y:(a.y+b.y)/2};
      if(gesture.distance<1)return;
      state.zoom=clamp(gesture.zoom+Math.log2(distance/gesture.distance),MIN_ZOOM,MAX_ZOOM);
      state.center={x:gesture.anchor.x-(mid.x-width/2)/factor(),y:gesture.anchor.y-(mid.y-height/2)/factor()};clampCenter();draw();return;
    }
    const dx=p.x-gesture.start.x,dy=p.y-gesture.start.y;
    if(Math.hypot(dx,dy)>4)gesture.moved=true;
    if(!gesture.moved)return;
    if(gesture.type==='altar') {const a=selected();a.x=clamp(gesture.origin.x+dx/factor(),0,MAP_SIZE);a.y=clamp(gesture.origin.y+dy/factor(),0,MAP_SIZE);}
    else {state.center={x:gesture.origin.x-dx/factor(),y:gesture.origin.y-dy/factor()};clampCenter();}
    draw();
  });
  function endPointer(e,cancelled=false) {
    if(!pointers.has(e.pointerId))return;
    pointers.delete(e.pointerId);
    if(gesture&&gesture.type!=='pinch') {
      if(gesture.type==='altar'&&gesture.moved){checkpoint(gesture.before);updateControls();}
      else if(!gesture.moved&&!cancelled)onMapClick(localPoint(e),gesture.target);
    }
    // A remaining finger after a pinch cannot accidentally place an altar.
    if(!pointers.size){gesture=null;map.classList.remove('dragging');}else if(gesture?.type==='pinch')gesture={type:'pinch',moved:true,distance:0};
    persist();draw();
  }
  map.addEventListener('pointerup',e=>endPointer(e));map.addEventListener('pointercancel',e=>endPointer(e,true));
  map.addEventListener('wheel',e=>{e.preventDefault();zoomAt(state.zoom-clamp(e.deltaY,-150,150)*.003,localPoint(e));},{passive:false});
  map.addEventListener('dblclick',e=>{if(!mode&&!e.target.closest('[data-map-altar]'))zoomAt(state.zoom+1,localPoint(e));});
  $('add-altar').onclick=()=>setMode('place');$('cancel-placement').onclick=()=>setMode(null);
  $('altar-list').onclick=e=>{
    const visibility=e.target.closest('[data-visibility]');
    if(visibility){commit(()=>{const a=state.altars.find(a=>a.id===visibility.dataset.visibility);a.visible=!a.visible;});return;}
    const row=e.target.closest('[data-altar]');if(row){state.selected=row.dataset.altar;updateControls();focusAltar();}
  };
  $('altar-list').onkeydown=e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('[data-altar]')){e.preventDefault();e.target.click();}};
  document.querySelectorAll('[data-level]').forEach(button=>button.onclick=()=>{const a=selected();if(a&&a.level!==+button.dataset.level)commit(()=>{a.level=+button.dataset.level;});});
  for(const key of ['compare','boundaries','landmarks','grid'])$(key).onchange=e=>commit(()=>{state[key]=e.target.checked;});
  $('altar-name').onchange=e=>{const a=selected(),name=e.target.value.trim().slice(0,60)||'Unnamed altar';if(a&&a.name!==name)commit(()=>{a.name=name;});e.target.value=name;};
  $('center-altar').onclick=focusAltar;$('locate').onclick=focusAltar;
  $('duplicate-altar').onclick=()=>{const a=selected();if(!a)return;if(state.altars.length>=100){toast('This plan can hold up to 100 altars.');return;}commit(()=>{const copy={...a,id:crypto.randomUUID?crypto.randomUUID():`copy-${Date.now()}`,name:(a.name+' copy').slice(0,60),x:clamp(a.x+a.level*40/state.metersPerPixel,0,MAP_SIZE),visible:true};state.altars.push(copy);state.selected=copy.id;state.center={x:copy.x,y:copy.y};},'Altar duplicated beside the original.');};
  $('delete-altar').onclick=()=>{const a=selected();if(!a)return;commit(()=>{state.altars=state.altars.filter(b=>b.id!==a.id);state.selected=state.altars[0]?.id||null;},'Altar removed. Use Undo to bring it back.');};
  $('undo').onclick=()=>{if(!history.length)return;state=validate(JSON.parse(history.pop()));updateControls();draw();persist();toast('Last change undone.');};
  $('zoom-in').onclick=()=>zoomAt(state.zoom+.6);$('zoom-out').onclick=()=>zoomAt(state.zoom-.6);
  $('fit-map').onclick=()=>{state.center=project(.66,-.74);state.zoom=11.5;draw();persist();};
  $('calibrate').onclick=()=>{if(mode==='calibrate')setMode(null);else setMode('calibrate');};$('scale-status').onclick=()=>setMode('calibrate');
  $('calibration-form').onsubmit=e=>{
    e.preventDefault();const distance=+$('known-distance').value;
    if(calibrationPoints.length!==2||!Number.isFinite(distance)||distance<=0)return;
    const pixels=Math.hypot(calibrationPoints[1].x-calibrationPoints[0].x,calibrationPoints[1].y-calibrationPoints[0].y),mpp=distance/pixels;
    if(mpp<.0001||mpp>1000){toast('That distance gives an unsupported scale. Choose points farther apart.');return;}
    commit(()=>{state.metersPerPixel=mpp;state.calibrated=true;},'Map scale calibrated. All altar boundaries have been updated.');$('calibration-dialog').close();setMode(null);
  };
  $('reset-scale').onclick=()=>{commit(()=>{state.metersPerPixel=DEFAULT_MPP;state.calibrated=false;},'Approximate map scale restored.');$('calibration-dialog').close();setMode(null);};
  $('calibration-dialog').addEventListener('close',()=>{if(mode==='calibrate')setMode(null);});
  $('retry-tiles').onclick=()=>{for(const [key,entry] of tileCache)if(entry.status==='error'){entry.img.remove();tileCache.delete(key);}draw();};
  $('dismiss-instruction').onclick=()=>{$('map-instruction').hidden=true;};
  $('mobile-panel').onclick=()=>{const open=$('sidebar').classList.toggle('open');$('mobile-panel').setAttribute('aria-expanded',String(open));};
  $('planner-nav').onclick=()=>{if(innerWidth<=600){$('sidebar').classList.add('open');$('mobile-panel').setAttribute('aria-expanded','true');}else focusAltar();};
  $('guide-button').onclick=()=>$('guide-dialog').showModal();$('help-button').onclick=()=>$('help-dialog').showModal();
  document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>b.closest('dialog').close());
  document.querySelectorAll('dialog').forEach(d=>d.addEventListener('click',e=>{if(e.target===d){const r=d.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)d.close();}}));
  function planURL() {
    const bytes=new TextEncoder().encode(JSON.stringify(state));let binary='';for(const byte of bytes)binary+=String.fromCharCode(byte);
    return location.href.split('#')[0]+'#plan='+btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
  }
  async function copyLink(url) {try{await navigator.clipboard.writeText(url);toast('Plan link copied. Your altars are ready to share.');return true;}catch{return false;}}
  $('share').onclick=async()=>{const url=planURL();if(!(await copyLink(url))){$('share-link').value=url;$('share-dialog').showModal();$('share-link').select();}};
  $('copy-link').onclick=async()=>{if(await copyLink($('share-link').value))$('share-dialog').close();else{$('share-link').select();toast('Select the link and use your browser’s Copy command.');}};
  function goToLocation(l) {if(!l)return;state.center={x:l.x,y:l.y};state.zoom=14.7;$('search').value=l.name;$('search-results').hidden=true;$('search').setAttribute('aria-expanded','false');$('search').blur();draw();persist();toast(l.name);}
  function search() {
    const q=$('search').value.trim().toLowerCase();searchItems=locations.filter(l=>l.name.toLowerCase().includes(q)).sort((a,b)=>a.name.localeCompare(b.name)).slice(0,10);
    if(!q){searchItems=['Fort Kelvin','Longkeep','The Blue Goblet Tavern','Springlands Ancient Spire','Revelwood Ancient Spire'].map(n=>locations.find(l=>l.name===n)).filter(Boolean);}
    $('search-results').innerHTML=searchItems.length?searchItems.map((l,i)=>`<button data-search-result="${i}">${icon(l.type==='spire'?'pin':'home')}<span>${escapeHTML(l.name)}<small>${l.type==='spire'?'Ancient spire':'Settlement'} · Embervale</small></span></button>`).join(''):'<div class="no-results">No landmarks found. Try “Longkeep” or “Revelwood”.</div>';
    $('search-results').hidden=false;$('search').setAttribute('aria-expanded','true');
  }
  $('search').addEventListener('input',search);$('search').addEventListener('focus',search);
  $('search-results').onclick=e=>{const b=e.target.closest('[data-search-result]');if(b)goToLocation(searchItems[+b.dataset.searchResult]);};
  $('search').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();goToLocation(searchItems[0]);}else if(e.key==='ArrowDown'){e.preventDefault();$('search-results').querySelector('button')?.focus();}else if(e.key==='Escape'){$('search-results').hidden=true;$('search').setAttribute('aria-expanded','false');$('search').blur();}};
  $('search-results').onkeydown=e=>{const b=e.target.closest('[data-search-result]');if(!b)return;const i=+b.dataset.searchResult;if(e.key==='ArrowDown'){e.preventDefault();b.nextElementSibling?.focus();}if(e.key==='ArrowUp'){e.preventDefault();if(i)b.previousElementSibling?.focus();else $('search').focus();}};
  document.addEventListener('pointerdown',e=>{if(!e.target.closest('.search-wrap')){$('search-results').hidden=true;$('search').setAttribute('aria-expanded','false');}});
  document.addEventListener('keydown',e=>{
    if(document.querySelector('dialog[open]'))return;
    if(/INPUT|TEXTAREA|SELECT/.test(e.target.tagName))return;
    if(e.key==='Escape'){setMode(null);$('sidebar').classList.remove('open');$('mobile-panel').setAttribute('aria-expanded','false');return;}
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();$('undo').click();return;}
    if(e.ctrlKey||e.metaKey||e.altKey)return;
    if(e.key.toLowerCase()==='a'){e.preventDefault();setMode('place');}
    if(e.key==='/'){e.preventDefault();$('search').focus();}
    if(e.key==='+'||e.key==='='){e.preventDefault();zoomAt(state.zoom+.6);}
    if(e.key==='-'){e.preventDefault();zoomAt(state.zoom-.6);}
    if(map.contains(document.activeElement)&&selected()&&['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key)){
      e.preventDefault();const delta=(e.shiftKey?10:1)/state.metersPerPixel;
      commit(()=>{const a=selected();a.x=clamp(a.x+(e.key==='ArrowLeft'?-delta:e.key==='ArrowRight'?delta:0),0,MAP_SIZE);a.y=clamp(a.y+(e.key==='ArrowUp'?-delta:e.key==='ArrowDown'?delta:0),0,MAP_SIZE);});
    }
  });
  const observer=new ResizeObserver(entries=>{width=entries[0].contentRect.width;height=entries[0].contentRect.height;draw();});observer.observe(map);
  window.addEventListener('pagehide',()=>{try{localStorage.setItem(STORAGE_KEY,JSON.stringify(state));}catch{}});
  updateControls();draw();persist();if(startMessage)setTimeout(()=>toast(startMessage),800);
})();
