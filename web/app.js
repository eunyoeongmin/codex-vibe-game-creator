'use strict';
const $ = id => document.getElementById(id);
const fragment = new URLSearchParams(location.hash.slice(1));
const token = fragment.get('token') || sessionStorage.getItem('harness-token');
if (fragment.has('token')) { sessionStorage.setItem('harness-token', token); history.replaceState(null, '', '/'); }
let current = null, cursor = 0, projects = [], polling = false, connected = false, working = false;
let uploads = [], openFile = null, fileDigest = null, selectedModel = '', lastQuestionKey = '', viewVersion = 0;
let sending = false;
let activity = null;
let chatHistory = {ready: false, busy: false, before: null, more: false};
let modelCatalog = [], sandboxPending = false;
let planning = null, planningKey = '', summaryVisible = false, summaryBusy = false;
let productionKey = '', productionStarted = null;
const itemNodes = new Map();
let appearance = {left: false, right: false, top: false, theme: 'light', sizes: {left: 246, right: 460, top: 100}};
try {
  const saved = JSON.parse(localStorage.getItem('harness-appearance') || '{}');
  for (const panel of ['left', 'right', 'top']) appearance[panel] = saved[panel] === true;
  appearance.theme = saved.theme === 'dark' ? 'dark' : 'light';
  for (const panel of ['left', 'right', 'top']) if (Number.isFinite(saved.sizes?.[panel])) appearance.sizes[panel] = saved.sizes[panel];
} catch (_) { /* Keep defaults when browser storage is unavailable. */ }
function panelBounds(panel) {
  if (panel === 'top') return [72, Math.max(72, Math.min(260, innerHeight * .35))];
  if (panel === 'left') return [160, Math.max(160, Math.min(420, innerWidth * .32))];
  return [220, Math.max(220, document.querySelector('main').clientWidth - 280)];
}
function applyAppearance() {
  const labels = {left: t("ui.left"), right: t("ui.right"), top: t("ui.top")};
  for (const panel of Object.keys(labels)) {
    document.body.classList.toggle(`${panel}-collapsed`, appearance[panel]);
    const label = t("ui.panel", labels[panel], appearance[panel] ? t("ui.expand") : t("ui.collapse"));
    $(`toggle-${panel}`).setAttribute('aria-label', label);
    $(`toggle-${panel}`).title = label;
    $(`toggle-${panel}`).setAttribute('aria-expanded', String(!appearance[panel]));
    $(`reveal-${panel}`)?.setAttribute('aria-label', t("ui.panel", labels[panel], t("ui.expand")));
  }
  for (const panel of ['left', 'right', 'top']) {
    const [min, max] = panelBounds(panel), value = Math.round(Math.max(min, Math.min(max, appearance.sizes[panel])));
    document.body.style.setProperty(`--${panel}-${panel === 'top' ? 'height' : 'width'}`, value + 'px');
    for (const [key, number] of Object.entries({min, max, now: value})) $(`resize-${panel}`).setAttribute(`aria-value${key}`, String(number));
  }
  document.documentElement.dataset.theme = appearance.theme;
  $('toggle-theme').textContent = appearance.theme === 'dark' ? t("ui.light.mode") : t("ui.dark.mode");
  $('toggle-theme').setAttribute('aria-pressed', String(appearance.theme === 'dark'));
  try { localStorage.setItem('harness-appearance', JSON.stringify(appearance)); } catch (_) {}
}
for (const panel of ['left', 'right', 'top']) $(`toggle-${panel}`).onclick = () => {
  document.body.classList.remove(`${panel}-peek`);
  appearance[panel] = !appearance[panel]; applyAppearance();
};
for (const panel of ['left', 'right', 'top']) {
  const region = $(`${panel}-panel`), edge = document.createElement('button');
  edge.id = `reveal-${panel}`; edge.className = 'panel-reveal'; edge.type = 'button';
  edge.setAttribute('aria-label', t("ui.panel", {left: t("ui.left"), right: t("ui.right"), top: t("ui.top")}[panel], t("ui.expand")));
  edge.setAttribute('aria-controls', region.id);
  (panel === 'right' ? $('workspace') : document.body).append(edge);
  const peek = () => { if (appearance[panel]) document.body.classList.add(`${panel}-peek`); };
  const hide = event => {
    if (!region.contains(event.relatedTarget) && event.relatedTarget !== edge)
      document.body.classList.remove(`${panel}-peek`);
  };
  edge.addEventListener('pointerenter', peek);
  edge.addEventListener('focus', peek);
  edge.addEventListener('pointerleave', hide);
  region.addEventListener('pointerleave', hide);
  region.addEventListener('focusout', hide);
  edge.addEventListener('blur', hide);
  edge.onclick = () => {
    appearance[panel] = false; document.body.classList.remove(`${panel}-peek`); applyAppearance();
    $(`toggle-${panel}`).focus();
  };
}
$('toggle-theme').onclick = () => { appearance.theme = appearance.theme === 'dark' ? 'light' : 'dark'; applyAppearance(); };
$('language').onchange = () => run(async () => {
  const settings = await api('preferences', {language: $('language').value});
  I18n.apply(settings.language); applyAppearance(); renderUploads();
  window.AssetUI?.render();
  planningKey = ''; productionKey = ''; if (planning) renderPlanning(planning);
  // Keep drafts, editor changes and question answers when changing languages.
  for (const card of $('questions').children) {
    const buttons = card.querySelector('.question-actions')?.children;
    if (buttons) { buttons[0].textContent = t("ui.skip"); buttons[1].textContent = t("ui.send.answer"); }
    for (const input of card.querySelectorAll('textarea')) input.placeholder = t("ui.or.type.your.answer.shift.enter.for.a");
  }
  if (!current) $('page-title').textContent = t("ui.where.ideas.become.games");
  await loadProjects(); await loadStatus();
  if (current) { await poll(); if (!$('tab-records').hidden) await loadRecords(); }
  notice(t("ui.the.conversation.language.applies.from.the.next.turn"));
});
applyAppearance();
window.addEventListener('resize', applyAppearance);
for (const panel of ['left', 'right', 'top']) {
  const handle = $(`resize-${panel}`);
  let drag = null;
  handle.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    event.preventDefault(); handle.setPointerCapture(event.pointerId);
    const rect = $(`${panel}-panel`).getBoundingClientRect();
    drag = {x: event.clientX, y: event.clientY, size: panel === 'top' ? rect.height : rect.width};
    document.body.classList.add('resizing');
  });
  handle.addEventListener('pointermove', event => {
    if (!drag) return;
    const delta = panel === 'top' ? event.clientY - drag.y : (event.clientX - drag.x) * (panel === 'right' ? -1 : 1);
    const [min, max] = panelBounds(panel);
    appearance.sizes[panel] = Math.max(min, Math.min(max, drag.size + delta)); applyAppearance();
  });
  const end = () => { drag = null; document.body.classList.remove('resizing'); };
  handle.addEventListener('pointerup', end); handle.addEventListener('pointercancel', end); handle.addEventListener('lostpointercapture', end);
  handle.addEventListener('keydown', event => {
    const direction = panel === 'top' ? {ArrowUp: -1, ArrowDown: 1} : {ArrowLeft: -1, ArrowRight: 1};
    if (!direction[event.key]) return;
    event.preventDefault();
    const [min, max] = panelBounds(panel);
    appearance.sizes[panel] = Math.max(min, Math.min(max, Number(handle.getAttribute('aria-valuenow')) + direction[event.key] * (panel === 'right' ? -16 : 16)));
    applyAppearance();
  });
}

