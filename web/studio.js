'use strict';
window.Studio=(()=>{
  const C=()=>window.Creator, roles={music:HarnessText.raw("ui.music"),effect:HarnessText.raw("ui.sound.2"),ambient:HarnessText.raw("ui.ambience"),voice:HarnessText.raw("ui.voice")};
  let mixer=null,timer=null,cancelBalance=null;
  function reset(){if(timer)clearInterval(timer);timer=null;if(mixer){void mixer.dispose();mixer=null;}if(cancelBalance){cancelBalance();cancelBalance=null;}}
  function render(section,box,data){if(section==='soundscape')soundList(box,data);else balanceList(box,data);}
  function soundList(box,data){
    box.append(button(t("ui.add.soundscape"),()=>editSound(null)),button(t("ui.connect.game.audio"),()=>C().request('sound_setup',{})));
    for(const record of data.soundscape){
      const row=C().card(record.name,t("ui.sound.cues",record.cues.length));
      row.append(element('small','',t(record.published_revision===record.revision?HarnessText.raw("ui.game.files.up.to.date"):HarnessText.raw("ui.game.files.need.publishing.2"))));
      for(const cue of record.cues)row.append(element('p','',`${cue.name} · ${t(roles[cue.role])} · ${cue.event}`));
      row.append(button(t("ui.edit"),()=>editSound(record)),button(t("ui.audition.mix"),()=>audition(record)),
        button(t("ui.publish.game.files"),async()=>{if(await C().mutate('creator-sound-publish',{id:record.id,revision:record.revision}))await C().load();}),
        button(t("ui.ask.ai.to.integrate"),()=>C().request('sound_integration',{id:record.id,revision:record.revision})),
        button(t("ui.change.history"),()=>C().history('soundscape_history',record.id)));
      box.append(row);
    }
  }
  async function editSound(record){
    const version=viewVersion, result=await projectApi('assets');if(version!==viewVersion)return;
    const options=result.assets.filter(a=>a.kind==='sound'&&a.status!=='retired').flatMap(a=>a.files.filter(p=>/\.(wav|mp3|ogg|m4a|flac)$/i.test(p)).map(path=>[JSON.stringify([a.id,path]),`${a.name} / ${path}`]));
    const box=C().modal(t("ui.sound.direction")),name=C().field(HarnessText.raw("ui.name"),record?.name||''),duck=C().field(HarnessText.raw("ui.music.level.during.voice"),record?.duck_music??.3,'number');duck.input.min=0;duck.input.max=1;duck.input.step=.05;
    box.append(name.wrap,duck.wrap);const volumes={};for(const [role,label]of Object.entries(roles)){const f=C().field(label,record?.buses[role]??1,'number');f.input.min=0;f.input.max=1;f.input.step=.05;volumes[role]=f;box.append(f.wrap);}
    const values=structuredClone(record?.cues||[]),list=element('div'),editor=element('div');
    function redraw(){list.replaceChildren();for(const [index,cue]of values.entries()){const row=C().card(cue.name,`${cue.key} · ${cue.event}`);row.append(button(t("ui.edit"),()=>cueForm(cue,index)),button(t("ui.remove.cue"),()=>{values.splice(index,1);redraw();}));list.append(row);}}
    function cueForm(cue,index){
      editor.replaceChildren();const controls={key:C().field(HarnessText.raw("ui.cue.key"),cue?.key),name:C().field(HarnessText.raw("ui.name"),cue?.name),event:C().field(HarnessText.raw("ui.when.it.plays"),cue?.event,'textarea'),role:C().select(HarnessText.raw("ui.role"),Object.entries(roles),cue?.role||'effect'),media:C().select(HarnessText.raw("ui.sound.asset"),options,cue?JSON.stringify([cue.asset_id,cue.path]):options[0]?.[0]),loop:C().select(HarnessText.raw("ui.loop"),[['false',HarnessText.raw("ui.off")],['true',HarnessText.raw("ui.on")]],String(cue?.loop||false))};
      const numeric={gain:[HarnessText.raw("ui.volume"),1,0,1,.05],loop_start:[HarnessText.raw("ui.loop.start.seconds"),0,0,86400,.1],loop_end:[HarnessText.raw("ui.loop.end.seconds.file.end"),0,0,86400,.1],fade_in:[HarnessText.raw("ui.fade.in.seconds"),0,0,30,.1],fade_out:[HarnessText.raw("ui.fade.out.seconds"),.2,0,30,.1],priority:[HarnessText.raw("ui.priority"),0,0,100,1],max_voices:[HarnessText.raw("ui.max.simultaneous.voices.per.cue"),1,1,16,1]};
      for(const [key,[label,initial,min,max,step]]of Object.entries(numeric)){controls[key]=C().field(label,cue?.[key]??initial,'number');Object.assign(controls[key].input,{min,max,step});}
      for(const field of Object.values(controls))field.input.required=true;
      C().form(editor,Object.values(controls),HarnessText.raw("ui.apply.cue"),async()=>{
        const value={};for(const [key,field]of Object.entries(controls))value[key]=Object.hasOwn(numeric,key)?Number(field.input.value):field.input.value;
        if(!value.media)throw Error(t("ui.register.a.sound.asset.first"));
        [value.asset_id,value.path]=JSON.parse(value.media);delete value.media;value.loop=value.loop==='true';
        if(index==null)values.push(value);else values[index]=value;editor.replaceChildren();redraw();
      });
    }
    box.append(list,button(t("ui.add.cue"),()=>cueForm(null,null)),editor);
    C().form(box,[],HarnessText.raw("ui.save"),async()=>{
      if(editor.childElementCount)throw Error(t("ui.apply.the.cue.being.edited.first"));
      const value={id:record?.id,name:name.input.value,duck_music:Number(duck.input.value),buses:Object.fromEntries(Object.entries(volumes).map(([k,v])=>[k,Number(v.input.value)])),cues:values};
      if(await C().mutate('creator-sound-save',{values:value,revision:record?.revision})){$('creator-dialog').close();await C().load();}
    });redraw();
  }
  async function audition(record){
    reset();const version=viewVersion;
    const player=GameCreatorAudio.create({resolve:async cue=>{
      if(version!==viewVersion)throw Error(t("ui.request.cancelled"));
      const media=await projectApi('asset-media?id='+encodeURIComponent(cue.asset_id)+'&path='+encodeURIComponent(cue.path));
      return Uint8Array.from(atob(media.data),c=>c.charCodeAt(0)).buffer;
    }});mixer=player;
    try{await player.unlock();const value=await projectApi(`creator-sound?id=${record.id}&revision=${record.revision}`);if(version!==viewVersion||mixer!==player){await player.dispose();return;}
      const box=C().modal(record.name);player.configure(value);const status=element('p');status.setAttribute('role','status');
      box.append(element('p','muted',t("ui.these.volume.changes.affect.audition.only")));
      for(const [role,label]of Object.entries(roles)){const control=C().field(label,value.buses[role],'range');control.input.min=0;control.input.max=1;control.input.step=.01;control.input.oninput=()=>player.setVolume(role,Number(control.input.value));box.append(control.wrap,button(t("ui.stop.role")+' · '+t(label),()=>player.stop(role)));}
      for(const cue of value.cues)box.append(button(cue.name,async()=>{const result=await player.play(cue.key);if(result.status==='skipped')status.textContent=t("ui.skipped.playback.due.to.priority");}));
      box.append(button(t("ui.stop.all"),()=>player.stopAll()),status);
      timer=setInterval(()=>{const s=player.status();status.textContent=t("ui.playing.music.ducking",s.active.length,t(s.ducked?HarnessText.raw("ui.on"):HarnessText.raw("ui.off")));},300);
    }catch(error){if(mixer===player)reset();throw error;}
  }
  function balanceList(box,data){
    box.append(button(t("ui.connect.game.calculations"),()=>C().request('balance_setup',{})));
    for(const record of data.balance){const row=C().card(record.name,`${record.adapter} · v${record.adapter_version}`);
      row.append(button(t("ui.compare.values"),()=>compare(record)),button(t("ui.request.an.ai.edit"),()=>C().request('balance',{id:record.id,revision:record.revision})),button(t("ui.change.history"),()=>C().history('balance_history',record.id)));
      C().details(row,HarnessText.raw("ui.calculation.evidence"),record.evidence);box.append(row);
      for(const saved of data.balance_run.filter(r=>r.balance_id===record.id)){
        const result=C().card(saved.name,saved.updated_at);result.append(button(t("ui.view.comparison"),()=>showResult(saved.balance_revision===record.revision?{parameters:record.parameters,output_metrics:record.outputs,...saved}:saved)),button(t("ui.request.adjustment.from.results"),()=>C().request('balance_run',{id:saved.id,revision:saved.revision})));box.append(result);
      }
    }
  }
  function resultTable(result){
    const table=element('table','gameplay-table'),head=element('tr');const first=result.scenarios[0];const keys=Object.keys(first.outputs);
    head.append(element('th','',t("ui.name")),element('th','',t("ui.input.values")));for(const key of keys)head.append(element('th','',result.output_metrics?.find(m=>m.key===key)?.label||key));table.append(head);
    for(const scenario of result.scenarios){const row=element('tr');row.append(element('td','',scenario.name),element('td','',Object.entries(scenario.inputs).map(([k,v])=>`${result.parameters?.find(p=>p.key===k)?.label||k}: ${v}`).join('\n')));
      for(const key of keys){const status=scenario.checks[key],unit=result.output_metrics?.find(m=>m.key===key)?.unit||'';row.append(element('td','',String(scenario.outputs[key])+(unit?' '+unit:'')+(status?' · '+t({within:HarnessText.raw("ui.within.target"),below:HarnessText.raw("ui.below.target"),above:HarnessText.raw("ui.above.target")}[status]):'')));}table.append(row);}
    return table;
  }
  function showResult(result){const box=C().modal(result.name);box.append(resultTable(result));C().details(box,HarnessText.raw("ui.user.targets"),result.goals);C().details(box,HarnessText.raw("ui.calculation.evidence"),result.evidence);}
  async function compare(record){
    reset();const version=viewVersion,context=await projectApi(`creator-balance?id=${record.id}&revision=${record.revision}`);if(version!==viewVersion)return;
    const preview=await projectApi('preview',{path:record.entry});if(version!==viewVersion)return;
    const box=C().modal(record.name),name=C().field(HarnessText.raw("ui.comparison.name"),record.name),area=element('div'),frames=element('details'),frame=element('iframe','timeline-preview');
    frame.title=t("ui.calculation.preview");frame.sandbox=HarnessText.raw("js.studio.allow.scripts.allow.same.origin");frames.append(element('summary','',t("ui.calculation.preview")),frame);
    box.append(name.wrap,area);let ready=false;frame.onload=()=>{ready=true;};frame.src=preview.url;
    const rows=[],goals={};
    function addScenario(){if(rows.length>=20)return;const row=C().card(t("ui.scenario")),label=C().field(HarnessText.raw("ui.name"),t("ui.scenario.2",rows.length+1)),inputs={};row.append(label.wrap);
      for(const p of record.parameters){const field=C().field(p.label,p.default,'number');Object.assign(field.input,{min:p.min,max:p.max,step:p.step});inputs[p.key]=field;row.append(field.wrap);}
      const entry={row,label,inputs};rows.push(entry);row.append(button(t("ui.remove.row"),()=>{rows.splice(rows.indexOf(entry),1);row.remove();}));area.append(row);
    }
    addScenario();addScenario();box.append(button(t("ui.add.scenario"),addScenario));
    for(const metric of record.outputs){const row=C().card(metric.label,metric.unit),min=C().field(HarnessText.raw("ui.target.minimum"),'','number'),max=C().field(HarnessText.raw("ui.target.maximum"),'','number');min.input.step=max.input.step='any';row.append(min.wrap,max.wrap);goals[metric.key]={min,max};box.append(row);}
    const progress=element('p');progress.setAttribute('role','status');
    C().form(box,[],HarnessText.raw("ui.calculate.and.record"),async()=>{
      if(!ready)throw Error(t("ui.wait.for.the.game.calculation.to.connect"));
      const target={};for(const [key,fields]of Object.entries(goals)){if(fields.min.input.value===''&&fields.max.input.value==='')continue;if(fields.min.input.value===''||fields.max.input.value==='')throw Error(t("ui.enter.both.target.minimum.and.maximum"));target[key]={min:Number(fields.min.input.value),max:Number(fields.max.input.value)};}
      const scenarios=rows.map(r=>({name:r.label.input.value,inputs:Object.fromEntries(Object.entries(r.inputs).map(([key,f])=>[key,Number(f.input.value)]))}));
      progress.textContent=t("ui.calculating.with.the.game.function");
      const calculated=await calculate(frame,preview.url,record,scenarios);if(version!==viewVersion)return;
      const result=await C().mutate('creator-balance-run',{id:record.id,revision:record.revision,fingerprint:context.fingerprint,name:name.input.value,goals:target,scenarios:calculated});
      if(result){await C().load();showResult({parameters:record.parameters,output_metrics:record.outputs,...result});}
    });box.append(progress,frames);
  }
  function calculate(frame,url,definition,scenarios){
    return new Promise((resolve,reject)=>{
      const origin=new URL(url).origin,source=frame.contentWindow,nonce=crypto.randomUUID();
      const cleanup=()=>{clearTimeout(deadline);window.removeEventListener('message',listener);cancelBalance=null;};
      const listener=event=>{if(event.origin!==origin||event.source!==source||event.data?.type!=='creator-balance-result'||event.data.nonce!==nonce)return;cleanup();event.data.error?reject(Error(event.data.error)):resolve(event.data.result);};
      const deadline=setTimeout(()=>{cleanup();frame.removeAttribute('src');reject(Error(t("ui.calculation.timed.out.check.the.game.function")));},15000);
      cancelBalance=()=>{cleanup();reject(Error(t("ui.request.cancelled")));};window.addEventListener('message',listener);
      source.postMessage({type:'creator-balance',nonce,definition,scenarios},origin);
    });
  }
  $('creator-dialog').addEventListener('close',reset);
  return {reset,render};
})();
