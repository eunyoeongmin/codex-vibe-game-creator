'use strict';
window.Production = (() => {
  const C = () => window.Creator;
  let visual = {}, pending = null, ticket = 0, playback = null;
  function reset() { visual = {}; pending = null; ticket++; stopPlayback(); }
  function render(section, box, data) {
    const version = viewVersion, serial = ++ticket;
    return run(async () => {
      if (section === 'visual') renderVisual(box, data);
      if (section === 'timeline') renderTimelines(box, data);
      if (section === 'relations') {
        const result = await projectApi('creator-graph');
        if (version === viewVersion && serial === ticket && box.dataset.production === section) renderRelations(box, result);
      }
    });
  }
  async function importImage(file) {
    if (!file || !file.type.startsWith('image/') || file.size > 12 * 1048576) throw new Error(t("ui.choose.an.image.up.to.mb"));
    const bitmap = await createImageBitmap(file);
    try {
      const canvas = document.createElement('canvas'), scale = Math.min(1, 1920 / bitmap.width);
      canvas.width = Math.round(bitmap.width * scale); canvas.height = Math.round(bitmap.height * scale);
      canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      return {image: canvas.toDataURL('image/png'), size: [canvas.width, canvas.height], captured_at: null, state: null};
    } finally { bitmap.close(); }
  }
  function renderVisual(box, data) {
    box.append(element('p', 'muted', t("ui.drag.on.the.captured.still.image.to.mark")));
    box.append(button(t("ui.capture.screen"), async () => {
      const result = await C().captureImage(); if (result) { visual = {...visual, ...result, regions: []}; pending=null; C().render(); }
    }));
    const upload = C().field(HarnessText.raw("ui.attach.image"), '', 'file'); upload.input.accept = 'image/*';
    upload.input.onchange = () => run(async () => {
      const version = viewVersion, result = await importImage(upload.input.files[0]);
      if (version === viewVersion) { visual = {...visual, ...result, regions: []}; pending=null; C().render(); }
    }); box.append(upload.wrap);
    if (visual.image) {
      const canvas = element('canvas', 'annotation-canvas'); canvas.width = visual.size[0]; canvas.height = visual.size[1];
      canvas.setAttribute('aria-label', t("ui.region.selection.image")); canvas.tabIndex = 0;
      const image = new Image(); image.src = visual.image; const ctx = canvas.getContext('2d');
      function draw(rect) {
        ctx.drawImage(image, 0, 0, canvas.width, canvas.height); ctx.lineWidth = Math.max(2, canvas.width / 400); ctx.strokeStyle = '#ff3c71';
        for (const r of [...(visual.regions || []).map(r => r.rect), ...(rect ? [rect] : [])]) ctx.strokeRect(r[0] * canvas.width, r[1] * canvas.height, r[2] * canvas.width, r[3] * canvas.height);
      }
      image.onload = () => draw();
      const point = event => { const r = canvas.getBoundingClientRect(); return [Math.max(0, Math.min(1, (event.clientX - r.left) / r.width)), Math.max(0, Math.min(1, (event.clientY - r.top) / r.height))]; };
      let start;
      canvas.onpointerdown = event => { start = point(event); canvas.setPointerCapture(event.pointerId); };
      function rectangle(event) { const end = point(event); return [Math.min(start[0], end[0]), Math.min(start[1], end[1]), Math.abs(end[0] - start[0]), Math.abs(end[1] - start[1])]; }
      canvas.onpointermove = event => { if (start) draw(rectangle(event)); };
      canvas.onpointerup = event => {
        if (!start) return; const rect = rectangle(event); start = null;
        if (rect[2] > .003 && rect[3] > .003) { pending = rect; coords.forEach((f, i) => { f.input.value = (rect[i] * 100).toFixed(2); }); }
        draw(pending);
      };
      canvas.onpointercancel = () => { start = null; draw(pending); };
      box.append(canvas);
      const coords = ['X (%)', 'Y (%)', HarnessText.raw("ui.width"), HarnessText.raw("ui.height")].map((label, i) => C().field(label, pending ? (pending[i] * 100).toFixed(2) : i < 2 ? 0 : 10, 'number'));
      coords.forEach(c => { c.input.min = 0; c.input.max = 100; c.input.step = '.01'; });
      const label = C().field(HarnessText.raw("ui.region.description")); label.input.required = true;
      C().form(box, [...coords, label], HarnessText.raw("ui.add.region"), async () => {
        const rect = coords.map(c => Number(c.input.value) / 100);
        if (rect[2] <= 0 || rect[3] <= 0 || rect[0] + rect[2] > 1.00001 || rect[1] + rect[3] > 1.00001) throw new Error(t("ui.keep.the.region.inside.the.image"));
        if ((visual.regions || []).length >= 12) throw new Error(t("ui.select.up.to.regions"));
        visual.regions = [...(visual.regions || []), {rect, label: label.input.value}]; pending = null; C().render();
      });
      for (const [index, region] of (visual.regions || []).entries()) {
        const row = C().card(`${index + 1}. ${region.label}`); row.append(button(t("ui.remove.region"), () => { visual.regions.splice(index, 1); C().render(); })); box.append(row);
      }
      const entry = C().field(HarnessText.raw("ui.html.entry.path"), visual.entry || $('preview-path').value || 'index.html');
      const note = C().field(HarnessText.raw("ui.request"), visual.comment || '', 'textarea'); note.input.required = true;
      note.input.oninput = () => { visual.comment = note.input.value; }; entry.input.oninput = () => { visual.entry = entry.input.value; };
      C().form(box, [entry, note], HarnessText.raw("ui.save.region.request"), async () => {
        if (!visual.regions?.length) throw new Error(t("ui.add.a.region.first"));
        if (await C().mutate('feedback-save', {...visual, entry: entry.input.value, comment: note.input.value, annotations: {size: visual.size, regions: visual.regions}})) {
          visual = {}; pending = null; await C().load();
        }
      });
    }
    for (const record of data.feedback.filter(r => r.annotations && !r.comparison_to)) {
      const row = C().card(record.comment, record.annotations.regions.map((r, i) => `${i + 1}. ${r.label}`).join('\n'));
      row.append(button(t("ui.view.marked.regions"),()=>viewMarked(record)),button(t("ui.send.to.ai"), () => C().request('feedback', {id: record.id})), button(t("ui.add.after.image"), () => afterForm(record)));
      for (const after of data.feedback.filter(r => r.comparison_to === record.id)) row.append(button(t("ui.before.and.after"), () => compare(record, after)));
      box.append(row);
    }
  }
  async function viewMarked(record){
    const version=viewVersion,result=await projectApi('feedback-image?id='+encodeURIComponent(record.id));if(version!==viewVersion)return;
    const box=C().modal(t("ui.view.marked.regions")),canvas=element('canvas','comparison-image'),image=new Image();image.src=result.image;
    image.onload=()=>{canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);ctx.strokeStyle='#ff3c71';ctx.lineWidth=Math.max(2,canvas.width/400);
      for(const r of record.annotations.regions){const[x,y,w,h]=r.rect;ctx.strokeRect(x*canvas.width,y*canvas.height,w*canvas.width,h*canvas.height);}
    };box.append(canvas,element('p','',record.annotations.regions.map((r,i)=>`${i+1}. ${r.label}`).join('\n')));
  }
  function afterForm(before) {
    const box = C().modal(t("ui.add.after.image")), upload = C().field(HarnessText.raw("ui.attach.image"), '', 'file'), note = C().field(HarnessText.raw("ui.play.feedback"), '', 'textarea');
    upload.input.accept = 'image/*'; upload.input.required = note.input.required = true;
    C().form(box, [upload, note], HarnessText.raw("ui.save"), async () => {
      const version=viewVersion;
      const image = await importImage(upload.input.files[0]);
      if(version!==viewVersion)return;
      if (await C().mutate('feedback-save', {...image, entry: before.entry, comparison_to: before.id, comment: note.input.value})) { $('creator-dialog').close(); await C().load(); }
    });
  }
  async function compare(before, after) {
    const version = viewVersion;
    const images = await Promise.all([before, after].map(r => projectApi('feedback-image?id=' + encodeURIComponent(r.id))));
    if (version !== viewVersion) return;
    const box = C().modal(t("ui.before.and.after")), grid = element('div', 'creator-comparison');
    for (const [index, record] of [before, after].entries()) {
      const cell = element('section'), canvas = element('canvas', 'comparison-image'), image = new Image(); image.src = images[index].image;
      image.onload = () => { canvas.width = image.naturalWidth; canvas.height = image.naturalHeight; const ctx = canvas.getContext('2d'); ctx.drawImage(image, 0, 0); ctx.strokeStyle = '#ff3c71'; ctx.lineWidth = Math.max(2, canvas.width / 400);
        for (const region of record.annotations?.regions || []) { const [x,y,w,h] = region.rect; ctx.strokeRect(x*canvas.width,y*canvas.height,w*canvas.width,h*canvas.height); }
      };
      cell.append(element('h3', '', t(index ? HarnessText.raw("ui.after") : HarnessText.raw("ui.before"))), canvas, element('p', '', record.comment)); grid.append(cell);
    }
    box.append(grid);
  }
  function renderRelations(box, graph) {
    const search = C().field(HarnessText.raw("ui.search.items")), list = element('div', 'creator-row-list'); box.append(search.wrap, list);
    if (graph.warnings.length) C().details(box, HarnessText.raw("ui.lookup.notices"), graph.warnings);
    function filter() {
      list.replaceChildren();
      for (const node of graph.nodes.filter(n => n.label.toLowerCase().includes(search.input.value.toLowerCase()))) list.append(button(`${node.kind} · ${node.label}`, () => showRelations(node.id, graph)));
    }
    search.input.oninput = filter; filter();
    if (!graph.nodes.length) box.append(element('p', 'muted', t("ui.no.registered.data.or.records")));
  }
  async function showRelations(id, graph) {
    const version = viewVersion, info = await projectApi('creator-related?id=' + encodeURIComponent(id)); if (version !== viewVersion) return;
    const box = C().modal(info.selected.label), labels = new Map(info.nodes.map(n => [n.id, n.label]));
    C().details(box, HarnessText.raw("ui.selected.item"), info.selected.record);
    box.append(button(t("ui.request.changes.to.this.connection"), () => C().request('relationship', {id, fingerprint: info.fingerprint})), button(t("ui.record.connection.evidence"), () => relationForm(id, graph)));
    box.append(element('h3', '', t("ui.recorded.connections")));
    if (!info.edges.length) box.append(element('p', '', t("ui.no.recorded.connections")));
    for (const edge of info.edges) {
      const relationNames={data_reference:HarnessText.raw("ui.data.reference"),story_link:HarnessText.raw("ui.story.link"),asset_file:HarnessText.raw("ui.used.file"),reference_ids:HarnessText.raw("ui.reference.link"),decision_ids:HarnessText.raw("ui.decision.evidence"),user_decision_ids:HarnessText.raw("ui.user.decision"),timeline_story_id:HarnessText.raw("ui.uses.dialogue"),timeline_asset_id:HarnessText.raw("ui.sequence.asset")};
      const row = C().card(`${labels.get(edge.source) || edge.source} → ${labels.get(edge.target) || edge.target}`, t(relationNames[edge.relation]||edge.relation));
      if (edge.stale || edge.missing) row.append(element('strong', 'creator-error', t("ui.evidence.changed.or.target.missing")));
      if (edge.interpretation) row.append(element('p', '', edge.interpretation));
      C().details(row, HarnessText.raw("ui.source.and.evidence"), edge.evidence);
      if (edge.evidence.path) row.append(button(t("ui.open.evidence.file"), () => openFile(edge.evidence.path, edge.evidence.line)));
      const other = edge.source === id ? edge.target : edge.source;
      if (labels.has(other)) row.append(button(t("ui.view.linked.item"), () => showRelations(other, graph))); box.append(row);
    }
    box.append(element('h3', '', t("ui.occurrences.in.code")),
      element('p', 'muted', t("ui.text.matches.these.do.not.establish.a.functional")));
    for (const occurrence of info.occurrences) {
      box.append(button(`${occurrence.path}:${occurrence.line}`, () => openFile(occurrence.path, occurrence.line)), element('pre', '', occurrence.text));
    }
    box.append(element('small', '', t("ui.files.searched", info.coverage.files)));
    if (info.coverage.truncated) box.append(element('p', '', t("ui.search.limit.reached")));
  }
  async function openFile(path, line = 1) {
    $('creator-dialog').close(); document.querySelector('[data-tab="files"]').click(); await readFile(path);
    const offset = $('editor').value.split('\n').slice(0, line - 1).join('\n').length;
    $('editor').focus(); $('editor').setSelectionRange(offset, offset);
  }
  function relationForm(source, graph) {
    const box = C().modal(t("ui.record.connection.evidence"));
    const target = C().select(HarnessText.raw("ui.linked.item"), graph.nodes.map(n => [n.id, n.label]), graph.nodes[0]?.id), relation = C().field(HarnessText.raw("ui.relationship")),
      path = C().field(HarnessText.raw("ui.evidence.file.path")), line = C().field(HarnessText.raw("ui.evidence.starting.line"), 1, 'number'), quote = C().field(HarnessText.raw("ui.exact.evidence.quote"), '', 'textarea'), interpretation = C().field(HarnessText.raw("ui.interpretation"), '', 'textarea');
    for (const control of [relation, path, line, quote, interpretation]) control.input.required = true;
    line.input.min = 1;
    C().form(box, [target, relation, path, line, quote, interpretation], HarnessText.raw("ui.save"), async () => {
      if (await C().mutate('creator-relation-save', {values: {source, target: target.input.value, relation: relation.input.value, interpretation: interpretation.input.value, user_note: interpretation.input.value,
        evidence: {path: path.input.value, line: Number(line.input.value), quote: quote.input.value}}})) { $('creator-dialog').close(); await C().load(); }
    });
  }
  const kinds = {dialogue:HarnessText.raw("ui.dialogue"), move:HarnessText.raw("ui.move"), sound:HarnessText.raw("ui.sound.2"), image:HarnessText.raw("ui.image"), transition:HarnessText.raw("ui.transition"), wait:HarnessText.raw("ui.wait")};
  function renderTimelines(box, data) {
    box.append(button(t("ui.add.timeline"), () => editTimeline(null, data)));
    for (const record of data.timeline) {
      const duration = record.steps.reduce((sum, step) => sum + step.delay + step.duration, 0);
      const row = C().card(record.name, t("ui.steps.s", record.steps.length, duration.toFixed(2)));
      row.append(element('small', '', t(record.published_revision === record.revision ? HarnessText.raw("ui.current.version.published.to.game.files") : HarnessText.raw("ui.game.files.need.publishing"))));
      row.append(button(t("ui.edit"), () => editTimeline(record, data)), button(t("ui.play.in.game"), () => play(record)), button(t("ui.stop.playback"), stopPlayback),
        button(t("ui.publish.game.files"), async () => { if (await C().mutate('creator-timeline-publish', {id: record.id, revision: record.revision})) await C().load(); }),
        button(t("ui.ask.ai.to.integrate"), () => C().request('timeline_integration', {id: record.id, revision: record.revision})),
        button(t("ui.request.an.ai.edit"), () => C().request('timeline', {id: record.id, revision: record.revision})),
        button(t("ui.change.history"), () => C().history('timeline_history', record.id)));
      box.append(row);
    }
    const status = element('p'); status.id = 'timeline-play-status'; status.setAttribute('role', 'status'); box.append(status);
  }
  async function editTimeline(record, data) {
    const version = viewVersion;
    const [assetResult,targetResult] = await Promise.all([projectApi('assets'),projectApi('creator-timeline-targets?path='+encodeURIComponent($('preview-path').value||'index.html'))]);
    const assets=assetResult.assets; if (version !== viewVersion) return;
    const draft = record ? JSON.parse(JSON.stringify(record)) : {name:'', steps:[]};
    const box = C().modal(t("ui.sequence.timeline")), name = C().field(HarnessText.raw("ui.name"), draft.name), steps = element('div'), bar = element('div', 'timeline-track');
    name.input.required = true; box.append(name.wrap, bar, steps);
    function redraw() {
      steps.replaceChildren(); bar.replaceChildren(); let at = 0;
      for (const [index, step] of draft.steps.entries()) {
        const block = element('span', 'timeline-block', `${at.toFixed(1)}s ${t(kinds[step.kind])}`); bar.append(block); at += step.delay + step.duration;
        const row = C().card(`${index + 1}. ${t(kinds[step.kind])}`, t("ui.delay.s.duration.s", step.delay, step.duration));
        if (step.target) row.append(element('small','',step.target));
        row.append(button(t("ui.edit"), () => stepForm(step, value => { draft.steps[index] = value; redraw(); })),
          button(t("ui.move.up"), () => { if (index) { [draft.steps[index-1],draft.steps[index]] = [draft.steps[index],draft.steps[index-1]]; redraw(); } }),
          button(t("ui.move.down"), () => { if (index < draft.steps.length-1) { [draft.steps[index+1],draft.steps[index]] = [draft.steps[index],draft.steps[index+1]]; redraw(); } }),
          button(t("ui.remove.step"), () => { draft.steps.splice(index,1); redraw(); })); steps.append(row);
      }
    }
    const editor = element('div'); box.append(button(t("ui.add.step"), () => stepForm(null, value => { draft.steps.push(value); redraw(); })), editor);
    function stepForm(previous, save) {
      editor.replaceChildren();
      const kind = C().select(HarnessText.raw("ui.action"), Object.entries(kinds), previous?.kind || 'wait'), delay = C().field(HarnessText.raw("ui.delay.before.s"),previous?.delay ?? 0,'number'), duration = C().field(HarnessText.raw("ui.duration.s"),previous?.duration ?? 1,'number');
      delay.input.min=0; duration.input.min=.05; delay.input.step=duration.input.step='.05';
      const dynamic = element('div'); editor.append(kind.wrap); let fields = {};
      function parameters() {
        dynamic.replaceChildren(); fields={}; const type=kind.input.value;
        if(type==='move') {
          fields={target:C().field(HarnessText.raw("ui.movement.target"),previous?.target || ''),x:C().field(HarnessText.raw("ui.horizontal.movement.px"),previous?.x ?? 0,'number'),y:C().field(HarnessText.raw("ui.vertical.movement.px"),previous?.y ?? 0,'number')};
          const suggestions=element('datalist');suggestions.id='timeline-target-suggestions';
          for(const item of targetResult.targets){const option=element('option','',item.label);option.value=item.id;suggestions.append(option);}
          fields.target.input.setAttribute('list',suggestions.id);fields.target.wrap.append(suggestions);
          fields.target.input.placeholder=t("ui.choose.a.registered.target.or.enter.a.name");
        }
        if(type==='transition') fields={color:C().field(HarnessText.raw("ui.transition.color"),previous?.color || '#000000','color')};
        if(type==='dialogue') fields={story_id:C().select(HarnessText.raw("ui.confirmed.story"),data.story.filter(s=>s.status==="confirmed").map(s=>[s.id,s.title]),previous?.story_id),excerpt:C().field(HarnessText.raw("ui.dialogue.excerpt.exact.source.text"),previous?.excerpt || '', 'textarea')};
        if(type==='sound'||type==='image') {
          const choices=assets.filter(a=>a.kind===(type==='sound'?'sound':'image')&&a.status!=='retired').flatMap(a=>a.files.map(path=>[JSON.stringify([a.id,path]),`${a.name} / ${path}`]));
          fields={media:C().select(HarnessText.raw("ui.asset.to.use"),choices,previous?.asset_id?JSON.stringify([previous.asset_id,previous.asset_path]):choices[0]?.[0])};
        }
        for(const [key,control] of Object.entries(fields)) { control.input.required=key!=='excerpt'; dynamic.append(control.wrap); }
      }
      kind.input.onchange=parameters; parameters(); editor.append(dynamic);
      C().form(editor,[delay,duration],HarnessText.raw("ui.apply.step"),async()=>{
        const value={id:previous?.id || 'STEP-'+crypto.randomUUID(),kind:kind.input.value,delay:Number(delay.input.value),duration:Number(duration.input.value)};
        for(const [key,control] of Object.entries(fields)) value[key]=['x','y'].includes(key)?Number(control.input.value):control.input.value;
        if(value.media) { [value.asset_id,value.asset_path]=JSON.parse(value.media); delete value.media; }
        if((value.kind==='dialogue'&&!value.story_id)||(['image','sound'].includes(value.kind)&&!value.asset_id)) throw new Error(t("ui.register.the.story.or.asset.first"));
        save(value);editor.replaceChildren();
      });
    }
    C().form(box,[],HarnessText.raw("ui.save.timeline"),async()=>{
      if(editor.childElementCount) throw new Error(t("ui.apply.the.step.being.edited.first"));
      if (await C().mutate('creator-timeline-save',{values:{...draft,name:name.input.value},revision:record?.revision})) { $('creator-dialog').close(); await C().load(); }
    }); redraw();
  }
  function stopPlayback() {
    if(playback) { try{playback.source.postMessage({type:'creator-timeline-stop',nonce:playback.nonce},playback.origin);}catch(_){} clearTimeout(playback.timer); window.removeEventListener('message',playback.listener); playback=null; }
    const status=$('timeline-play-status'); if(status) status.textContent=t("ui.playback.stopped");
  }
  async function play(record) {
    const version=viewVersion, sequence=await projectApi(`creator-timeline?id=${encodeURIComponent(record.id)}&revision=${record.revision}`); if(version!==viewVersion)return;
    stopPlayback();
    const preview=await projectApi('preview',{path:$('preview-path').value||'index.html'}); if(version!==viewVersion)return;
    const box=C().modal(record.name), frame=element('iframe','timeline-preview'), status=element('p'); status.setAttribute('role','status');
    frame.title=t("ui.sequence.preview"); frame.sandbox=HarnessText.raw("js.creator.allow.scripts.allow.same.origin.allow.pointer.lock"); frame.allow='autoplay'; frame.allowFullscreen=true;
    const start=button(t("ui.play"),()=>startPlayback()); start.disabled=true;
    frame.onload=()=>{start.disabled=false;}; box.append(start,button(t("ui.stop.playback"),stopPlayback),status,frame);frame.src=preview.url;
    function startPlayback(){
    stopPlayback();
    const origin=new URL(preview.url).origin, source=frame.contentWindow, nonce=crypto.randomUUID();
    status.textContent=t("ui.connecting.playback");
    const listener=event=>{
      if(event.origin!==origin||event.source!==source||event.data?.type!=='creator-timeline-event'||event.data.nonce!==nonce)return;
      clearTimeout(playback?.timer);
      status.textContent=event.data.status==='error'?String(event.data.error):['finished','stopped'].includes(event.data.status)?t(event.data.status==='finished'?HarnessText.raw("ui.playback.complete"):HarnessText.raw("ui.playback.stopped")):t("ui.playing.step",event.data.index+1);
      if(['error','finished','stopped'].includes(event.data.status)){window.removeEventListener('message',listener);playback=null;}
    };
    const timer=setTimeout(()=>{ stopPlayback();status.textContent=t("ui.playback.did.not.respond.reopen.the.preview"); },(sequence.steps[0]?.delay||0)*1000+5000);
    playback={origin,source,nonce,listener,timer};window.addEventListener('message',listener);
    source.postMessage({type:'creator-timeline-play',nonce,timeline:sequence},origin);
    }
  }
  $('creator-dialog').addEventListener('close',stopPlayback);
  return {reset,render};
})();