async function api(path, body) {
  let response;
  try { response = await fetch('/api/' + path, {method: body === undefined ? 'GET' : 'POST',
    headers: {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body)}); }
  catch (_) { const error = new Error(t("ui.cannot.reach.the.dashboard.server.restart.the.program")); error.reconnect = true; throw error; }
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(((result.message_key ? t(result.message_key, ...(result.message_args || [])) : t(result.error)) || t("ui.request.failed")) + (result.detail ? '\n' + result.detail : ''));
    error.reconnect = response.status >= 500;
    error.restartRequired = result.restart_required === true;
    throw error;
  }
  return result;
}
const projectApi = (action, body) => api('projects/' + current.id + '/' + action, body);
function notice(text, reconnect = false) { $('notice-text').textContent = t(text) || ''; $('notice').hidden = !text; $('reconnect').hidden = !text || !reconnect; }
async function run(action) { try { return await action(); } catch (error) { notice(t(error.message), !!current && (!!error.reconnect || !connected)); } }
function element(tag, className, text) { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; }
function button(text, handler, className) { const node = element('button', className, text); node.type = 'button'; node.addEventListener('click', () => run(handler)); return node; }

async function loadProjects() {
  projects = (await api('projects')).projects;
  $('project-list').replaceChildren(); $('project-cards').replaceChildren();
  $('project-count').textContent = t("ui.projects", projects.length);
  for (const project of projects) {
    $('project-list').append(button(project.name, () => openProject(project), current?.id === project.id ? 'selected' : ''));
    const card = button('', () => openProject(project), 'project-card');
    card.append(element('strong', '', project.name), element('small', '', t("ui.open.workshop")));
    $('project-cards').append(card);
  }
  if (!projects.length) $('project-cards').append(element('p', 'empty', t("ui.no.projects.yet.name.your.first.game.to")));
}

async function loadStatus() {
  const status = await api('status');
  $('account-label').textContent = t(status.error) || (status.account ? t("ui.codex.connected", status.account.planType || status.account.type) : t("ui.sign.in.to.start.creating.games"));
  $('login').hidden = !!status.account;
  if (status.account) $('login-link').hidden = true;
  const wasPending = sandboxPending;
  sandboxPending = status.sandbox_readiness !== 'ready' && status.sandbox_setup?.success === null;
  $('sandbox-setup').hidden = status.sandbox_setup?.success !== false || !!status.error;
  $('sandbox-setup').disabled = status.sandbox_setup?.success === null;
  $('sandbox-status').textContent = status.sandbox_readiness === 'ready' ? '' :
    t(status.sandbox_setup?.error) || (sandboxPending ? t("ui.setting.up.permissions.complete.the.windows.administrator.prompt") : t("ui.checking.permissions"));
  modelCatalog = status.models || [];
  const previous = $('model').value;
  $('model').replaceChildren(new Option(t("ui.default.codex.model"), ''));
  for (const model of status.models || []) $('model').add(new Option(model.displayName || model.model, model.model));
  $('model').value = previous;
  renderEfforts($('effort').value);
  renderSpeeds($('speed').value);
  if (wasPending && status.sandbox_readiness === 'ready' && current && !connected && !$('connect').disabled) await connect();
  return status;
}

function renderEfforts(preferred) {
  const model = modelCatalog.find(m => m.model === $('model').value) || modelCatalog.find(m => m.isDefault);
  const efforts = model?.supportedReasoningEfforts || [];
  $('effort').replaceChildren();
  const labels = {none: t("ui.none"), minimal: t("ui.minimal"), low: t("ui.low"), medium: t("ui.medium"), high: t("ui.high"), xhigh: t("ui.very.high"), ultra: t("ui.maximum")};
  for (const item of efforts) {
    const value = item.reasoningEffort;
    const option = new Option(`${labels[value] || value} (${value})`, value);
    option.title = item.description || ''; $('effort').add(option);
  }
  $('effort').value = efforts.some(e => e.reasoningEffort === preferred) ? preferred : (model?.defaultReasoningEffort || '');
  $('effort').disabled = !efforts.length;
}

function renderSpeeds(preferred) {
  const model = modelCatalog.find(m => m.model === $('model').value) || modelCatalog.find(m => m.isDefault);
  const tiers = model?.serviceTiers?.length ? model.serviceTiers : (model?.additionalSpeedTiers || []).map(id => ({id: id === 'fast' ? 'priority' : id, name: id}));
  $('speed').replaceChildren(new Option(t("ui.standard.speed"), 'default'));
  for (const tier of tiers) {
    if (tier.id === 'default') continue;
    const option = new Option(['fast', 'priority'].includes(tier.id) ? t("ui.fast.higher.usage") : tier.name, tier.id);
    option.title = tier.description || ''; $('speed').add(option);
  }
  $('speed').value = [...$('speed').options].some(o => o.value === preferred) ? preferred : 'default';
  $('speed').disabled = $('speed').options.length < 2;
  $('speed').title = $('speed').selectedOptions[0]?.title || t("ui.available.speeds.for.this.model");
}

