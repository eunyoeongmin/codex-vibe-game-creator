'use strict';
window.Creator = (() => {
  let data = null, section = 'content', owner = null, generation = 0, feedback = {}, dialogOwner = null;
  const names = {live: HarnessText.raw('live.workspace'), systems: HarnessText.raw('live.diagram'), soundscape: HarnessText.raw("ui.sound.direction"), balance: HarnessText.raw("ui.game.balance"), saves: HarnessText.raw("ui.play.saves"), languages: HarnessText.raw("ui.game.localization"), experiment: HarnessText.raw("ui.play.comparison"), integration: HarnessText.raw("ui.system.integration.design"), content_plan: HarnessText.raw("ui.content.progression"), content: HarnessText.raw("ui.content.editor"), visual: HarnessText.raw("ui.point.and.request"), relations: HarnessText.raw("ui.data.relationships"), timeline: HarnessText.raw("ui.sequence.timeline"), feedback: HarnessText.raw("ui.play.feedback"), checkpoint: HarnessText.raw("ui.checkpoints"), variant: HarnessText.raw("ui.alternatives"), story: HarnessText.raw("ui.story.workspace"), export: HarnessText.raw("ui.export.game")};
  function reset() {
    owner = current?.id; data = null; generation++; feedback = {}; dialogOwner = null;
    window.LiveWorkspace?.reset(); window.Production?.reset(); window.Gameplay?.reset(); window.Studio?.reset();
    $('creator-dialog').close(); $('creator-body').replaceChildren(); $('creator-status').textContent = '';
  }
  function field(label, value = '', type = 'text') {
    const wrap = element('label', 'creator-field', t(label));
    const input = element(type === 'textarea' ? 'textarea' : 'input');
    if (type !== 'textarea') input.type = type;
    input.value = value ?? ''; wrap.append(input); return {wrap, input};
  }
  function select(label, options, value) {
    const wrap = element('label', 'creator-field', t(label)), input = element('select');
    for (const [key, name] of options) { const option = element('option', '', t(name)); option.value = key; input.append(option); }
    input.value = value; wrap.append(input); return {wrap, input};
  }
  function form(parent, inputs, label, handler) {
    const node = element('form', 'creator-form'); for (const input of inputs) node.append(input.wrap);
    const submit = element('button', 'primary', t(label)); submit.type = 'submit'; node.append(submit);
    const project = current.id;
    node.onsubmit = event => { event.preventDefault(); if (submit.disabled) return; run(async () => {
      if (project !== current?.id) return;
      submit.disabled = true;
      try { await handler(); } catch (error) {
        let message = node.querySelector('.creator-error');
        if (!message) { message = element('p', 'creator-error'); message.setAttribute('role', 'alert'); node.append(message); }
        message.textContent = t(error.message);
        throw error;
      } finally { submit.disabled = false; }
    }); };
    parent.append(node); return node;
  }
  function modal(title) {
    $('creator-dialog').close(); dialogOwner = current.id;
    $('creator-dialog-title').textContent = title; $('creator-dialog-body').replaceChildren();
    $('creator-dialog').showModal(); return $('creator-dialog-body');
  }
  async function mutate(action, body) {
    const version = viewVersion;
    const result = await projectApi(action, body);
    if (version !== viewVersion) return null;
    $('creator-status').textContent = t("ui.saved");
    return result;
  }
  function request(kind, payload, title) {
    const box = modal(title || t("ui.request.an.ai.edit")), input = field(HarnessText.raw("ui.request"), '', 'textarea'); input.input.required = true;
    form(box, [input], HarnessText.raw("ui.send.request"), async () => {
      const result = await mutate('creator-request', {kind, ...payload, text: input.input.value});
      if (result) { $('creator-dialog').close(); $('creator-status').textContent = t("ui.request.sent"); }
    });
  }
  function card(title, note) {
    const node = element('article', 'record'); node.append(element('strong', '', title));
    if (note) node.append(element('p', '', note)); return node;
  }
  function details(parent, label, value) {
    const item = element('details'); item.append(element('summary', '', t(label)), element('pre', '', JSON.stringify(value, null, 2))); parent.append(item);
  }
  async function load() {
    if (owner !== current?.id) reset();
    const version = viewVersion, ticket = ++generation;
    const result = await projectApi('creator');
    if (version !== viewVersion || ticket !== generation) return;
    data = result; render();
  }
  function render() {
    const nav = $('creator-navigation'); nav.replaceChildren();
    for (const [key, label] of Object.entries(names)) {
      const control = button(t(label), () => { section = key; render(); });
      control.classList.toggle('primary', section === key); nav.append(control);
    }
    const box = $('creator-body'); box.replaceChildren(); box.dataset.production = section; if (!data) return;
    if (['live','systems'].includes(section)) return window.LiveWorkspace?.render(section,box,data);
    window.LiveWorkspace?.leave();
    if (['soundscape','balance'].includes(section)) return window.Studio?.render(section, box, data);
    if (['saves', 'languages', 'experiment', 'integration', 'content_plan'].includes(section)) return window.Gameplay?.render(section, box, data);
    if (['visual', 'relations', 'timeline'].includes(section)) return window.Production?.render(section, box, data);
    ({content: renderContent, feedback: renderFeedback, checkpoint: renderCheckpoints, variant: renderVariants, story: renderStory, export: renderExports})[section](box);
  }
  function renderContent(box) {
    box.append(button(t("ui.ask.ai.to.register.game.data"), () => request('content_setup', {}, t("ui.ask.ai.to.register.game.data"))));
    if (!data.content.length) box.append(element('p', 'muted', t("ui.no.game.data.registered")));
    for (const definition of data.content) {
      const node = card(definition.name, definition.path);
      node.append(button(t("ui.edit.rows"), () => editDataset(definition.id)), button(t("ui.change.history"), () => history('content_edit', definition.id)));
      box.append(node);
    }
  }
  async function history(kind, id) {
    const version = viewVersion, result = await projectApi(`creator-history?kind=${kind}&id=${encodeURIComponent(id)}`);
    if (version !== viewVersion) return;
    const box = modal(t("ui.change.history")); details(box, HarnessText.raw("ui.records"), result.items);
  }
  async function editDataset(id) {
    const version = viewVersion, result = await projectApi(`content-show?id=${encodeURIComponent(id)}`);
    if (version !== viewVersion) return;
    const box = modal(result.definition.name), list = element('div', 'creator-row-list'), editor = element('div');
    const search = field(HarnessText.raw("ui.search.rows")); box.append(search.wrap, list, editor);
    function rows() {
      list.replaceChildren();
      for (const row of result.rows.filter(r => JSON.stringify(r).toLowerCase().includes(search.input.value.toLowerCase()))) {
        const identity = row[result.definition.id_field];
        const label = `${identity} · ${Object.entries(row).filter(([k]) => k !== result.definition.id_field).slice(0, 2).map(([, v]) => String(v)).join(' · ')}`;
        list.append(button(label, () => editRow(result, row, editor)));
      }
    }
    search.input.oninput = rows; rows();
  }
  async function editRow(info, row, box) {
    box.replaceChildren(); const version = viewVersion, ticket = ++generation;
    const controls = [];
    for (const spec of info.definition.fields) {
      let control;
      if (spec.type === 'boolean') control = select(spec.label, [['true', HarnessText.raw("ui.yes")], ['false', HarnessText.raw("ui.no")]], String(row[spec.key]));
      else if (spec.type === 'enum') control = select(spec.label, spec.options.map(v => [v, v]), row[spec.key]);
      else if (spec.type === 'reference') {
        const referenced = await projectApi(`content-show?id=${encodeURIComponent(spec.dataset)}`);
        if (version !== viewVersion || ticket !== generation) return;
        control = select(spec.label, referenced.rows.map(r => [r[referenced.definition.id_field], r[referenced.definition.id_field]]), row[spec.key]);
      } else control = field(spec.label, row[spec.key], ['number', 'integer'].includes(spec.type) ? 'number' : 'text');
      control.spec = spec; control.input.disabled = !spec.editable; control.input.required = spec.required;
      if (spec.min !== undefined) control.input.min = spec.min;
      if (spec.max !== undefined) control.input.max = spec.max;
      if (spec.type === 'number') control.input.step = 'any';
      if (!spec.required && control.input.tagName === 'SELECT') {
        const empty = element('option', '', '—'); empty.value = ''; control.input.prepend(empty); control.input.value = row[spec.key] == null ? '' : String(row[spec.key]);
      }
      controls.push(control);
    }
    const payload = {id: info.definition.id, row_id: row[info.definition.id_field], digest: info.digest, revision: info.definition.revision};
    form(box, controls, HarnessText.raw("ui.save"), async () => {
      const values = {};
      for (const {spec, input} of controls.filter(c => c.spec.editable)) {
        values[spec.key] = input.value === '' && !spec.required ? null : ['number', 'integer'].includes(spec.type) ? Number(input.value) : spec.type === 'boolean' ? input.value === 'true' : input.value;
      }
      if (await mutate('content-save', {...payload, values})) await editDataset(info.definition.id);
    });
    box.append(button(t("ui.modify.this.item"), () => request('content', payload)));
  }
  function renderCheckpoints(box) {
    const name = field(HarnessText.raw("ui.name")); name.input.required = true;
    form(box, [name], HarnessText.raw("ui.save.checkpoint"), async () => { if (await mutate('checkpoint-add', {name: name.input.value})) await load(); });
    for (const record of data.checkpoint) {
      const node = card(record.name, `${record.created_at} · ${(record.size / 1048576).toFixed(1)} MB`);
      node.append(button(t("ui.restore"), async () => {
        if (!window.confirm(t("ui.save.the.current.state.and.restore.this.checkpoint"))) return;
        if (await mutate('checkpoint-restore', {id: record.id, confirmation: 'restore:' + record.id})) {
          $('preview-frame').removeAttribute('src'); $('preview-actions').hidden = true;
          window.Workbench?.reset(); planningKey = ''; productionKey = ''; await load();
        }
      })); box.append(node);
    }
  }
  function renderVariants(box) {
    const name = field(HarnessText.raw("ui.name")), hypothesis = field(HarnessText.raw("ui.difference.to.try"), '', 'textarea'), entry = field(HarnessText.raw("ui.html.entry.path"), $('preview-path').value || 'index.html');
    name.input.required = hypothesis.input.required = entry.input.required = true;
    form(box, [name, hypothesis, entry], HarnessText.raw("ui.create.alternative"), async () => {
      if (await mutate('variant-add', {name: name.input.value, hypothesis: hypothesis.input.value, entry: entry.input.value})) await load();
    });
    for (const record of data.variant) {
      const node = card(record.name, record.hypothesis); node.append(element('small', '', record.folder));
      node.append(button(t("ui.run.side.by.side"), async () => {
        const version = viewVersion, urls = await projectApi('variant-preview', {id: record.id}); if (version !== viewVersion) return;
        const container = modal(record.name), grid = element('div', 'creator-comparison');
        for (const [key, label] of [['main', HarnessText.raw("ui.main.game")], ['alternative', HarnessText.raw("ui.alternatives")]]) {
          const cell = element('section'), link = element('a', '', t("ui.open.in.new.tab")); link.href = urls[key]; link.target = '_blank'; link.rel = HarnessText.raw("js.creator.noopener.noreferrer");
          const frame = element('iframe'); frame.src = urls[key]; frame.title = t(label); frame.sandbox = HarnessText.raw("js.creator.allow.scripts.allow.same.origin.allow.pointer.lock"); frame.allowFullscreen = true;
          cell.append(element('h3', '', t(label)), link, frame); grid.append(cell);
        }
        container.append(grid);
      }));
      if (record.status === 'comparison') node.append(button(t("ui.request.an.ai.edit"), () => request('variant', {id: record.id})), button(t("ui.use.this.alternative"), async () => {
        if (!window.confirm(t("ui.back.up.the.main.game.and.apply.this"))) return;
        if (await mutate('variant-adopt', {id: record.id, confirmation: 'adopt:' + record.id})) await load();
      })); else node.append(element('p', '', t("ui.selected")));
      box.append(node);
    }
  }
  function renderStory(box) {
    box.append(button(t("ui.add.story.record"), () => storyForm()), button(t("ui.request.story.writing"), () => request('story', {}, t("ui.request.story.writing"))));
    for (const record of data.story) {
      const node = card(record.title, record.body);
      node.append(element('small', '', `${t(record.kind)} · ${t(record.status)} · ${record.updated_at}`));
      if (record.condition) node.append(element('p', '', `${t("ui.trigger.conditions")}: ${record.condition}`));
      if (record.game_effect) node.append(element('p', '', `${t("ui.game.effects")}: ${record.game_effect}`));
      node.append(button(t("ui.edit"), () => storyForm(record)), button(t("ui.request.an.ai.edit"), () => request('story', {id: record.id, revision: record.revision})),
        button(t("ui.change.history"), () => history('story_history', record.id))); box.append(node);
    }
  }
  function storyForm(record = {}) {
    const box = modal(t("ui.story.workspace"));
    const fields = {
      kind: select(HarnessText.raw("ui.type.2"), [["character", HarnessText.raw("ui.character")], ["event", HarnessText.raw("ui.event")], ["branch", HarnessText.raw("ui.branch")], ["world", HarnessText.raw("ui.world.setting")]], record.kind || "character"),
      title: field(HarnessText.raw("ui.title"), record.title), body: field(HarnessText.raw("ui.content"), record.body, 'textarea'),
      condition: field(HarnessText.raw("ui.trigger.conditions"), record.condition, 'textarea'), game_effect: field(HarnessText.raw("ui.game.effects"), record.game_effect, 'textarea'),
      links: field(HarnessText.raw("ui.linked.story.ids"), (record.links || []).join(', ')),
      status: select(HarnessText.raw("ui.status"), [["proposed", HarnessText.raw("ui.proposed")], ["confirmed", HarnessText.raw("ui.confirmed")]], record.status || "proposed")
    };
    fields.title.input.required = fields.body.input.required = true;
    form(box, Object.values(fields), HarnessText.raw("ui.save"), async () => {
      const values = Object.fromEntries(Object.entries(fields).map(([key, control]) => [key, control.input.value]));
      values.links = values.links.split(',').map(v => v.trim()).filter(Boolean); if (record.id) values.id = record.id;
      if (await mutate('story-save', {values, revision: record.revision})) { $('creator-dialog').close(); await load(); }
    });
  }
  async function gameState() {
    const frame = $('preview-frame'), src = frame.getAttribute('src'); if (!src) return {};
    const origin = new URL(src).origin, nonce = crypto.randomUUID(), source = frame.contentWindow;
    return new Promise(resolve => {
      let timer;
      const finish = value => { clearTimeout(timer); window.removeEventListener('message', receive); resolve(value); };
      const receive = event => {
        if (event.source !== source || event.origin !== origin || event.data?.type !== 'creator-state' || event.data.nonce !== nonce) return;
        try { if (JSON.stringify(event.data.state).length > 32000) return finish({}); } catch (_) { return finish({}); }
        finish({state: event.data.state, state_at: event.data.at});
      };
      window.addEventListener('message', receive); timer = setTimeout(() => finish({}), 1800);
      source.postMessage({type: 'creator-state-request', nonce}, origin);
    });
  }
  async function captureImage() {
    if (!navigator.mediaDevices?.getDisplayMedia) throw new Error(t("ui.screen.capture.is.unavailable.attach.an.image.file"));
    const version = viewVersion;
    const stream = await navigator.mediaDevices.getDisplayMedia({video: true, audio: false});
    try {
      const video = document.createElement('video'); video.srcObject = stream; video.muted = true; await video.play();
      const canvas = document.createElement('canvas'), scale = Math.min(1, 1920 / video.videoWidth);
      canvas.width = Math.round(video.videoWidth * scale); canvas.height = Math.round(video.videoHeight * scale);
      canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
      const image = canvas.toDataURL('image/png'), captured_at = new Date().toISOString(), state = await gameState();
      if (version === viewVersion) return {...state, image, captured_at, size: [canvas.width, canvas.height]};
    } finally { stream.getTracks().forEach(track => track.stop()); }
  }
  async function capture() { const result = await captureImage(); if (result) { feedback = {...feedback, ...result}; showFeedbackImage(); } }
  function showFeedbackImage() {
    const box = $('creator-feedback-image'); if (!box) return; box.replaceChildren();
    if (feedback.image) { const image = element('img'); image.src = feedback.image; image.alt = t("ui.play.screenshot"); box.append(image); }
    box.append(element('small', '', t(feedback.state == null ? HarnessText.raw("ui.game.state.unavailable") : HarnessText.raw("ui.game.state.captured"))));
    if (feedback.state != null) details(box, HarnessText.raw("ui.game.state"), feedback.state);
  }
  function renderFeedback(box) {
    box.append(button(t("ui.capture.screen"), capture));
    const upload = field(HarnessText.raw("ui.attach.image"), '', 'file'); upload.input.accept = 'image/*';
    upload.input.onchange = () => run(async () => {
      const version = viewVersion, file = upload.input.files[0]; if (!file) return;
      if (!file.type.startsWith('image/') || file.size > 12 * 1048576) throw new Error(t("ui.choose.an.image.up.to.mb"));
      const bitmap = await createImageBitmap(file);
      try {
        const canvas = document.createElement('canvas'), scale = Math.min(1, 1920 / bitmap.width);
        canvas.width = Math.round(bitmap.width * scale); canvas.height = Math.round(bitmap.height * scale); canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        if (version === viewVersion) { feedback = {...feedback, image: canvas.toDataURL('image/png'), captured_at: null, state: null, state_at: null}; showFeedbackImage(); }
      } finally { bitmap.close(); }
    });
    const imageBox = element('div'); imageBox.id = 'creator-feedback-image'; box.append(upload.wrap, imageBox);
    const entry = field(HarnessText.raw("ui.html.entry.path"), feedback.entry || $('preview-path').value || 'index.html'), comment = field(HarnessText.raw("ui.play.feedback"), feedback.comment || '', 'textarea');
    comment.input.required = true; comment.input.oninput = () => { feedback.comment = comment.input.value; };
    entry.input.oninput = () => { feedback.entry = entry.input.value; };
    form(box, [entry, comment], HarnessText.raw("ui.save.feedback"), async () => {
      if (await mutate('feedback-save', {...feedback, entry: entry.input.value, comment: comment.input.value})) { feedback = {}; await load(); }
    }); showFeedbackImage();
    for (const record of data.feedback) {
      const node = card(record.comment, `${record.entry} · ${record.created_at}`);
      if (record.image) node.append(button(t("ui.view.image"), async () => {
        const version = viewVersion, result = await projectApi('feedback-image?id=' + encodeURIComponent(record.id)); if (version !== viewVersion) return;
        const modalBox = modal(t("ui.play.screenshot")), image = element('img'); image.src = result.image; image.alt = t("ui.play.screenshot"); modalBox.append(image);
      }));
      if (record.state != null) details(node, HarnessText.raw("ui.game.state"), record.state);
      node.append(button(t("ui.send.to.ai"), () => request('feedback', {id: record.id}))); box.append(node);
    }
  }
  async function download(record) {
    const response = await fetch(`/api/projects/${current.id}/creator-download?id=${encodeURIComponent(record.id)}`, {headers: {Authorization: 'Bearer ' + token}});
    if (!response.ok) throw new Error((await response.json()).error);
    const url = URL.createObjectURL(await response.blob()), anchor = document.createElement('a');
    anchor.href = url; anchor.download = record.name.replace(/[<>:"/\\|?*]/g, '-') + '.zip'; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 60000);
  }
  function renderExports(box) {
    const name = field(HarnessText.raw("ui.name"), current.name), entry = field(HarnessText.raw("ui.html.entry.path"), $('preview-path').value || 'index.html'); name.input.required = entry.input.required = true;
    form(box, [name, entry], HarnessText.raw("ui.create.game.zip"), async () => {
      if (await mutate('game-export', {name: name.input.value, entry: entry.input.value})) await load();
    });
    box.append(element('p', 'muted', t("ui.exports.the.selected.html.folder.build.engine.projects")));
    for (const record of data.export) {
      const node = card(record.name, `${record.created_at} · ${(record.size / 1048576).toFixed(1)} MB`);
      details(node, HarnessText.raw("ui.included.files"), record.files); node.append(button(t("ui.download.zip"), () => download(record))); box.append(node);
    }
  }
  $('creator-refresh').onclick = () => run(load);
  $('creator-dialog-close').onclick = () => $('creator-dialog').close();
  $('preview-feedback').onclick = () => run(async () => { section = 'feedback'; document.querySelector('[data-tab="creator"]').click(); });
  function open(next){section=next; document.querySelector('[data-tab="creator"]').click();}
  return {open, reset, load, render, field, select, form, modal, mutate, request, card, details, captureImage, history};
})();
