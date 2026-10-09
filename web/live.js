'use strict';
window.LiveWorkspace=(()=>{
  const C=()=>window.Creator, pending=new Set();
  let generation=0, status=null, chosen=null, currentPoint=null;
  function leave(){
    document.body.classList.remove('diagram-mode');
    if(!document.body.classList.contains('live-mode'))return;
    document.body.classList.remove('live-mode');
    $('tab-preview').hidden=!document.querySelector('[data-tab="preview"]').classList.contains('active');
  }
  function reset(){generation++;leave();status=null;chosen=null;currentPoint=null;for(const cancel of [...pending])cancel();}
  function rpc(frame,operation,payload={},type='creator-live'){
    const src=frame.getAttribute('src');if(!src)return Promise.reject(Error(t('ui.open.the.game.preview.first')));
    const origin=new URL(src,location.href).origin,source=frame.contentWindow,nonce=crypto.randomUUID(),version=viewVersion;
    return new Promise((resolve,reject)=>{
      const finish=()=>{clearTimeout(timer);window.removeEventListener('message',listener);pending.delete(cancel);};
      const cancel=()=>{finish();reject(Error(t('ui.request.cancelled')));};
      const listener=e=>{if(e.source!==source||e.origin!==origin||e.data?.nonce!==nonce||e.data.type!==type+'-result')return;finish();if(version!==viewVersion)return reject(Error(t('ui.request.cancelled')));e.data.error?reject(Error(e.data.error)):resolve(e.data.result);};
      const timer=setTimeout(()=>{finish();reject(Error(t('ui.game.did.not.respond.reopen.the.preview')));},10000);
      pending.add(cancel);window.addEventListener('message',listener);source.postMessage({type,operation,nonce,...payload},origin);
    });
  }
  const main=(op,data)=>rpc($('preview-frame'),op,data);
  window.addEventListener('message',event=>{
    const frame=$('preview-frame'),src=frame.getAttribute('src');
    if(!src||event.source!==frame.contentWindow||event.origin!==new URL(src,location.href).origin||event.data?.type!=='creator-live-selection')return;
    chosen=event.data.id;
    const select=$('live-target');if(select)select.value=chosen;
    const label=$('live-status');if(label)label.textContent=t('live.selected')+' '+(status?.registry?.targets.find(v=>v.id===chosen)?.name||chosen);
  });
  function render(section,box,data){
    const ticket=++generation,version=viewVersion;
    if(section==='systems'){leave();document.body.classList.add('diagram-mode');return run(async()=>{const result=await projectApi('creator-live-graph'+(currentPoint?'?point='+encodeURIComponent(currentPoint):''));if(ticket===generation&&version===viewVersion&&box.dataset.production==='systems')diagram(box,result);});}
    document.body.classList.remove('diagram-mode');
    document.body.classList.add('live-mode');
    $('tab-preview').hidden=false;
    const toolbar=element('div','live-toolbar');box.append(toolbar);
    toolbar.append(button(t('live.exit'),()=>{leave();document.querySelector('[data-tab="preview"]').click();}),button(t('live.setup'),()=>C().request('live_setup',{})));
    const feedback=element('p','muted');feedback.id='live-status';box.append(feedback);
    const controls=element('div','live-controls');box.append(controls);
    toolbar.append(button(t('ui.refresh'),()=>run(load)));
    async function load(){
      const info=await main('info');if(ticket!==generation||version!==viewVersion||box.dataset.production!=='live')return;
      status=info;controls.replaceChildren();
      if(!info.registry){feedback.textContent=t('live.not_connected');return;}
      const targets=C().select(HarnessText.raw('live.target'),info.registry.targets.map(v=>[v.id,v.name]),info.selected||chosen||info.registry.targets[0]?.id);targets.input.id='live-target';
      chosen=targets.input.value||null;
      targets.input.onchange=()=>run(async()=>{chosen=targets.input.value;await main('select',{target:chosen});});
      feedback.textContent=t(info.recording?'live.recording':'live.idle');
      controls.append(targets.wrap,
        button(t('live.pick'),()=>main('pick').then(()=>{feedback.textContent=t('live.pick_hint');})),
        button(t('live.cancel_pick'),()=>main('cancel')),
        button(t('live.start_record'),async()=>{await main('start');await load();}),
        button(t('live.stop_record'),async()=>{await main('stop');await load();}),
        button(t('live.resume'),async()=>{await main('resume');await load();}));
      const name=C().field(HarnessText.raw('ui.name'));
      C().form(controls,[name],HarnessText.raw('live.capture'),async()=>{
        const target=targets.input.value;await main('select',{target});
        const captured=await main('capture');if(ticket!==generation||version!==viewVersion||box.dataset.production!=='live')return;
        const record=await C().mutate('creator-live-capture',{...captured,name:name.input.value});
        if(!record)return;currentPoint=record.id;await C().load();
      });
      controls.append(element('small','',t('live.record_limit')),element('small','',t(info.pause_supported?'live.can_pause':'live.no_pause')));
    }
    if($('preview-frame').getAttribute('src'))void run(load);
    else feedback.textContent=t('ui.open.the.game.preview.first');
    for(const record of data.live_points||[]){
      const row=C().card(record.name,record.created_at);
      row.append(element('small','',t('live.status.'+record.status)),button(t('live.inspect'),async()=>{
        const point=await projectApi('creator-live-point?id='+encodeURIComponent(record.id));if(version!==viewVersion)return;currentPoint=point.id;
        const modal=C().modal(point.name);C().details(modal,HarnessText.raw('live.observations'),{selected:point.selected,paused:point.paused,events:point.events,snapshot:point.snapshot});
      }),button(t('live.diagram'),()=>{currentPoint=record.id;C().open('systems');}));
      if(record.status==='captured')row.append(button(t('live.branch'),async()=>{if(await C().mutate('creator-live-branch',{id:record.id}))await C().load();}),button(t('live.request'),()=>C().request('live_point',{id:record.id})));
      if(record.status==='comparison')row.append(button(t('live.edit_branch'),()=>C().request('live_variant',{id:record.id})),button(t('live.compare'),()=>compare(record)),button(t('live.keep_original'),async()=>{
        if(confirm(t('live.confirm_original'))&&await C().mutate('creator-live-select',{id:record.id,choice:'original'}))await C().load();
      }));
      box.append(row);
    }
  }
  async function compare(record){
    const version=viewVersion,value=await projectApi('creator-live-preview',{id:record.id});if(version!==viewVersion)return;
    const box=C().modal(t('live.compare')),frames=element('div','live-compare'),notes=element('p','muted'),players=[];
    for(const [key,label]of [['main','live.before'],['alternative','live.after']]){
      const pane=element('section'),frame=element('iframe');frame.title=t(label);frame.setAttribute('sandbox','allow-scripts allow-same-origin allow-pointer-lock');frame.src=value[key];
      pane.append(element('h3','',t(label)),frame);frames.append(pane);players.push(frame);
    }
    box.append(element('p','muted',t('live.compare_help')),frames,notes);
    let restored=false;
    const restore=button(t('live.same_point'),async()=>{
      restore.disabled=true;restored=false;
      try{
        await Promise.all(players.map(frame=>rpc(frame,'pause')));
        await Promise.all(players.map(frame=>rpc(frame,'restore',{snapshot:value.snapshot},'creator-play')));
        await Promise.all(players.map(frame=>rpc(frame,'resume')));
        restored=true;notes.textContent=t('live.restored');
      }finally{restore.disabled=false;}
    });
    box.append(restore,button(t('live.adopt'),async()=>{
      if(!restored)throw Error(t('live.restore_first'));
      if(!confirm(t('live.confirm_adopt')))return;
      const saved=await C().mutate('creator-live-select',{id:record.id,choice:'alternative',alternative_fingerprint:value.alternative_fingerprint});
      if(saved){$('creator-dialog').close();$('preview-frame').src=value.main;await C().load();}
    }));
  }
  function diagram(box,graph){
    box.append(button(t('live.setup'),()=>C().request('live_setup',{})),button(t('ui.close'),leave));
    if(!graph.registry){box.append(element('p','muted',t('live.not_connected')));return;}
    const focus=C().select(HarnessText.raw('live.focus'),graph.nodes.map(n=>[n.id,n.name]),graph.nodes[0]?.id),
      mode=C().select(HarnessText.raw('live.view'),[['near',HarnessText.raw('live.near')],['impact',HarnessText.raw('live.impact')],['all',HarnessText.raw('live.all')]],'near'),
      kind=C().select(HarnessText.raw('live.filter'),[['all',HarnessText.raw('live.all')],['system',HarnessText.raw('live.systems')],['content',HarnessText.raw('live.content')]],'all');
    const filters=element('div','live-filters');filters.append(focus.wrap,mode.wrap,kind.wrap);box.append(filters);
    const zoom=element('div','live-toolbar'),surface=element('div','live-graph'),detail=element('section','live-detail');box.append(zoom,surface,detail);
    const NS='http://www.w3.org/2000/svg';let svg,view,drag=null;
    const el=(tag,attrs={})=>{const e=document.createElementNS(NS,tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);return e;};
    function inspect(item){
      detail.replaceChildren(element('h3','',item.name||item.trigger));
      for(const [label,value]of [[t('live.role'),item.role],[t('live.condition'),item.condition],[t('live.effect'),item.effect],[t('live.reads'),item.reads?.join(', ')],[t('live.writes'),item.writes?.join(', ')]])if(value)detail.append(element('p','',label+': '+value));
      if(item.status)detail.append(element('p','',t(item.status==='planned'?'live.planned':'live.implemented')+' / '+t(item.evidence_current?'live.current':'live.stale')+' / '+t('live.observed_count',item.observed||0)));
      C().details(detail,HarnessText.raw('live.evidence'),{files:item.evidence,records:item.refs});
      detail.append(button(t('live.request'),()=>C().request('live_system',{id:item.id,revision:graph.revision})));
    }
    function draw(){
      const id=focus.input.value,chosen=new Set([id]);
      if(mode.input.value==='all')graph.nodes.forEach(n=>chosen.add(n.id));
      else if(mode.input.value==='near')for(const e of graph.edges)if(e.source===id||e.target===id){chosen.add(e.source);chosen.add(e.target);}
      else {let more=true;while(more){more=false;for(const e of graph.edges)if(chosen.has(e.source)&&!chosen.has(e.target)){chosen.add(e.target);more=true;}}}
      const nodes=graph.nodes.filter(n=>chosen.has(n.id)&&(kind.input.value==='all'||(kind.input.value==='system'?n.kind==='system':n.kind!=='system'))),ids=new Set(nodes.map(n=>n.id));
      const links=graph.edges.filter(e=>ids.has(e.source)&&ids.has(e.target));
      surface.replaceChildren();svg=el('svg',{role:'img','aria-label':t('live.diagram')});surface.append(svg);
      const defs=el('defs'),marker=el('marker',{id:'live-arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:6,markerHeight:6,orient:'auto-start-reverse'});marker.append(el('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'currentColor'}));defs.append(marker);svg.append(defs);
      const positions=new Map(nodes.map((n,i)=>[n.id,{x:50+(i%3)*260,y:50+Math.floor(i/3)*150}]));
      view=[0,0,820,Math.max(260,Math.ceil(nodes.length/3)*150+60)];
      const apply=()=>svg.setAttribute('viewBox',view.join(' '));apply();
      for(const edge of links){
        const a=positions.get(edge.source),b=positions.get(edge.target),group=el('g',{tabindex:0,role:'button','aria-label':edge.trigger});
        const x=a.x+105,y=a.y,tx=b.x+105,ty=b.y,offset=edge.source===edge.target?90:45;
        const path=el('path',{d:edge.source===edge.target?`M ${x} ${y} C ${x+offset} ${y-110} ${x-offset} ${y-110} ${x-15} ${y}`:`M ${x} ${y} Q ${(x+tx)/2+offset} ${(y+ty)/2-55} ${tx} ${ty}`,
          class:'live-edge '+(edge.observed?'observed':edge.status)+(edge.evidence_current?'':' stale'),'marker-end':'url(#live-arrow)'});
        const title=el('title');title.textContent=edge.trigger+' · '+t(edge.status==='planned'?'live.planned':'live.implemented')+' · '+t('live.observed_count',edge.observed);
        const caption=el('text',{x:(x+tx)/2+offset/2,y:(y+ty)/2-30,class:'live-edge-label','text-anchor':'middle'});
        caption.textContent=edge.trigger.length>22?edge.trigger.slice(0,21)+'…':edge.trigger;
        group.append(path,title,caption);group.onclick=()=>inspect(edge);group.onkeydown=e=>{if(e.key==='Enter')inspect(edge);};svg.append(group);
      }
      for(const node of nodes){
        const p=positions.get(node.id),g=el('g',{transform:`translate(${p.x},${p.y})`,tabindex:0,role:'button','aria-label':node.name,class:'live-node'});
        g.append(el('rect',{width:210,height:62,rx:6}));const label=el('text',{x:12,y:26});label.textContent=node.name.length>20?node.name.slice(0,19)+'…':node.name;
        const kind=el('text',{x:12,y:47,class:'live-node-kind'});kind.textContent=t('live.kind.'+node.kind);g.append(label,kind);g.onclick=()=>inspect(node);g.onkeydown=e=>{if(e.key==='Enter')inspect(node);};svg.append(g);
      }
      svg.onwheel=e=>{e.preventDefault();const scale=e.deltaY>0?1.12:.88;view[2]=Math.max(250,Math.min(10000,view[2]*scale));view[3]=Math.max(150,Math.min(10000,view[3]*scale));apply();};
      svg.onpointerdown=e=>{if(e.target===svg){drag={x:e.clientX,y:e.clientY,v:[...view]};svg.setPointerCapture(e.pointerId);}};
      svg.onpointermove=e=>{if(drag){view[0]=drag.v[0]-(e.clientX-drag.x)*view[2]/svg.clientWidth;view[1]=drag.v[1]-(e.clientY-drag.y)*view[3]/svg.clientHeight;apply();}};
      svg.onpointerup=()=>{drag=null;};svg.onpointercancel=()=>{drag=null;};
      zoom.replaceChildren(button(t('live.zoom_in'),()=>{view[2]*=.8;view[3]*=.8;apply();}),button(t('live.zoom_out'),()=>{view[2]*=1.25;view[3]*=1.25;apply();}),button(t('live.reset_view'),draw));
    }
    focus.input.onchange=mode.input.onchange=kind.input.onchange=draw;
    box.append(element('p','muted',t('live.legend')));draw();
  }
  $('preview-live').onclick=()=>C().open('live');
  return {render,reset,leave,rpc};
})();