async function openProject(project) {
  window.Workbench?.reset(); window.Creator?.reset();
  clearUploads(); sending = false;
  window.AssetUI?.reset();
  viewVersion++; current = project; cursor = 0; itemNodes.clear(); lastQuestionKey = '';
  const version = viewVersion;
  chatHistory = {ready: false, busy: false, before: null, more: false};
  connected = working = false; activity = null; openFile = fileDigest = null;
  planning = null; planningKey = ''; summaryVisible = false;
  productionKey = ''; productionStarted = null;
  $('planning-summary').hidden = true;
  $('home').hidden = true; $('workspace').hidden = false; $('folder').hidden = false;
  $('page-title').textContent = project.name; $('messages').replaceChildren(); $('questions').replaceChildren();
  $('messages').classList.add('history-initial');
  $('instruction-history').replaceChildren();
  $('message').value = ''; $('editor-panel').hidden = true; $('preview-frame').removeAttribute('src');
  $('preview-link').removeAttribute('href'); $('preview-link').textContent = ''; $('preview-actions').hidden = true;
  $('model').value = project.model || selectedModel; renderEfforts(); renderSpeeds(project.info?.requested_service_tier); renderUploads(); notice('');
  await loadHistory(true);
  if (version !== viewVersion || !chatHistory.ready) return;
  await loadProjects(); await loadFiles(); await poll(); await loadUsage();
  if (version !== viewVersion) return;
  if (!connected) await connect();
}

async function loadHistory(initial = false) {
  if (!current || chatHistory.busy || (!initial && !chatHistory.more)) return;
  const state = chatHistory, version = viewVersion, id = current.id;
  state.busy = true;
  const loader = $('history-loading'); loader.hidden = false;
  $('history-retry').hidden = true; loader.querySelector('progress').hidden = false;
  $('history-loading-label').textContent = initial ? t("ui.loading.conversation") : t("ui.loading.earlier.messages");
  $('messages').setAttribute('aria-busy', 'true');
  try {
    const result = await api(`projects/${id}/history${initial ? '' : '?before=' + state.before}`);
    if (version !== viewVersion) return;
    const box = $('messages'), fragment = document.createDocumentFragment();
    // Anchor to a visible message so live replies arriving during the request cannot move the viewport.
    const anchor = [...box.children].find(node => node.getBoundingClientRect().bottom > box.getBoundingClientRect().top);
    const anchorTop = anchor?.getBoundingClientRect().top;
    for (const event of result.events) showEvent(event, fragment, true);
    for (const event of result.instructions || []) showEvent(event, fragment, true);
    if (initial) box.replaceChildren(fragment); else box.prepend(fragment);
    state.before = result.before; state.more = result.has_more;
    if (initial) {
      cursor = result.cursor; state.ready = true;
      box.classList.remove('history-initial'); box.scrollTop = box.scrollHeight;
    } else if (anchor) box.scrollTop += anchor.getBoundingClientRect().top - anchorTop;
    loader.hidden = true;
    if (state.error && $('notice-text').textContent === t(state.error)) notice('');
    state.error = null;
  } catch (error) {
    if (version !== viewVersion) return;
    $('history-loading-label').textContent = t("ui.could.not.load.the.conversation");
    loader.querySelector('progress').hidden = true; $('history-retry').hidden = false;
    state.error = error.message;
    notice(error.message, !!error.reconnect);
  } finally {
    state.busy = false;
    if (version === viewVersion) $('messages').setAttribute('aria-busy', 'false');
  }
}
$('messages').addEventListener('scroll', () => {
  if (chatHistory.ready && $('messages').scrollTop < 120) run(() => loadHistory());
});
$('history-retry').onclick = () => run(async () => {
  await loadHistory(!chatHistory.ready);
  if (chatHistory.ready) { await poll(); if (!connected) await connect(); }
});

async function connect() {
  $('connect').disabled = true; $('connection-state').textContent = t("ui.connecting.to.codex");
  const projectId = current.id, version = viewVersion;
  try {
    const settings = {model: $('model').value || null, effort: $('effort').value || null, service_tier: $('speed').value};
    try { await api(`projects/${projectId}/connect`, settings); }
    catch (error) {
      if (!error.restartRequired || version !== viewVersion) throw error;
      notice(error.message, true);
      if (!window.confirm(t("ui.codex.is.not.responding.restarting.the.connection.may"))) throw error;
      await api(`projects/${projectId}/connect`, {...settings, restart: true});
    }
    if (version !== viewVersion) return;
    connected = true;
    notice(''); await poll();
  } catch (error) {
    if (version === viewVersion) {
      connected = false; $('connection-state').textContent = t("ui.not.connected");
    }
    throw error;
  } finally { $('connect').disabled = false; }
}

