'use strict';
(() => {
  if (window.GameCreatorLive) return;
  let registry=null, adapter={}, recording=false, events=[], seq=0, selected=null, picking=false, paused=false;
  const errors={not_connected:HarnessText.raw('live.not_connected'),resume_first:HarnessText.raw('live.resume_first'),pause_pair:HarnessText.raw('live.pause_pair'),invalid_target:HarnessText.raw('live.invalid_target'),invalid_events:HarnessText.raw('live.invalid_events')};
  const error=key=>new Error(errors[key]);
  const copy=value=>JSON.parse(JSON.stringify(value));
  const ready=()=>{if(!registry)throw error('not_connected');};
  const choose=id=>{
    ready();
    if(!registry.targets.some(t=>t.id===id))throw error('invalid_target');
    selected=id;picking=false;
    window.dispatchEvent(new CustomEvent('creator-live-picked',{detail:{id}}));
    return id;
  };
  let consumeClick=false;
  window.addEventListener('click',event=>{if(consumeClick){consumeClick=false;event.preventDefault();event.stopImmediatePropagation();}},true);
  window.addEventListener('pointerdown',event=>{
    consumeClick=false;
    if(!picking||!registry)return;
    consumeClick=true;
    event.preventDefault();event.stopImmediatePropagation();
    let target;
    if(typeof adapter.pick==='function')target=adapter.pick({x:event.clientX,y:event.clientY,width:innerWidth,height:innerHeight});
    if(!target&&event.target?.closest)target=registry.targets.find(t=>t.selector&&event.target.closest(t.selector))?.id;
    if(target)choose(target);
  },true);
  const api=window.GameCreatorLive={
    register(value,options={}){
      if(!value?.revision||!Array.isArray(value.nodes)||!Array.isArray(value.edges)||!Array.isArray(value.targets))throw error('not_connected');
      if(paused)throw error('resume_first');
      if((typeof options.pause==='function')!==(typeof options.resume==='function'))throw error('pause_pair');
      for(const target of value.targets)if(target.selector){try{document.querySelector(target.selector);}catch{throw error('invalid_target');}}
      registry=copy(value);adapter=options;recording=false;events=[];seq=0;selected=null;picking=false;
      return api.info();
    },
    async load(url,options={}){const response=await fetch(url);if(!response.ok)throw error('not_connected');return api.register(await response.json(),options);},
    info(){return {registry:registry?copy(registry):null,recording,paused,selected,picking,pause_supported:typeof adapter.pause==='function',save_supported:!!window.GameCreatorPlay?.info()};},
    start(){ready();events=[];seq=0;recording=true;return api.info();},
    stop(){recording=false;return api.info();},
    pick(){ready();picking=true;return api.info();},
    cancel(){picking=false;return api.info();},
    select:choose,
    emit(edgeId,values={}){
      if(!recording)return;
      ready();if(!registry.edges.some(e=>e.id===edgeId))throw error('invalid_events');
      const encoded=JSON.stringify(values);
      if(!values||Array.isArray(values)||typeof values!=='object'||encoded.length>4000)throw error('invalid_events');
      events.push({edge_id:edgeId,seq:++seq,at:new Date().toISOString(),values:JSON.parse(encoded)});
      if(events.length>120)events.shift();
    },
    async pause(){ready();if(!paused&&typeof adapter.pause==='function'){await adapter.pause();paused=true;}return api.info();},
    async resume(){if(paused){await adapter.resume();paused=false;}return api.info();},
    async capture(){
      ready();if(!selected)throw error('invalid_target');
      await api.pause();
      const snapshot=window.GameCreatorPlay?.info()?await window.GameCreatorPlay.capture():null;
      return {registry_revision:registry.revision,selected,events:copy(events),snapshot,paused,captured_at:new Date().toISOString(),entry:registry.entry};
    }
  };
})();
