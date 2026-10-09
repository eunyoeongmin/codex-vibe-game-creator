'use strict';
window.Gameplay = (() => {
  const C = () => window.Creator;
  let pending = new Set();
  function reset() { for (const cancel of [...pending]) cancel(); }
  function previewEntry() {
    const src=$('preview-frame').getAttribute('src');
    if(!src)throw new Error(t("ui.open.the.game.preview.first"));
    return decodeURIComponent(new URL(src,location.href).pathname).replace(/^\//,'');
  }
  function bridge(operation, payload = {}) {
    const frame = $('preview-frame'), src = frame.getAttribute('src');
    if (!src) return Promise.reject(new Error(t("ui.open.the.game.preview.first")));
    const origin = new URL(src, location.href).origin, source = frame.contentWindow, nonce = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      const cleanup = () => { clearTimeout(timer); window.removeEventListener('message', listener); pending.delete(cancel); };
      const cancel = () => { cleanup(); reject(new Error(t("ui.request.cancelled"))); };
      const listener = event => {
        if (event.origin !== origin || event.source !== source || event.data?.type !== 'creator-play-result' || event.data.nonce !== nonce) return;
        cleanup(); event.data.error ? reject(new Error(event.data.error)) : resolve(event.data.result);
      };
      const timer = setTimeout(() => { cleanup(); reject(new Error(t("ui.game.did.not.respond.reopen.the.preview"))); }, 15000);
      pending.add(cancel); window.addEventListener('message', listener);
      source.postMessage({type:'creator-play', operation, nonce, ...payload}, origin);
    });
  }
  async function render(section, box, data) {
    if (section === 'saves') return saves(box, data);
    if (section === 'languages') return languages(box, data);
    return designs(section, box, data);
  }
  function saves(box, data) {
    box.append(button(t("ui.connect.game.saves"), () => C().request('play_setup', {})));
    const name = C().field(HarnessText.raw("ui.name")), kind = C().select(HarnessText.raw("ui.type.2"), [['slot',HarnessText.raw("ui.play.slot")],['point',HarnessText.raw("ui.play.point")]], 'slot');
    C().form(box, [name, kind], HarnessText.raw("ui.save.current.play"), async () => {
      const version = viewVersion, entry = previewEntry(), state = await bridge('capture');
      if (version !== viewVersion) return;
      if (await C().mutate('creator-play-save', {name:name.input.value, kind:kind.input.value, entry, snapshot:state})) await C().load();
    });
    for (const record of data.play_save) {
      const row = C().card(record.name, `${t({slot:HarnessText.raw("ui.play.slot"),point:HarnessText.raw("ui.play.point"),backup:HarnessText.raw("ui.before.restore"),migration:HarnessText.raw("ui.migrated.save")}[record.kind])} · v${record.version} · ${record.updated_at}`);
      row.append(element('small','',record.entry), button(t("ui.load"), async () => {
        if (!confirm(t("ui.preserve.current.play.and.load.this.point"))) return;
        const version = viewVersion, saved = await projectApi('creator-play-get?id='+encodeURIComponent(record.id));
        if (version !== viewVersion) return;
        const entry = previewEntry();
        if (entry !== saved.entry) throw new Error(t("ui.open.this.save.s.game.entry.in.the"));
        const currentState = await bridge('capture'); if (version !== viewVersion) return;
        if (currentState.adapter !== saved.snapshot.adapter) throw new Error(t("ui.this.save.belongs.to.another.game"));
        if (!await C().mutate('creator-play-save', {name:t("ui.before.restore"),kind:'backup',entry,snapshot:currentState})) return;
        const converted = await bridge('migrate', {snapshot:saved.snapshot}); if (version !== viewVersion) return;
        if (converted.version !== saved.snapshot.version) {
          if (!await C().mutate('creator-play-save', {name:saved.name,kind:'migration',entry,snapshot:converted,parent_id:saved.id})) return;
        }
        await bridge('restore', {snapshot:converted}); if (version !== viewVersion) return;
        await C().load(); $('creator-status').textContent=t("ui.play.loaded");
      }));
      box.append(row);
    }
  }
  function languages(box, data) {
    box.append(button(t("ui.connect.game.strings"), () => C().request('localization_setup', {})));
    for (const record of data.localization) {
      const row = C().card(record.name, record.path);
      row.append(button(t("ui.edit.translations"), () => editLanguage(record)), button(t("ui.request.an.ai.edit"), () => C().request('localization', {id:record.id,revision:record.revision})), button(t("ui.change.history"), () => C().history('localization_edit',record.id)));
      box.append(row);
    }
  }
  async function editLanguage(record) {
    const version=viewVersion, info=await projectApi('creator-localization?id='+encodeURIComponent(record.id)); if(version!==viewVersion)return;
    const box=C().modal(record.name), language=C().select(HarnessText.raw("ui.language"),Object.keys(info.messages).map(v=>[v,v]),record.base_locale), search=C().field(HarnessText.raw("ui.search.strings")), editor=element('div');
    const messages=structuredClone(info.messages); let controls=[];
    const flush=()=>{for(const [key,input] of controls) messages[language.input.dataset.previous][key]=input.value;};
    const redraw=()=>{
      controls=[]; editor.replaceChildren(); language.input.dataset.previous=language.input.value;
      for(const [key,original] of Object.entries(messages[record.base_locale]).filter(([k,v])=>(k+' '+v).toLowerCase().includes(search.input.value.toLowerCase()))) {
        const input=C().field(key,messages[language.input.value][key]||'','textarea'); controls.push([key,input.input]);
        input.wrap.append(element('small','',original)); editor.append(input.wrap);
      }
    };
    language.input.onchange=()=>{flush();redraw();}; search.input.oninput=()=>{flush();redraw();};
    box.append(language.wrap,search.wrap);
    const newLanguage=C().field(HarnessText.raw("ui.language.code.to.add"));
    C().form(box,[newLanguage],HarnessText.raw("ui.add.language"),async()=>{
      flush(); const locale=newLanguage.input.value.trim();
      if(!/^[A-Za-z][A-Za-z0-9-]{0,34}$/.test(locale)||messages[locale])throw new Error(t("ui.enter.a.new.language.code"));
      messages[locale]={};const option=element('option','',locale);option.value=locale;language.input.append(option);language.input.value=locale;redraw();
    });
    const issues=element('div');
    for(const issue of info.issues) issues.append(element('p','creator-error',`${issue.locale} / ${issue.key}: ${t(issue.type==='missing'?HarnessText.raw("ui.missing.translation"):HarnessText.raw("ui.variable.mismatch"))}`));
    box.append(issues,editor);
    C().form(box,[],HarnessText.raw("ui.save"),async()=>{
      flush(); if(await C().mutate('creator-localization-save',{id:record.id,revision:record.revision,digest:info.digest,messages})) await editLanguage(record);
    });
    box.append(button(t("ui.apply.preview.language"),async()=>{ await bridge('language',{locale:language.input.value}); }),button(t("ui.check.text.overflow"),async()=>{
      const observed=await bridge('strings');if(version!==viewVersion)return;
      issues.replaceChildren(element('p','muted',t("ui.checks.visible.dom.text.on.the.current.screen")));
      for(const issue of observed.issues) issues.append(element('p','creator-error',`${issue.locale} / ${issue.key}: ${t("ui.text.overflow")}`));
      if(!observed.issues.length)issues.append(element('p','',t("ui.no.text.overflow.on.this.screen")));
    })); redraw();
  }
  const labels={experiment:HarnessText.raw("ui.play.comparison"),integration:HarnessText.raw("ui.system.integration.design"),content_plan:HarnessText.raw("ui.content.progression")};
  const rowFields={experiment:['name','change'],integration:['action','state_change','existing_connection','unresolved'],content_plan:['name','situation','player_action','reuse','outcome']};
  const fieldLabels={name:HarnessText.raw("ui.name"),change:HarnessText.raw("ui.change"),action:HarnessText.raw("ui.player.action"),state_change:HarnessText.raw("ui.state.change"),existing_connection:HarnessText.raw("ui.existing.connection"),unresolved:HarnessText.raw("ui.open.choices"),situation:HarnessText.raw("ui.new.situation"),player_action:HarnessText.raw("ui.different.action.or.choice"),reuse:HarnessText.raw("ui.reuse.prior.learning"),outcome:HarnessText.raw("ui.outcome")};
  function designs(kind,box,data) {
    box.append(button(t("ui.request.design"),()=>C().request(kind+'_setup',{})),button(t("ui.write.manually"),()=>designForm(kind,null)));
    for(const record of data[kind]) {
      const row=C().card(record.name,record.hypothesis);row.append(element('small','',t(record.status==="proposed"?HarnessText.raw("ui.proposed"):record.status==='implemented'?HarnessText.raw("ui.implementation.recorded"):HarnessText.raw("ui.user.selected"))));
      const table=element('table','gameplay-table'), head=element('tr'); for(const field of rowFields[kind])head.append(element('th','',t(fieldLabels[field])));table.append(head);
      for(const item of record[{experiment:'candidates',integration:'flow',content_plan:'units'}[kind]]){const tr=element('tr');for(const field of rowFields[kind])tr.append(element('td','',item[field]));table.append(tr);}row.append(table);
      row.append(button(t("ui.expand.table"),()=>{const detail=C().modal(record.name);detail.append(element('p','',record.hypothesis),table.cloneNode(true));}));
      if(kind==='content_plan') {
        row.append(element('p','',t("ui.units",record.units.length,record.target_count)));
        if(record.repeated_rows.length)row.append(element('p','creator-error',t("ui.identical.rows",record.repeated_rows.join(', '))));
      }
      if(kind==='experiment') {
        row.append(element('p','',t("ui.observation.criteria")+': '+record.observation),element('p','',t("ui.keep.unchanged")+': '+record.invariants));
        if(!record.variants)row.append(button(t("ui.create.candidate.folders"),async()=>{if(await C().mutate('creator-experiment-build',{id:record.id,revision:record.revision}))await C().load();}));
        for(const id of record.variants||[]) {
          const candidate=data.variant.find(v=>v.id===id); if(!candidate)continue;
          const item=C().card(candidate.name,candidate.hypothesis);
        item.append(button(t("ui.build.this.candidate"),()=>C().request('variant',{id},candidate.name)),button(t("ui.open.2"),async()=>{const opened=await projectApi('variant-preview',{id}); const link=element('a','',t("ui.open.candidate"));link.href=opened.alternative;link.target='_blank';link.rel='noopener';item.append(link);link.click();}));
          if(record.status==="proposed")item.append(button(t("ui.select.this.candidate"),()=>choose(kind,record,id)));row.append(item);
        }
      }
      if(record.status==="proposed") {
        if(!record.variants)row.append(button(t("ui.edit"),()=>designForm(kind,record)));
        if(kind!=='experiment')row.append(button(t("ui.approve.design"),()=>choose(kind,record)));
      }
      row.append(button(t("ui.request.an.ai.edit"),()=>C().request(kind,{id:record.id,revision:record.revision})),button(t("ui.change.history"),()=>C().history(kind+'_history',record.id)));
      if(record.status==='approved'&&kind!=='experiment')row.append(button(t("ui.implement.approved.design"),()=>C().request(kind,{id:record.id,revision:record.revision})));
      if(record.implementation)C().details(row,HarnessText.raw("ui.implementation.evidence"),record.implementation);
      box.append(row);
    }
  }
  function choose(kind,record,chosen) {
    const box=C().modal(t(kind==='experiment'?HarnessText.raw("ui.select.this.candidate"):HarnessText.raw("ui.approve.design"))), reason=C().field(HarnessText.raw("ui.selection.reason"),'','textarea'); reason.input.required=true;
    if(kind==='experiment')box.append(element('p','',t("ui.the.selected.candidate.replaces.the.main.game.previous")));
    C().form(box,[reason],HarnessText.raw("ui.confirm.selection"),async()=>{
      if(await C().mutate('creator-design-approve',{kind,id:record.id,revision:record.revision,chosen,user_quote:reason.input.value})){$('creator-dialog').close();await C().load();}
    });
  }
  async function designForm(kind,record) {
    const version=viewVersion, graph=kind==='integration'?await projectApi('creator-graph'):null;if(version!==viewVersion)return;
    const box=C().modal(t(labels[kind])), controls={name:C().field(HarnessText.raw("ui.name"),record?.name),user_quote:C().field(HarnessText.raw("ui.original.user.statement"),record?.user_quote,'textarea'),hypothesis:C().field(HarnessText.raw("ui.design.hypothesis"),record?.hypothesis,'textarea')};
    if(kind==='experiment')Object.assign(controls,{entry:C().field(HarnessText.raw("ui.game.entry.path"),record?.entry||$('preview-path').value||'index.html'),variable:C().field(HarnessText.raw("ui.variable.to.compare"),record?.variable),invariants:C().field(HarnessText.raw("ui.keep.unchanged"),record?.invariants,'textarea'),observation:C().field(HarnessText.raw("ui.observation.criteria"),record?.observation,'textarea')});
    if(kind==='content_plan'){controls.target_count=C().field(HarnessText.raw("ui.target.count"),record?.target_count||1,'number');controls.target_count.input.min=1;controls.target_count.input.max=200;}
    for(const control of Object.values(controls)){control.input.required=true;box.append(control.wrap);}
    const nodeControls=[];
    if(graph)for(const node of graph.nodes){const label=element('label','creator-field'),input=element('input');input.type='checkbox';input.checked=record?.node_ids.includes(node.id)||false;label.append(input,document.createTextNode(node.label));box.append(label);nodeControls.push([node.id,input]);}
    const key={experiment:'candidates',integration:'flow',content_plan:'units'}[kind], values=structuredClone(record?.[key]||[]), area=element('div');let rows=[];
    function redraw(){area.replaceChildren();rows=[];for(const [index,row] of values.entries()){
      const item=C().card(String(index+1)), inputs={};for(const field of rowFields[kind]){inputs[field]=C().field(fieldLabels[field],row[field]||'','textarea');inputs[field].input.required=true;item.append(inputs[field].wrap);}
      rows.push(inputs);item.append(button(t("ui.remove.row"),()=>{flush();values.splice(index,1);redraw();}));area.append(item);
    }}
    function flush(){rows.forEach((row,index)=>{for(const [field,control]of Object.entries(row))values[index][field]=control.input.value;});}
    box.append(area,button(t("ui.add.row"),()=>{flush();values.push({});redraw();}));
    C().form(box,[],HarnessText.raw("ui.save"),async()=>{
      flush();const value={id:record?.id,...Object.fromEntries(Object.entries(controls).map(([k,c])=>[k,k==='target_count'?Number(c.input.value):c.input.value])),[key]:values};
      if(graph){value.fingerprint=graph.fingerprint;value.node_ids=nodeControls.filter(([,c])=>c.checked).map(([id])=>id);}
      if(await C().mutate('creator-design-save',{kind,values:value,revision:record?.revision})){$('creator-dialog').close();await C().load();}
    });redraw();
  }
  return {reset,render};
})();
