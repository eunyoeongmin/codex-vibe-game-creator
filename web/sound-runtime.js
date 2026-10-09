'use strict';
(() => {
  if (window.GameCreatorAudio) return;
  function create(options={}) {
    let ctx=null, config=null, generation=0, voices=[], cache=new Map(), master=null, buses={}, duck=null;
    const levels={music:1,effect:1,ambient:1,voice:1}, epochs={music:0,effect:0,ambient:0,voice:0};
    const ramp=(gain,value,duration)=>{ const now=ctx.currentTime; gain.cancelScheduledValues(now);gain.setValueAtTime(gain.value,now);gain.linearRampToValueAtTime(value,now+duration); };
    function updateDuck() { if(duck)ramp(duck.gain,voices.some(v=>v.role==='voice')?(config?.duck_music??.3):1,.08); }
    async function unlock() {
      if(!ctx){const Audio=window.AudioContext||window.webkitAudioContext;if(!Audio)throw Error(HarnessText.raw("js.sound.runtime.web.audio.is.unavailable"));ctx=new Audio();master=ctx.createGain();master.connect(ctx.destination);
        duck=ctx.createGain();duck.connect(master);
        for(const role of Object.keys(levels)){const gain=ctx.createGain();gain.gain.value=levels[role];gain.connect(role==='music'?duck:master);buses[role]=gain;}
      }
      await ctx.resume();if(ctx.state!=='running')throw Error(HarnessText.raw("js.sound.runtime.press.play.to.enable.browser.audio"));
    }
    function finish(voice){if(voice.finished)return;voice.finished=true;voices=voices.filter(v=>v!==voice);voice.source.disconnect();voice.gain.disconnect();updateDuck();}
    function halt(voice,duration=0){if(voice.finished)return;voice.stopping=true;ramp(voice.gain.gain,0,duration);try{voice.source.stop(ctx.currentTime+duration);}catch(_){}if(!duration)finish(voice);}
    function stop(role){if(role&&!Object.hasOwn(levels,role))throw Error(HarnessText.raw("js.sound.runtime.unknown.audio.role"));for(const key of Object.keys(epochs))if(!role||key===role)epochs[key]++;
      for(const voice of [...voices])if(!role||voice.role===role)halt(voice,voice.fade_out);}
    function stopAll(){generation++;for(const voice of [...voices])halt(voice);}
    function configure(value,{baseURL=location.href}={}){
      if(!value||!Array.isArray(value.cues))throw Error(HarnessText.raw("js.sound.runtime.soundscape.cues.required"));stopAll();config=structuredClone(value);config.baseURL=String(baseURL);cache.clear();
      for(const role of Object.keys(levels))setVolume(role,value.buses?.[role]??1);
      updateDuck();
    }
    function setVolume(role,value){if(!Object.hasOwn(levels,role)||!Number.isFinite(value)||value<0||value>1)throw Error(HarnessText.raw("js.sound.runtime.volume.must.be.between.and"));levels[role]=value;if(buses[role])ramp(buses[role].gain,value,.04);}
    async function buffer(cue){
      const key=cue.path+':'+cue.sha256;
      if(!cache.has(key))cache.set(key,(async()=>{
        let raw;
        if(options.resolve)raw=await options.resolve(cue);
        else {const url=new URL(cue.path,config.baseURL),base=new URL(config.baseURL);if(url.origin!==base.origin)throw Error(HarnessText.raw("js.sound.runtime.audio.must.belong.to.this.game"));
          const response=await fetch(url);if(!response.ok)throw Error(HarnessText.raw("js.sound.runtime.audio.file.could.not.be.loaded")+cue.path);raw=await response.arrayBuffer();}
        return ctx.decodeAudioData(raw.slice(0));
      })().catch(e=>{cache.delete(key);throw e;}));
      return cache.get(key);
    }
    async function play(key){
      if(!config)throw Error(HarnessText.raw("js.sound.runtime.load.a.soundscape.first"));const cue=config.cues.find(c=>c.key===key);if(!cue)throw Error(HarnessText.raw("js.sound.runtime.unknown.sound.cue")+key);
      const ticket=generation, epoch=epochs[cue.role];await unlock();let audio;
      try{audio=await buffer(cue);}catch(error){if(ticket!==generation)return {status:'cancelled'};throw error;}
      if(ticket!==generation||epoch!==epochs[cue.role])return {status:'cancelled'};
      const end=cue.loop_end||audio.duration;
      if(cue.loop&&(cue.loop_start>=end||end>audio.duration+.001))throw Error(HarnessText.raw("js.sound.runtime.loop.range.is.outside.this.audio.file"));
      const same=voices.filter(v=>v.key===key&&!v.stopping);
      if(same.length>=cue.max_voices){const oldest=same[0];halt(oldest,0);}
      if(voices.length>=64){const lowest=[...voices].sort((a,b)=>a.priority-b.priority)[0];if(lowest.priority>cue.priority)return {status:'skipped',reason:'priority'};halt(lowest,0);}
      const source=ctx.createBufferSource(),gain=ctx.createGain();source.buffer=audio;source.loop=cue.loop;source.loopStart=cue.loop_start;source.loopEnd=end;
      gain.gain.value=cue.fade_in?0:cue.gain;source.connect(gain);gain.connect(buses[cue.role]);
      if(cue.role==='music')for(const old of [...voices])if(old.role==='music')halt(old,old.fade_out);
      const voice={key,role:cue.role,priority:cue.priority,fade_out:cue.fade_out,source,gain,finished:false,stopping:false};
      voices.push(voice);source.onended=()=>finish(voice);source.start();if(cue.fade_in)ramp(gain.gain,cue.gain,cue.fade_in);updateDuck();
      return {status:'playing',key,duration:audio.duration};
    }
    async function load(url,options={}){const response=await fetch(url);if(!response.ok)throw Error(HarnessText.raw("js.sound.runtime.cannot.load.soundscape"));configure(await response.json(),options);}
    function status(){return {active:voices.map(v=>({key:v.key,role:v.role,stopping:v.stopping})),volumes:{...levels},ducked:voices.some(v=>v.role==='voice'),state:ctx?.state||'not_started'};}
    async function dispose(){stopAll();cache.clear();if(ctx)await ctx.close();ctx=null;master=null;duck=null;buses={};}
    return {unlock,configure,load,play,stop,stopAll,setVolume,status,dispose};
  }
  window.GameCreatorAudio={create};
})();
