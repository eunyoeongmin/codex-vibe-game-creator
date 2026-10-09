'use strict';
window.AssetUI = (() => {
  let items = [], artDecisions = [], selected = null, loading = false, epoch = 0;
  const kinds = () => ({image: t("ui.image"), sound: t("ui.sound")});
  const statuses = () => ({temporary: t("ui.temporary"), proposed: t("ui.proposed"), confirmed: t("ui.confirmed"), retired: t("ui.retired")});
  const methods = () => ({code: t("ui.code.art"), image_skill: t("ui.image.generation"), external: t("ui.external.asset"), other_skill: t("ui.other.skill.not.connected")});
  const usages = () => ({planned: t("ui.planned"), in_use: t("ui.in.use"), unused: t("ui.unused")});
  const lines = text => text.split('\n').map(s => s.trim()).filter(Boolean);
  function options(select, values, all = false) {
    const previous = select.value;
    select.replaceChildren(...(all ? [new Option(t("ui.all"), '')] : []), ...Object.entries(values).map(([v, label]) => new Option(label, v)));
    if ([...select.options].some(o => o.value === previous)) select.value = previous;
  }
  function reset() {
    epoch++; items = []; artDecisions = []; selected = null;
    $('asset-dialog').close(); $('asset-list').replaceChildren();
    $('asset-search').value = ''; $('asset-kind-filter').value = ''; $('asset-status-filter').value = '';
    $('asset-attention').hidden = true;
  }
  async function load() {
    if (!current || loading) return;
    loading = true; const version = viewVersion, own = epoch;
    try {
      const result = await projectApi('assets');
      if (version !== viewVersion || own !== epoch) return;
      items = result.assets; artDecisions = result.art_decisions || []; render();
    } finally { loading = false; }
  }
  function render() {
    $('asset-art-decisions').replaceChildren();
    for (const d of artDecisions) $('asset-art-decisions').append(element('p', '', `${d.topic}: ${d.decision} (${d.id})`));
    options($('asset-kind-filter'), kinds(), true); options($('asset-status-filter'), statuses(), true);
    const query = $('asset-search').value.trim().toLocaleLowerCase();
    const visible = items.filter(a => (!$('asset-kind-filter').value || a.kind === $('asset-kind-filter').value) &&
      (!$('asset-status-filter').value || a.status === $('asset-status-filter').value) &&
      (!query || [a.name,a.group,a.usage,a.art_notes,a.reason].join(' ').toLocaleLowerCase().includes(query)));
    $('asset-list').replaceChildren();
    if (!visible.length) $('asset-list').append(element('p', 'muted', t("ui.no.assets.to.display")));
    for (const a of visible) {
      const card = element('article', HarnessText.raw("js.assets.record.asset.card"));
      card.append(element('strong', '', a.name), element('small', '', `${kinds()[a.kind]} · ${statuses()[a.status]} · ${usages()[a.usage_state]}`));
      if (a.group) card.append(element('small', '', a.group));
      card.append(element('p', '', a.usage), element('small', '', a.methods.map(m=>methods()[m]).join(' + ')));
      if (a.status === 'temporary') card.append(element('p', 'asset-temporary', a.replacement_plan));
      card.append(button(t("ui.open.edit"), () => edit(a)));
      $('asset-list').append(card);
    }
  }
  function attention(counts) {
    const pending = (counts?.temporary || 0) + (counts?.proposed || 0);
    $('asset-attention').hidden = !pending;
    $('asset-attention').textContent = t("ui.assets.temporary.proposed", counts?.temporary || 0, counts?.proposed || 0);
  }
  async function edit(asset = null) {
    epoch++;
    selected = asset;
    $('asset-form').reset(); $('asset-history').replaceChildren(); $('asset-media').replaceChildren();
    $('asset-request-text').value = ''; $('asset-request-panel').hidden = !asset;
    $('asset-history-button').hidden = !asset;
    $('asset-title').textContent = asset ? t("ui.version.2", asset.name, asset.revision) : t("ui.add.asset");
    options($('asset-kind'), kinds()); options($('asset-status'), statuses()); options($('asset-usage-state'), usages());
    $('asset-methods').replaceChildren();
    for (const [value, label] of Object.entries(methods())) {
      const wrapper = element('label'), input = element('input'); input.type = 'checkbox'; input.value = value;
      input.checked = asset?.methods.includes(value) || false; wrapper.append(input, document.createTextNode(label)); $('asset-methods').append(wrapper);
    }
    for (const field of ['name','kind','group','usage','usage_state','status','files','art_notes','reason','source_note','replacement_plan','decision_ids','reference_ids']) {
      const node = $('asset-' + field.replaceAll('_', '-'));
      const value = asset?.[field] ?? ({kind:'image', status:'temporary', usage_state:'planned'}[field] || '');
      node.value = Array.isArray(value) ? value.join('\n') : value;
    }
    $('asset-change-note').value = '';
    $('asset-link-decisions').replaceChildren();
    for (const d of artDecisions) {
      const label=element('label'), input=element('input'); input.type='checkbox';
      input.checked=asset?.decision_ids.includes(d.id) || false;
      input.onchange=()=>{
        const ids=new Set(lines($('asset-decision-ids').value)); if(input.checked) ids.add(d.id); else ids.delete(d.id);
        $('asset-decision-ids').value=[...ids].join('\n');
      };
      label.append(input,document.createTextNode(`${d.topic}: ${d.decision}`)); $('asset-link-decisions').append(label);
    }
    $('asset-status').onchange();
    if (!$('asset-dialog').open) $('asset-dialog').showModal();
    if (asset) await preview(asset);
  }
  async function preview(asset) {
    const version = viewVersion, own = epoch;
    for (const path of asset.files) {
      const name = element('p', 'asset-file', path); $('asset-media').append(name);
      if (!/\.(png|jpe?g|gif|webp|avif|bmp|svg|mp3|wav|ogg|m4a|flac)$/i.test(path)) {
        $('asset-media').append(button(t("ui.edit.code.file"), async () => {
          await readFile(path); $('asset-dialog').close(); document.querySelector('[data-tab="files"]').click();
        }));
        continue;
      }
      try {
        const result = await projectApi(`asset-media?id=${encodeURIComponent(asset.id)}&path=${encodeURIComponent(path)}`);
        if (version !== viewVersion || own !== epoch || !$('asset-dialog').open) return;
        const node = element(result.mime.startsWith('audio/') ? 'audio' : 'img');
        if (node.tagName === 'AUDIO') node.controls = true; else node.alt = asset.name;
        node.src = `data:${result.mime};base64,${result.data}`; $('asset-media').append(node);
      } catch (error) { if (version === viewVersion && own === epoch) name.append(document.createTextNode(' · ' + t(error.message))); }
    }
  }
  $('asset-add').onclick = () => run(() => edit());
  $('asset-refresh').onclick = () => run(load);
  for (const name of ['kind-filter','status-filter','search']) $('asset-'+name).addEventListener('input', render);
  $('asset-close').onclick = () => $('asset-dialog').close();
  $('asset-dialog').addEventListener('close', () => {
    epoch++;
    for (const audio of $('asset-media').querySelectorAll('audio')) audio.pause();
  });
  $('asset-status').onchange = () => {
    $('asset-replacement-plan').required = $('asset-status').value === 'temporary';
    if ($('asset-status').value === 'retired') $('asset-usage-state').value = 'unused';
  };
  $('asset-attention').onclick = () => { document.querySelector('[data-tab="assets"]').click(); };
  $('asset-form').onsubmit = event => {
    event.preventDefault(); run(async () => {
      const values = {};
      for (const field of ['name','kind','group','usage','usage_state','status','files','art_notes','reason','source_note','replacement_plan','decision_ids','reference_ids']) {
        const value = $('asset-' + field.replaceAll('_', '-')).value;
        values[field] = ['files','decision_ids','reference_ids'].includes(field) ? lines(value) : value;
      }
      values.methods = [...$('asset-methods').querySelectorAll('input:checked')].map(n=>n.value);
      if (values.status === "confirmed") values.approval_quote = t("ui.selected.save.as.confirmed.in.asset.management");
      const version = viewVersion, own = epoch;
      $('asset-save').disabled = true;
      try {
        await projectApi('asset-save', {id:selected?.id, revision:selected?.revision, values, change_note:$('asset-change-note').value});
        if (version !== viewVersion || own !== epoch) return;
        $('asset-dialog').close(); await load(); notice(t("ui.asset.record.saved"));
      } finally { $('asset-save').disabled = false; }
    });
  };
  $('asset-upload').onchange = () => run(async () => {
    const file = $('asset-upload').files[0]; if (!file) return;
    const version = viewVersion, own = epoch, pid = current.id;
    $('asset-upload').value = '';
    if (file.size > 16 * 1024 * 1024) throw new Error(t("ui.attachments.must.be.mb.or.smaller"));
    $('asset-save').disabled = true;
    try {
      const data = await new Promise((resolve,reject) => { const r = new FileReader(); r.onload=()=>resolve(r.result.split(',')[1]); r.onerror=reject; r.readAsDataURL(file); });
      const result = await api(`projects/${pid}/upload`, {name:file.name, data});
      if (version !== viewVersion || own !== epoch) return;
      $('asset-files').value = [...lines($('asset-files').value), result.path].join('\n');
    } finally { $('asset-save').disabled = false; }
  });
  $('asset-history-button').onclick = () => run(async () => {
    const version = viewVersion, own = epoch;
    const result = await projectApi('asset-history?id=' + encodeURIComponent(selected.id));
    if (version !== viewVersion || own !== epoch) return;
    $('asset-history').replaceChildren();
    for (const h of result.history) {
      const detail=element('details'), summary=element('summary','',`v${h.revision} · ${h.created_at} · ${h.change_note}`);
      detail.append(summary,element('pre','',JSON.stringify(h.snapshot,null,2))); $('asset-history').append(detail);
    }
  });
  $('asset-request-send').onclick = () => run(async () => {
    if (!connected) throw new Error(t("ui.connect.to.this.project.s.conversation.first"));
    const text=$('asset-request-text').value;
    if (!text.trim()) throw new Error(t("ui.enter.a.change.request"));
    const version=viewVersion, own=epoch;
    $('asset-request-send').disabled=true; sending=true; renderActivity();
    try {
      const result=await projectApi('asset-request',{id:selected.id,revision:selected.revision,text});
      if (version!==viewVersion || own!==epoch) return;
      working=result.working; activity=result.activity; $('asset-dialog').close(); await poll();
    } finally { $('asset-request-send').disabled=false; if(version===viewVersion) {sending=false;renderActivity();} }
  });
  return {reset,load,render,attention};
})();