function addMessage(kind, text, target = $('messages')) {
  const node = element('div', 'message ' + kind);
  node.append(element('span', 'role', kind === 'user' ? t("ui.you") : kind === 'agent' ? t('html.codex.2') : t("ui.activity")));
  const body = element('div', '', text); node.append(body); target.append(node); return {node, body};
}
function renderAgent(record, text) {
  record.rawText = text;
  const visible = text.replaceAll('[[HARNESS:SHOW_SUMMARY]]', '');
  const parts = document.createDocumentFragment();
  record.images ||= new Map();
  // Keep code examples as text and render only explicit Markdown image references.
  const pattern = /```[\s\S]*?(?:```|$)|`[^`\n]+`|!?\[([^\]\n]*)\]\((<[^>\n]+>|[^\n]+?)\)/g;
  let offset = 0;
  for (const match of visible.matchAll(pattern)) {
    if (match[1] === undefined) continue;
    let path = match[2].replace(/^<|>$/g, '').trim();
    if (!match[0].startsWith('!') && !/\.(png|jpe?g|gif|webp|bmp|avif)(?:[?#].*)?$/i.test(path)) continue;
    if (/^[a-z][a-z\d+.-]*:/i.test(path) && !/^https?:\/\//i.test(path) && !/^[a-z]:[\\/]/i.test(path)) continue;
    if (!/^https?:\/\//i.test(path)) { try { path = decodeURIComponent(path); } catch (_) {} }
    parts.append(document.createTextNode(visible.slice(offset, match.index)));
    let image = record.images.get(path);
    if (!image) {
      image = chatImage(path, match[1]); record.images.set(path, image);
    }
    parts.append(image); offset = match.index + match[0].length;
  }
  parts.append(document.createTextNode(visible.slice(offset)));
  record.body.replaceChildren(parts);
  record.node.hidden = !visible;
}

function chatImage(path, alt = '', source = null) {
  const frame = element('figure', 'chat-image'), image = element('img'), status = element('span', 'muted');
  image.alt = alt || path; image.referrerPolicy = 'no-referrer';
  frame.append(image, status);
  const version = viewVersion, projectId = current.id;
  const failed = () => { image.hidden = true; status.textContent = t("ui.could.not.load.image", path); };
  image.onerror = failed;
  if (source) image.src = source;
  else if (/^https?:\/\//i.test(path)) image.src = path;
  else api(`projects/${projectId}/image?path=${encodeURIComponent(path)}`).then(result => {
    if (version === viewVersion) image.src = `data:${result.mime};base64,${result.data}`;
  }).catch(failed);
  return frame;
}

function generatedImageSource(result) {
  if (typeof result !== 'string' || result.length > 24 * 1024 * 1024) return null;
  const data = result.replace(/^data:image\/(?:png|jpeg|gif|webp);base64,/, '');
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(data)) return null;
  const mime = data.startsWith('iVBORw0KGgo') ? 'image/png' : data.startsWith('/9j/') ? 'image/jpeg' :
    data.startsWith('R0lGOD') ? 'image/gif' : data.startsWith('UklGR') ? 'image/webp' : null;
  return mime ? `data:${mime};base64,${data}` : null;
}
function userMessageText(text) {
  // Decode only known reply envelopes for display; preserve the original event.
  try {
    const wrapped = text.trim().match(/^<send_user_message_question_reply>\s*([\s\S]*?)\s*<\/send_user_message_question_reply>$/);
    const value = JSON.parse(wrapped ? wrapped[1] : text);
    const replies = wrapped ? value : value?.type === 'question_answers' ? value.answers : null;
    if (!Array.isArray(replies) || !replies.length) return text;
    if (!replies.every(r => typeof r?.question === 'string' &&
        typeof (wrapped ? r.answer : r.user_quote) === 'string')) return text;
    return replies.map(r => `${r.question}\n${wrapped ? r.answer : r.skipped ? t("ui.skip") : r.user_quote}`).join('\n\n');
  } catch (_) { return text; }
}
function showEvent(event, target = $('messages'), historical = false) {
  // Keep the original event log; terminal execution is not conversation content.
  if (event.kind === 'command_delta' ||
      (event.kind === 'item' && event.item.type === 'commandExecution')) return;
  if (event.kind === 'instruction_sent') {
    const entry = element('details', 'instruction-entry');
    entry.append(element('summary', '', `${event.sent_at} · ${event.section} · v${event.version}`));
    entry.append(element('pre', '', t("ui.file.file.sha.text.sha.conversation.turn.method", event.path, event.sha256, event.text_sha256, event.thread_id, event.turn_id || t("ui.applied.on.connection"), event.method, event.text)));
    entry.dataset.seq = event.seq;
    const history = $('instruction-history');
    const next = [...history.children].find(node => Number(node.dataset.seq) < event.seq);
    history.insertBefore(entry, next || null);
  } else if (event.kind === 'agent_delta') {
    let record = itemNodes.get(event.item_id);
    if (!record) { record = addMessage('agent', '', target); itemNodes.set(event.item_id, record); }
    renderAgent(record, (record.rawText || '') + event.text);
  } else if (event.kind === 'user' || ['error', 'blocked', 'disconnected', 'model_selected'].includes(event.kind)) {
    const record = addMessage(event.kind, event.kind === 'user' ? userMessageText(event.text) : event.text, target);
    if (event.kind === 'user' && event.attachments?.length) renderMessageAttachments(record.node, event.attachments);
    if (!historical && event.kind === 'disconnected') notice(t("ui.codex.disconnected"), true);
  } else if (event.kind === 'startup') {
    const node = element('div', 'message'); const details = element('details');
    details.append(element('summary', '', t("ui.automatic.startup.message")), element('pre', '', event.text));
    node.append(details); target.append(node);
  } else if (event.kind === 'item') {
    const item = event.item;
    if (historical && itemNodes.has(item.id)) return;
    if (item.type === 'agentMessage') {
      if (item.questions?.length) return;
      let record = itemNodes.get(item.id);
      if (!record) { record = addMessage('agent', '', target); itemNodes.set(item.id, record); }
      if (item.text) renderAgent(record, item.text);
    } else if (item.type === 'imageGeneration' && event.phase === 'completed') {
      if (itemNodes.has(item.id)) return;
      const source = generatedImageSource(item.result);
      if (!source && !item.savedPath) return;
      const record = addMessage('agent', '', target);
      record.body.append(chatImage(item.savedPath || '', '', source)); itemNodes.set(item.id, record);
    } else if (item.type === 'commandExecution' || item.type === 'fileChange') {
      let record = itemNodes.get(item.id);
      if (!record) {
        const node = element('details', 'command'), label = element('summary'), body = element('pre');
        node.append(label, body); target.append(node); record = {node, label, body}; itemNodes.set(item.id, record);
      }
      const title = item.type === 'commandExecution' ? item.command : (item.changes || []).map(c => c.path).join(', ');
      record.label.textContent = (event.phase === 'completed' ? (item.status === 'failed' ? t("ui.failed") : t("ui.done.2")) : t("ui.in.progress.2")) + title;
      const output = item.type === 'commandExecution' ? item.aggregatedOutput : JSON.stringify(item.changes, null, 2);
      if (output) record.body.textContent = output;
    }
  } else if (event.kind === 'command_delta') {
    const record = itemNodes.get(event.item_id); if (record) record.body.textContent += event.text;
  } else if (event.kind === 'turn_completed' && event.error) {
    addMessage('error', event.error.message || JSON.stringify(event.error), target);
  }
}

async function poll() {
  if (!current || polling || !chatHistory.ready) return;
  polling = true; const id = current.id, version = viewVersion;
  try {
    const result = await api(`projects/${id}/events?after=${cursor}`);
    if (version !== viewVersion) return;
    const box = $('messages'), follow = box.scrollHeight - box.scrollTop - box.clientHeight < 100;
    for (const event of result.events) { showEvent(event); cursor = event.seq; }
    if (connected && !result.connected) notice(t("ui.codex.disconnected"), true);
    connected = result.connected; working = result.working; activity = result.activity || null;
    if (result.project.model && document.activeElement !== $('model')) $('model').value = result.project.model;
    if (document.activeElement !== $('effort')) renderEfforts(result.project.info?.requested_effort);
    if (document.activeElement !== $('speed')) renderSpeeds(result.project.info?.requested_service_tier);
    $('connection-state').textContent = connected ? (working ? t("ui.codex.is.working") : t("ui.connected")) : t("ui.not.connected");
    $('working-label').textContent = working ? t("ui.you.can.send.messages.while.work.continues") : '';
    $('stop').hidden = !working; $('connect').hidden = connected;
    $('model').disabled = false;
    updateSendButton();
    renderPlanning(result.progress);
    window.Workbench?.render(result);
    window.AssetUI?.attention(result.asset_counts);
    if (!$('tab-assets').hidden) await window.AssetUI?.load();
    renderQuestions(result.progress?.show_summary ? [] : result.questions); renderEnvironment(result.project); renderContext(result.project.info?.token_usage);
    renderActivity();
    if (follow) box.scrollTop = box.scrollHeight;
  } catch (error) {
    if (version === viewVersion) $('codex-activity').hidden = true;
    throw error;
  } finally { polling = false; }
}

function renderActivity() {
  const labels = {thinking: t("ui.thinking"), responding: t("ui.writing.a.reply"), planning: t("ui.preparing.the.plan"),
    command: t("ui.running.a.command"), editing: t("ui.editing.files"), reading: t("ui.reading.files"),
    file_search: t("ui.searching.files"), listing: t("ui.listing.files"), web_search: t("ui.searching.the.web"),
    tool: t("ui.using.a.tool"), image_view: t("ui.viewing.an.image"), image_generation: t("ui.generating.an.image"),
    compacting: t("ui.compacting.conversation")};
  $('codex-activity-label').textContent = sending ? t("ui.sending.request") : labels[activity] || t("ui.working");
  $('codex-activity').hidden = !current || !connected || !(sending || working)
    || (!sending && activity === 'waiting');
}

function renderPlanning(value) {
  if (!value) return;
  planning = value;
  renderProduction(value.production);
  const total = value.categories.length;
  const confirmed = value.categories.filter(category => category.status === "confirmed").length;
  $('planning-count').textContent = t("ui.confirmed.categories.2", confirmed, total);
  $('planning-bar').max = total || 1;
  $('planning-bar').value = confirmed;
  $('spec-version').textContent = value.spec_version ? `SPEC v${value.spec_version}` : '';
  $('show-summary').hidden = !!value.spec_version || value.show_summary;
  const names = {confirmed: t("ui.confirmed"), proposed: t("ui.proposed"), undecided: t("ui.undecided")};
  const key = value.fingerprint;
  if (key !== planningKey) {
    planningKey = key; $('planning-checklist').replaceChildren(); $('summary-items').replaceChildren();
    for (const category of value.categories) {
      const row = element('div', 'planning-row');
      row.append(element('span', '', t(category.label)), element('span', '', names[category.status]));
      $('planning-checklist').append(row);
      $('summary-items').append(element('h4', '', t(category.label)));
      const list = element('ul');
      if (!category.items.length) list.append(element('li', '', t("ui.undecided")));
      for (const item of category.items) list.append(element('li', '', `[${names[item.status]}] ${item.topic}: ${item.decision} (${item.id})`));
      $('summary-items').append(list);
    }
  }
  $('planning-summary').hidden = !value.show_summary;
  if (value.show_summary && !summaryVisible) {
    appearance.right = false; applyAppearance();
    document.querySelector('[data-tab="progress"]').click();
  }
  summaryVisible = value.show_summary;
  $('summary-start').disabled = summaryBusy || working || !connected || !value.categories.some(c => c.items.length);
  $('summary-more').disabled = summaryBusy || working;
}

function renderProduction(production) {
  const started = !!production?.started;
  $('production-progress').hidden = !started;
  $('progress-title').textContent = started ? t("ui.production.progress") : t("ui.design.progress");
  if (productionStarted !== started) $('planning-details').open = !started;
  productionStarted = started;
  if (!started) return;
  const key = JSON.stringify(production);
  if (key === productionKey) return;
  productionKey = key;
  $('milestone-count').textContent = t("ui.milestones.complete", production.completed, production.total);
  $('milestone-bar').max = production.total || 1;
  $('milestone-bar').value = production.completed;
  $('milestone-bar').hidden = !!production.error || !production.total;
  const card = $('current-milestone'); card.replaceChildren();
  const names = {pending: t("ui.wait"), active: t("ui.in.progress"), done: t("ui.done"), blocked: t("ui.blocked")};
  const currentMilestone = production.current || production.milestones.find(m => m.status === 'blocked');
  if (production.error) {
    $('milestone-count').textContent = t("ui.milestone.records.need.attention");
    card.append(element('p', '', t(production.error)));
  } else if (currentMilestone) {
    card.append(element('small', '', names[currentMilestone.status]),
                element('h3', '', `${currentMilestone.id} · ${currentMilestone.title}`));
    const progress = currentMilestone.progress;
    if (progress) {
      card.append(element('p', '', t("ui.tasks.complete", progress.completed, progress.total)));
      const bar = element('progress'); bar.max = progress.total; bar.value = progress.completed;
      bar.setAttribute('aria-label', t("ui.completed.tasks.in.the.current.milestone")); card.append(bar);
      card.append(element('p', '', progress.note));
      if (progress.updated_at) card.append(element('small', '', t("ui.last.update", new Date(progress.updated_at).toLocaleString(I18n.locale))));
    } else card.append(element('p', 'muted', t("ui.no.detailed.progress.recorded")));
    card.append(element('p', '', t("ui.done.when", currentMilestone.done_condition)));
  } else {
    card.append(element('p', '', !production.total ? t("ui.waiting.for.milestone.plan") :
      production.completed === production.total ? t("ui.all.milestones.complete") : t("ui.no.active.milestone")));
  }
  $('milestone-list').replaceChildren();
  for (const milestone of production.milestones) {
    const entry = element('details');
    entry.append(element('summary', '', `${names[milestone.status]} · ${milestone.id} · ${milestone.title}`));
    entry.append(element('p', '', t("ui.done.when", milestone.done_condition)));
    if (milestone.not_doing) entry.append(element('p', 'muted', t("ui.out.of.scope", milestone.not_doing)));
    if (window.Workbench) entry.append(Workbench.targetButton('milestone', milestone.id));
    $('milestone-list').append(entry);
  }
}

async function summaryAction(action) {
  if (!planning || summaryBusy) return;
  const id = current.id, version = viewVersion, fingerprint = planning.fingerprint;
  summaryBusy = true; renderPlanning(planning);
  try {
    const result = await api(`projects/${id}/summary-${action}`, {fingerprint});
    if (version === viewVersion) { renderPlanning(result); notice(''); await poll(); }
  } catch (error) {
    if (version === viewVersion) renderPlanning(await api(`projects/${id}/progress`));
    throw error;
  } finally { summaryBusy = false; if (planning) renderPlanning(planning); }
}

function renderQuestions(questions) {
  const key = JSON.stringify(questions.map(q => q.id)); if (key === lastQuestionKey) return;
  lastQuestionKey = key; $('questions').replaceChildren();
  for (const group of questions) {
    const card = element('div', 'question-card'), inputs = [];
    for (const question of group.questions) {
      card.append(element('h4', '', question.title));
      const options = element('div', 'options'), input = element('textarea');
      input.rows = 2;
      input.placeholder = t("ui.or.type.your.answer.shift.enter.for.a"); input.setAttribute('aria-label', question.title + t("ui.custom.answer"));
      for (const option of question.options || []) {
        const node = button(option, () => { input.value = option; for (const b of options.children) b.classList.toggle('selected', b === node); input.focus(); });
        options.append(node);
      }
      input.addEventListener('input', () => { for (const b of options.children) b.classList.remove('selected'); });
      card.append(options, input); inputs.push(input);
    }
    const actions = element('div', 'question-actions');
    let submitting = false;
    const answer = async skip => {
      if (submitting) return;
      const answers = inputs.map(input => skip ? '' : input.value);
      if (!skip && answers.some(a => !a.trim())) throw new Error(t("ui.choose.an.answer.or.type.your.own"));
      submitting = true;
      for (const b of actions.children) b.disabled = true;
      let accepted = false;
      try { await projectApi('answer', {id: group.id, answers}); accepted = true; notice(''); await poll(); }
      finally { if (!accepted) { submitting = false; for (const b of actions.children) b.disabled = false; } }
    };
    for (const input of inputs) input.addEventListener('keydown', event => {
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
        event.preventDefault();
        if (!event.repeat) run(() => answer(false));
      }
    });
    actions.append(button(t("ui.skip"), () => answer(true)), button(t("ui.send.answer"), () => answer(false), 'primary'));
    card.append(actions); $('questions').append(card);
  }
}

function renderEnvironment(project) {
  const info = project.info || {}, list = element('dl');
  for (const [label, value] of [
    [t("ui.project.name"), project.name], [t("ui.project.folder"), project.path],
    [t("ui.conversation.id"), project.thread_id || t("ui.not.created.yet")], [t("ui.model"), info.model || t("ui.not.connected.2")],
    [t("ui.instructions.loaded.by.codex"), (info.instruction_sources || []).join('\n') || t("ui.available.after.connecting")],
    [t("ui.dashboard.instruction.file"), info.instruction_bundle?.path || t("ui.available.after.connecting")],
    [t("ui.dashboard.instruction.version"), info.instruction_bundle ? `v${info.instruction_bundle.version}\nSHA-256: ${info.instruction_bundle.sha256}` : t("ui.available.after.connecting")],
    [t("ui.writable.folders"), (info.writable_roots || []).join('\n') || t("ui.not.connected.2")],
    [t("ui.writes.outside.the.project"), t("ui.not.allowed")]]) { list.append(element('dt', '', label), element('dd', '', value)); }
  $('environment').replaceChildren(list);
}

async function loadUsage() {
  const result = await api('usage'); $('quota-details').replaceChildren();
  if (!result.available) {
    $('quota-brief').textContent = t("ui.usage.unavailable");
    $('quota-details').append(element('p', 'muted', t(result.message))); return;
  }
  const namedBuckets = Object.values(result.rateLimitsByLimitId || {});
  const buckets = namedBuckets.length ? namedBuckets : [result.rateLimits];
  const brief = [];
  for (const bucket of buckets) {
    if (!bucket) continue;
    const card = element('div', 'quota-card'); card.append(element('h3', '', bucket.limitName || bucket.limitId || t('product.codex')));
    for (const window of [bucket.primary, bucket.secondary]) {
      if (!window || typeof window.usedPercent !== 'number') continue;
      const remaining = Math.max(0, Math.min(100, 100 - window.usedPercent));
      const mins = window.windowDurationMins;
      const label = mins ? (mins % 1440 === 0 ? t("ui.days", mins / 1440) : mins % 60 === 0 ? t("ui.hours", mins / 60) : t("ui.minutes", mins)) : t("ui.usage.limit");
      const reset = window.resetsAt ? new Date(window.resetsAt * 1000).toLocaleString(I18n.locale) : t("ui.unavailable");
      card.append(element('p', '', t("ui.limit.remaining", label, remaining)));
      const progress = element('progress'); progress.max = 100; progress.value = remaining; card.append(progress);
      card.append(element('small', 'muted', t("ui.resets", reset)));
      if (brief.length < 2) brief.push(t("ui.remaining", label, remaining));
    }
    if (bucket.credits?.unlimited) card.append(element('p', 'muted', t("ui.credits.unlimited")));
    else if (bucket.credits?.balance != null) card.append(element('p', 'muted', t("ui.credit.balance", bucket.credits.balance)));
    if (bucket.rateLimitReachedType) card.append(element('p', 'muted', t("ui.you.have.reached.the.current.usage.limit")));
    $('quota-details').append(card);
  }
  $('quota-brief').textContent = brief.join(' · ') || t("ui.usage.unavailable");
}

function renderContext(usage) {
  if (!usage) {
    $('context-brief').textContent = t("ui.context.awaiting.response");
    $('context-details').textContent = t("ui.token.information.will.appear.when.codex.reports.it"); return;
  }
  const input = usage.last?.inputTokens, limit = usage.modelContextWindow;
  const format = value => typeof value === 'number' ? value.toLocaleString(I18n.locale) : t("ui.unavailable");
  $('context-brief').textContent = t("ui.context", format(input), format(limit));
  $('context-details').textContent = t("ui.latest.input.tokens.context.limit.tokens.latest.output", format(input), format(limit), format(usage.last?.outputTokens), format(usage.total?.totalTokens));
}

async function loadFiles() {
  const id = current?.id; if (!id) return;
  const result = await api(`projects/${id}/files`); if (id !== current?.id) return;
  $('file-list').replaceChildren();
  for (const file of result.files) $('file-list').append(button(file, () => readFile(file)));
}
async function readFile(path) {
  const version = viewVersion;
  const result = await projectApi('file?path=' + encodeURIComponent(path));
  if (version !== viewVersion) return;
  openFile = path; fileDigest = result.digest;
  $('file-name').textContent = path; $('editor').value = result.text; $('editor-panel').hidden = false;
  $('editor').readOnly = path === '.project' || path.startsWith('.harness/'); $('save-file').hidden = $('editor').readOnly;
  if (/\.html?$/i.test(path)) $('preview-path').value = path;
}
async function loadRecords() {
  if (!current) return;
  const version = viewVersion;
  const result = await projectApi('records'); if (version !== viewVersion) return;
  $('records').replaceChildren();
  const names = {user_decisions: t("ui.user.decision"), work_decisions: t("ui.work.decisions"), user_references: t("ui.references")};
  for (const [table, records] of Object.entries(result)) {
    $('records').append(element('h3', '', `${names[table]} · ${records.length}`));
    if (!records.length) $('records').append(element('p', 'muted', t("ui.no.saved.records")));
    for (const record of records) {
      const card = element('div', 'record');
      card.append(element('small', '', `${record.id} · ${record.category || record.area || record.kind} · ${record.status || ''}`));
      card.append(element('div', '', (record.topic ? record.topic + ': ' : '') + (record.decision || record.title_or_url)));
      if (window.Workbench) card.append(Workbench.targetButton({user_decisions: 'user', work_decisions: 'work', user_references: 'reference'}[table], record.id));
      if (table === 'user_references') {
        card.append(referenceDetails(record)); $('records').append(card); continue;
      }
      const details = element('details'); details.append(element('summary', '', t("ui.view.original.text.and.reasoning")), element('pre', '', JSON.stringify(record, null, 2)));
      card.append(details); $('records').append(card);
    }
  }
}
function renderUploads() {
  $('attachments').replaceChildren();
  for (const attachment of uploads) {
    const card = element('div', 'attachment-card');
    if (attachment.preview) {
      const image = element('img'); image.src = attachment.preview; image.alt = attachment.name;
      card.append(image);
    }
    card.append(element('span', 'attachment-name', attachment.name));
    if (!attachment.path) card.append(element('small', 'muted', t("ui.uploading")));
    const remove = button('×', () => { removeUpload(attachment); renderUploads(); }, 'attachment-remove');
    remove.setAttribute('aria-label', t("ui.remove.attachment", attachment.name));
    card.append(remove); $('attachments').append(card);
  }
  updateSendButton();
}
function updateSendButton() {
  $('send').disabled = !connected || sending || uploads.some(file => !file.path);
  renderActivity();
}
function removeUpload(attachment) {
  if (attachment.preview) URL.revokeObjectURL(attachment.preview);
  uploads = uploads.filter(file => file !== attachment);
}
function clearUploads() {
  for (const attachment of [...uploads]) removeUpload(attachment);
}
async function attachFiles(files) {
  if (!current) return;
  const version = viewVersion, projectId = current.id;
  const errors = [];
  // Show every selected file immediately, and keep send disabled until uploads finish.
  const pending = [];
  for (const file of files) {
    if (file.size > 16 * 1024 * 1024) { errors.push(t("ui.attachments.must.be.mb.or.smaller")); continue; }
    const extension = { 'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp', 'image/gif': 'gif' }[file.type];
    const name = file.name || `image-${Date.now()}.${extension || 'png'}`;
    const attachment = {name, path: null, preview: file.type.startsWith('image/') ? URL.createObjectURL(file) : null};
    uploads.push(attachment); pending.push({file, attachment});
  }
  renderUploads();
  for (const {file, attachment} of pending) {
    if (version !== viewVersion) return;
    if (!uploads.includes(attachment)) continue;
    try {
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(',')[1]);
        reader.onerror = () => reject(new Error(t("ui.could.not.read.the.file")));
        reader.readAsDataURL(file);
      });
      if (version !== viewVersion || !uploads.includes(attachment)) continue;
      const result = await api(`projects/${projectId}/upload`, {name: attachment.name, data});
      if (version !== viewVersion) return;
      if (uploads.includes(attachment)) attachment.path = result.path;
    } catch (error) {
      if (version !== viewVersion) return;
      removeUpload(attachment); errors.push(error.message);
    }
    renderUploads();
  }
  if (version !== viewVersion) return;
  if (errors.length) notice([...new Set(errors)].join('\n'));
  await loadFiles();
}
function renderMessageAttachments(node, paths) {
  const projectId = current.id, version = viewVersion;
  const gallery = element('div', 'message-attachments'); node.append(gallery);
  for (const path of paths) {
    if (!/\.(png|jpe?g|gif|webp|bmp|avif)$/i.test(path)) continue;
    const image = element('img'); image.alt = path.split('/').pop();
    image.style.visibility = 'hidden'; gallery.append(image);
    api(`projects/${projectId}/attachment?path=${encodeURIComponent(path)}`).then(result => {
      if (version !== viewVersion || !image.isConnected) return;
      image.src = `data:${result.mime};base64,${result.data}`; image.style.visibility = '';
    }).catch(() => { image.style.visibility = ''; });
  }
}

$('new-project').onclick = $('welcome-create').onclick = () => { $('create-dialog').showModal(); $('project-name').focus(); };
$('cancel-create').onclick = () => $('create-dialog').close();
$('create-form').onsubmit = event => { event.preventDefault(); run(async () => {
  $('create-submit').disabled = true;
  try { selectedModel = $('model').value; const {project} = await api('projects', {name: $('project-name').value}); $('create-dialog').close(); $('project-name').value = ''; await openProject(project); }
  finally { $('create-submit').disabled = false; }
}); };
$('home-link').onclick = event => { event.preventDefault(); clearUploads(); sending = false; viewVersion++; current = null; $('home').hidden = false; $('workspace').hidden = true; $('folder').hidden = true; $('page-title').textContent = t("ui.where.ideas.become.games"); $('connection-state').textContent = t("ui.select.a.project"); notice(''); run(loadProjects); };
$('connect').onclick = () => run(connect);
$('reconnect').onclick = () => run(async () => {
  $('reconnect').disabled = true;
  try { if (current) await connect(); else { await loadStatus(); notice(''); } }
  finally { $('reconnect').disabled = false; }
});
$('show-summary').onclick = () => run(async () => renderPlanning(await projectApi('summary', {})));
$('summary-start').onclick = () => run(() => summaryAction('start'));
$('summary-more').onclick = () => run(() => summaryAction('more'));
$('model').onchange = () => run(async () => {
  renderEfforts();
  renderSpeeds($('speed').value);
  if (!current || !connected) { selectedModel = $('model').value; return; }
  await saveModelSettings();
});
async function saveModelSettings() {
  const result = await projectApi('model', {model: $('model').value, effort: $('effort').value || null, service_tier: $('speed').value});
  $('model').value = result.model; renderEfforts(result.effort); renderSpeeds(result.service_tier);
  notice(t("ui.model.reasoning.effort.and.speed.settings.apply.to"));
}
$('effort').onchange = () => run(async () => { if (current && connected) await saveModelSettings(); });
$('speed').onchange = () => run(async () => { if (current && connected) await saveModelSettings(); });
$('login').onclick = () => {
  const popup = window.open('about:blank', '_blank');
  run(async () => { try {
    const result = await api('login', {}); $('login-link').href = result.url; $('login-link').hidden = false;
    if (popup) popup.location = result.url;
    notice(t("ui.complete.codex.sign.in.then.connect.to.the"));
  } catch (error) { popup?.close(); throw error; } });
};
$('folder').onclick = () => run(() => projectApi('folder', {}));
$('sandbox-setup').onclick = () => run(async () => { await api('sandbox', {}); notice(t("ui.preparing.windows.permissions.complete.the.administrator.prompt.when")); await loadStatus(); });
$('composer').onsubmit = event => { event.preventDefault(); run(async () => {
  if ($('send').disabled) return;
  const text = $('message').value; if (!text.trim() && !uploads.length) return;
  const version = viewVersion, attached = [...uploads], target = window.Workbench?.currentTarget();
  sending = true; updateSendButton();
  try {
    const result = await projectApi('message', {text, attachments: attached.map(file => file.path), target});
    if (version !== viewVersion) return;
    if (typeof result.working === 'boolean') { working = result.working; activity = result.activity || null; }
    if ($('message').value === text) $('message').value = '';
    window.Workbench?.clear(target);
    for (const attachment of attached) removeUpload(attachment);
    renderUploads(); notice(''); await poll();
  } finally { if (version === viewVersion) { sending = false; updateSendButton(); } }
}); };
$('message').onkeydown = event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229 && !event.repeat) { event.preventDefault(); if (!$('send').disabled) $('composer').requestSubmit(); } };
$('stop').onclick = () => run(() => projectApi('interrupt', {}));
$('upload').onchange = () => {
  const files = [...$('upload').files]; $('upload').value = '';
  run(() => attachFiles(files));
};
$('message').addEventListener('paste', event => {
  const files = [...(event.clipboardData?.files || [])].filter(file => file.type.startsWith('image/'));
  if (!files.length) return; // Ordinary text and links keep their normal paste behavior.
  event.preventDefault(); run(() => attachFiles(files));
});
const dropZone = document.querySelector('.chat-panel');
let dragDepth = 0;
const isFileDrag = event => [...(event.dataTransfer?.types || [])].includes('Files');
const clearDrop = () => { dragDepth = 0; dropZone.classList.remove('file-dragover'); };
dropZone.addEventListener('dragenter', event => {
  if (!current || !isFileDrag(event)) return;
  event.preventDefault(); dragDepth++; dropZone.classList.add('file-dragover');
});
dropZone.addEventListener('dragleave', () => { if (--dragDepth <= 0) clearDrop(); });
dropZone.addEventListener('dragover', event => {
  if (!current || !isFileDrag(event)) return;
  event.preventDefault(); event.dataTransfer.dropEffect = 'copy';
});
dropZone.addEventListener('drop', event => {
  clearDrop(); if (!current || !isFileDrag(event)) return;
  event.preventDefault(); run(() => attachFiles([...event.dataTransfer.files]));
});
// A file dropped outside the chat must not navigate away from the dashboard.
window.addEventListener('dragover', event => { if (isFileDrag(event)) event.preventDefault(); });
window.addEventListener('drop', event => { if (isFileDrag(event)) event.preventDefault(); clearDrop(); });
window.addEventListener('dragend', clearDrop);
$('refresh-files').onclick = () => run(loadFiles); $('refresh-records').onclick = () => run(loadRecords);
$('save-file').onclick = () => run(async () => { const result = await projectApi('file', {path: openFile, text: $('editor').value, digest: fileDigest}); fileDigest = result.digest; notice(t("ui.file.saved")); });
$('preview-button').onclick = () => run(async () => {
  const version = viewVersion;
  const result = await projectApi('preview', {path: $('preview-path').value});
  if (version !== viewVersion) return;
  $('preview-frame').src = result.url;
  $('preview-link').href = result.url; $('preview-link').textContent = result.url; $('preview-actions').hidden = false;
});
$('preview-fullscreen').onclick = () => run(async () => { await $('preview-frame').requestFullscreen(); });
$('preview-copy').onclick = () => run(async () => { await navigator.clipboard.writeText($('preview-link').href); notice(t("ui.preview.url.copied")); });
$('usage-button').onclick = () => { $('usage-dialog').showModal(); run(loadUsage); };
$('close-usage').onclick = () => $('usage-dialog').close();
$('refresh-usage').onclick = () => run(loadUsage);
for (const tab of document.querySelectorAll('[data-tab]')) tab.onclick = () => run(async () => {
  if (tab.dataset.tab !== 'creator') window.LiveWorkspace?.leave();
  for (const node of document.querySelectorAll('[data-tab]')) node.classList.toggle('active', node === tab);
  for (const node of document.querySelectorAll('.tab-content')) node.hidden = node.id !== 'tab-' + tab.dataset.tab;
  if (tab.dataset.tab === 'records') await loadRecords();
  if (tab.dataset.tab === 'assets') await window.AssetUI?.load();
  if (tab.dataset.tab === 'creator') await window.Creator?.load();
  if (tab.dataset.tab === 'discards') await window.Workbench?.loadDiscards();
  if (tab.dataset.tab === 'files') await loadFiles();
});
run(async () => {
  await I18n.load();
  if (!token) { I18n.apply(navigator.language); applyAppearance(); throw new Error(t("ui.open.the.dashboard.using.the.launcher.or.start")); }
  let settings = await api('preferences');
  if (!settings.language) settings = await api('preferences', {language: I18n.normalize(navigator.language)});
  I18n.apply(settings.language); applyAppearance();
  $('app-version').textContent = 'v' + settings.version;
  await loadProjects(); await loadStatus();
});
setInterval(() => { if (current) run(poll); }, 900);
setInterval(() => { if (!$('login').hidden || !$('sandbox-setup').hidden || sandboxPending) run(loadStatus); }, 5000);
setInterval(() => { if (connected) run(loadUsage); }, 60000);
