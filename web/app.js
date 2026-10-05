'use strict';
const $ = id => document.getElementById(id);
const fragment = new URLSearchParams(location.hash.slice(1));
const token = fragment.get('token') || sessionStorage.getItem('harness-token');
if (fragment.has('token')) { sessionStorage.setItem('harness-token', token); history.replaceState(null, '', '/'); }
let current = null, cursor = 0, projects = [], polling = false, connected = false, working = false;
let uploads = [], openFile = null, fileDigest = null, selectedModel = '', lastQuestionKey = '', viewVersion = 0;
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
  const labels = {left: t('왼쪽'), right: t('오른쪽'), top: t('상단')};
  for (const panel of Object.keys(labels)) {
    document.body.classList.toggle(`${panel}-collapsed`, appearance[panel]);
    const label = t('{0} 패널 {1}', labels[panel], appearance[panel] ? t('펼치기') : t('접기'));
    $(`toggle-${panel}`).setAttribute('aria-label', label);
    $(`toggle-${panel}`).title = label;
    $(`toggle-${panel}`).setAttribute('aria-expanded', String(!appearance[panel]));
    $(`reveal-${panel}`)?.setAttribute('aria-label', t('{0} 패널 {1}', labels[panel], t('펼치기')));
  }
  for (const panel of ['left', 'right', 'top']) {
    const [min, max] = panelBounds(panel), value = Math.round(Math.max(min, Math.min(max, appearance.sizes[panel])));
    document.body.style.setProperty(`--${panel}-${panel === 'top' ? 'height' : 'width'}`, value + 'px');
    for (const [key, number] of Object.entries({min, max, now: value})) $(`resize-${panel}`).setAttribute(`aria-value${key}`, String(number));
  }
  document.documentElement.dataset.theme = appearance.theme;
  $('toggle-theme').textContent = appearance.theme === 'dark' ? t('화이트 모드') : t('다크 모드');
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
  edge.setAttribute('aria-label', t('{0} 패널 {1}', {left: t('왼쪽'), right: t('오른쪽'), top: t('상단')}[panel], t('펼치기')));
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
  I18n.apply(settings.language); applyAppearance();
  planningKey = ''; productionKey = ''; if (planning) renderPlanning(planning);
  // Keep drafts, editor changes and question answers when changing languages.
  for (const card of $('questions').children) {
    const buttons = card.querySelector('.question-actions')?.children;
    if (buttons) { buttons[0].textContent = t('건너뛰기'); buttons[1].textContent = t('답변 보내기'); }
    for (const input of card.querySelectorAll('input')) input.placeholder = t('직접 입력할 수도 있어요');
  }
  if (!current) $('page-title').textContent = t('아이디어가 게임이 되는 곳');
  await loadProjects(); await loadStatus();
  if (current) { await poll(); if (!$('tab-records').hidden) await loadRecords(); }
  notice(t('대화 언어는 다음 작업부터 적용됩니다.'));
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
  catch (_) { const error = new Error(t('대시보드 연결이 끊어졌습니다.')); error.reconnect = true; throw error; }
  const result = await response.json();
  if (!response.ok) { const error = new Error(t(result.error) || t('요청에 실패했습니다.')); error.reconnect = response.status >= 500; throw error; }
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
  $('project-count').textContent = t('{0}개 프로젝트', projects.length);
  for (const project of projects) {
    $('project-list').append(button(project.name, () => openProject(project), current?.id === project.id ? 'selected' : ''));
    const card = button('', () => openProject(project), 'project-card');
    card.append(element('strong', '', project.name), element('small', '', t('작업실 열기 ↗')));
    $('project-cards').append(card);
  }
  if (!projects.length) $('project-cards').append(element('p', 'empty', t('아직 프로젝트가 없습니다. 이름을 정해 첫 작업실을 만들어 보세요.')));
}

async function loadStatus() {
  const status = await api('status');
  $('account-label').textContent = t(status.error) || (status.account ? t('Codex 연결됨 · {0}', status.account.planType || status.account.type) : t('게임 제작을 시작하려면 로그인하세요'));
  $('login').hidden = !!status.account;
  if (status.account) $('login-link').hidden = true;
  const wasPending = sandboxPending;
  sandboxPending = status.sandbox_readiness !== 'ready' && status.sandbox_setup?.success === null;
  $('sandbox-setup').hidden = status.sandbox_setup?.success !== false || !!status.error;
  $('sandbox-setup').disabled = status.sandbox_setup?.success === null;
  $('sandbox-status').textContent = status.sandbox_readiness === 'ready' ? '' :
    t(status.sandbox_setup?.error) || (sandboxPending ? t('작업 권한 자동 설정 중 · Windows 관리자 확인 창을 완료해 주세요.') : t('작업 권한 확인 중'));
  modelCatalog = status.models || [];
  const previous = $('model').value;
  $('model').replaceChildren(new Option(t('Codex 기본 모델'), ''));
  for (const model of status.models || []) $('model').add(new Option(model.displayName || model.model, model.model));
  $('model').value = previous;
  renderEfforts($('effort').value);
  if (wasPending && status.sandbox_readiness === 'ready' && current && !connected && !$('connect').disabled) await connect();
  return status;
}

function renderEfforts(preferred) {
  const model = modelCatalog.find(m => m.model === $('model').value) || modelCatalog.find(m => m.isDefault);
  const efforts = model?.supportedReasoningEfforts || [];
  $('effort').replaceChildren();
  const labels = {none: t('없음'), minimal: t('최소'), low: t('낮음'), medium: t('보통'), high: t('높음'), xhigh: t('매우 높음'), ultra: t('최대')};
  for (const item of efforts) {
    const value = item.reasoningEffort;
    const option = new Option(`${labels[value] || value} (${value})`, value);
    option.title = item.description || ''; $('effort').add(option);
  }
  $('effort').value = efforts.some(e => e.reasoningEffort === preferred) ? preferred : (model?.defaultReasoningEffort || '');
  $('effort').disabled = !efforts.length;
}

async function openProject(project) {
  viewVersion++; current = project; cursor = 0; itemNodes.clear(); lastQuestionKey = ''; uploads = [];
  connected = working = false; openFile = fileDigest = null;
  planning = null; planningKey = ''; summaryVisible = false;
  productionKey = ''; productionStarted = null;
  $('planning-summary').hidden = true;
  $('home').hidden = true; $('workspace').hidden = false; $('folder').hidden = false;
  $('page-title').textContent = project.name; $('messages').replaceChildren(); $('questions').replaceChildren();
  $('instruction-history').replaceChildren();
  $('message').value = ''; $('editor-panel').hidden = true; $('preview-frame').removeAttribute('src');
  $('model').value = project.model || selectedModel; renderEfforts(); renderUploads(); notice('');
  await loadProjects(); await loadFiles(); await poll(); await loadUsage();
  if (!connected) await connect();
}

async function connect() {
  $('connect').disabled = true; $('connection-state').textContent = t('Codex 연결 중');
  try {
    await projectApi('connect', {model: $('model').value || null, effort: $('effort').value || null}); connected = true;
    notice(''); await poll();
  } finally { $('connect').disabled = false; }
}

function addMessage(kind, text) {
  const node = element('div', 'message ' + kind);
  node.append(element('span', 'role', kind === 'user' ? t('나') : kind === 'agent' ? 'CODEX' : t('작업 안내')));
  const body = element('div', '', text); node.append(body); $('messages').append(node); return {node, body};
}
function renderAgent(record, text) {
  record.rawText = text;
  record.body.textContent = text.replaceAll('[[HARNESS:SHOW_SUMMARY]]', '');
  record.node.hidden = !record.body.textContent;
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
    return replies.map(r => `${r.question}\n${wrapped ? r.answer : r.skipped ? t('건너뛰기') : r.user_quote}`).join('\n\n');
  } catch (_) { return text; }
}
function showEvent(event) {
  // Keep the original event log; terminal execution is not conversation content.
  if (event.kind === 'command_delta' ||
      (event.kind === 'item' && event.item.type === 'commandExecution')) return;
  if (event.kind === 'instruction_sent') {
    const entry = element('details', 'instruction-entry');
    entry.append(element('summary', '', `${event.sent_at} · ${event.section} · v${event.version}`));
    entry.append(element('pre', '', t('파일: {0}\n파일 SHA-256: {1}\n본문 SHA-256: {2}\n대화: {3}\n턴: {4}\n전달: {5}\n\n{6}', event.path, event.sha256, event.text_sha256, event.thread_id, event.turn_id || t('연결 시 적용'), event.method, event.text)));
    $('instruction-history').prepend(entry);
  } else if (event.kind === 'agent_delta') {
    let record = itemNodes.get(event.item_id);
    if (!record) { record = addMessage('agent', ''); itemNodes.set(event.item_id, record); }
    renderAgent(record, (record.rawText || '') + event.text);
  } else if (event.kind === 'user' || ['error', 'blocked', 'disconnected', 'model_selected'].includes(event.kind)) {
    addMessage(event.kind, event.kind === 'user' ? userMessageText(event.text) : event.text);
    if (event.kind === 'disconnected') notice(t('Codex 연결이 끊어졌습니다.'), true);
  } else if (event.kind === 'startup') {
    const node = element('div', 'message'); const details = element('details');
    details.append(element('summary', '', t('자동 시작 안내를 보냈습니다')), element('pre', '', event.text));
    node.append(details); $('messages').append(node);
  } else if (event.kind === 'item') {
    const item = event.item;
    if (item.type === 'agentMessage') {
      if (item.questions?.length) return;
      let record = itemNodes.get(item.id);
      if (!record) { record = addMessage('agent', ''); itemNodes.set(item.id, record); }
      if (item.text) renderAgent(record, item.text);
    } else if (item.type === 'commandExecution' || item.type === 'fileChange') {
      let record = itemNodes.get(item.id);
      if (!record) {
        const node = element('details', 'command'), label = element('summary'), body = element('pre');
        node.append(label, body); $('messages').append(node); record = {node, label, body}; itemNodes.set(item.id, record);
      }
      const title = item.type === 'commandExecution' ? item.command : (item.changes || []).map(c => c.path).join(', ');
      record.label.textContent = (event.phase === 'completed' ? (item.status === 'failed' ? t('실패 · ') : t('완료 · ')) : t('진행 · ')) + title;
      const output = item.type === 'commandExecution' ? item.aggregatedOutput : JSON.stringify(item.changes, null, 2);
      if (output) record.body.textContent = output;
    }
  } else if (event.kind === 'command_delta') {
    const record = itemNodes.get(event.item_id); if (record) record.body.textContent += event.text;
  } else if (event.kind === 'turn_completed' && event.error) {
    addMessage('error', event.error.message || JSON.stringify(event.error));
  }
}

async function poll() {
  if (!current || polling) return;
  polling = true; const id = current.id, version = viewVersion;
  try {
    const result = await api(`projects/${id}/events?after=${cursor}`);
    if (version !== viewVersion) return;
    const box = $('messages'), follow = box.scrollHeight - box.scrollTop - box.clientHeight < 100;
    for (const event of result.events) { showEvent(event); cursor = event.seq; }
    if (connected && !result.connected) notice(t('Codex 연결이 끊어졌습니다.'), true);
    connected = result.connected; working = result.working;
    if (result.project.model && document.activeElement !== $('model')) $('model').value = result.project.model;
    if (document.activeElement !== $('effort')) renderEfforts(result.project.info?.requested_effort);
    $('connection-state').textContent = connected ? (working ? t('Codex 작업 중') : t('대화 연결됨')) : t('연결 대기');
    $('working-label').textContent = working ? t('작업 중에도 메시지를 보낼 수 있어요') : '';
    $('stop').hidden = !working; $('connect').hidden = connected;
    $('model').disabled = false;
    $('send').disabled = !connected;
    renderPlanning(result.progress);
    renderQuestions(result.progress?.show_summary ? [] : result.questions); renderEnvironment(result.project); renderContext(result.project.info?.token_usage);
    if (follow) box.scrollTop = box.scrollHeight;
  } finally { polling = false; }
}

function renderPlanning(value) {
  if (!value) return;
  planning = value;
  renderProduction(value.production);
  const total = value.categories.length;
  const confirmed = value.categories.filter(category => category.status === 'confirmed').length;
  $('planning-count').textContent = t('확정 {0} / {1} 항목', confirmed, total);
  $('planning-bar').max = total || 1;
  $('planning-bar').value = confirmed;
  $('spec-version').textContent = value.spec_version ? `SPEC v${value.spec_version}` : '';
  $('show-summary').hidden = !!value.spec_version || value.show_summary;
  const names = {confirmed: t('확정'), proposed: t('제안'), undecided: t('미결정')};
  const key = value.fingerprint;
  if (key !== planningKey) {
    planningKey = key; $('planning-checklist').replaceChildren(); $('summary-items').replaceChildren();
    for (const category of value.categories) {
      const row = element('div', 'planning-row');
      row.append(element('span', '', t(category.label)), element('span', '', names[category.status]));
      $('planning-checklist').append(row);
      $('summary-items').append(element('h4', '', t(category.label)));
      const list = element('ul');
      if (!category.items.length) list.append(element('li', '', t('미결정')));
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
  $('progress-title').textContent = started ? t('제작 진행') : t('기획 진행');
  if (productionStarted !== started) $('planning-details').open = !started;
  productionStarted = started;
  if (!started) return;
  const key = JSON.stringify(production);
  if (key === productionKey) return;
  productionKey = key;
  $('milestone-count').textContent = t('마일스톤 완료 {0} / {1}', production.completed, production.total);
  $('milestone-bar').max = production.total || 1;
  $('milestone-bar').value = production.completed;
  $('milestone-bar').hidden = !!production.error || !production.total;
  const card = $('current-milestone'); card.replaceChildren();
  const names = {pending: t('대기'), active: t('진행 중'), done: t('완료'), blocked: t('중단')};
  const currentMilestone = production.current || production.milestones.find(m => m.status === 'blocked');
  if (production.error) {
    $('milestone-count').textContent = t('마일스톤 기록 확인 필요');
    card.append(element('p', '', t(production.error)));
  } else if (currentMilestone) {
    card.append(element('small', '', names[currentMilestone.status]),
                element('h3', '', `${currentMilestone.id} · ${currentMilestone.title}`));
    const progress = currentMilestone.progress;
    if (progress) {
      card.append(element('p', '', t('완료 작업 {0} / {1}', progress.completed, progress.total)));
      const bar = element('progress'); bar.max = progress.total; bar.value = progress.completed;
      bar.setAttribute('aria-label', t('현재 마일스톤의 완료 작업 비율')); card.append(bar);
      card.append(element('p', '', progress.note));
      if (progress.updated_at) card.append(element('small', '', t('최근 기록: {0}', new Date(progress.updated_at).toLocaleString(I18n.locale))));
    } else card.append(element('p', 'muted', t('세부 진행 기록 없음')));
    card.append(element('p', '', t('완료 조건: {0}', currentMilestone.done_condition)));
  } else {
    card.append(element('p', '', !production.total ? t('마일스톤 계획 작성 대기') :
      production.completed === production.total ? t('전체 마일스톤 완료') : t('진행 중인 마일스톤 없음')));
  }
  $('milestone-list').replaceChildren();
  for (const milestone of production.milestones) {
    const entry = element('details');
    entry.append(element('summary', '', `${names[milestone.status]} · ${milestone.id} · ${milestone.title}`));
    entry.append(element('p', '', t('완료 조건: {0}', milestone.done_condition)));
    if (milestone.not_doing) entry.append(element('p', 'muted', t('제외: {0}', milestone.not_doing)));
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
      const options = element('div', 'options'), input = element('input');
      input.placeholder = t('직접 입력할 수도 있어요'); input.setAttribute('aria-label', question.title + t(' 직접 입력'));
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
      if (!skip && answers.some(a => !a.trim())) throw new Error(t('답변을 선택하거나 직접 입력해 주세요.'));
      submitting = true;
      for (const b of actions.children) b.disabled = true;
      let accepted = false;
      try { await projectApi('answer', {id: group.id, answers}); accepted = true; notice(''); await poll(); }
      finally { if (!accepted) { submitting = false; for (const b of actions.children) b.disabled = false; } }
    };
    for (const input of inputs) input.addEventListener('keydown', event => {
      if (event.key === 'Enter' && !event.isComposing && event.keyCode !== 229) {
        event.preventDefault();
        if (!event.repeat) run(() => answer(false));
      }
    });
    actions.append(button(t('건너뛰기'), () => answer(true)), button(t('답변 보내기'), () => answer(false), 'primary'));
    card.append(actions); $('questions').append(card);
  }
}

function renderEnvironment(project) {
  const info = project.info || {}, list = element('dl');
  for (const [label, value] of [
    [t('프로젝트 이름'), project.name], [t('프로젝트 폴더'), project.path],
    [t('대화 ID'), project.thread_id || t('아직 생성되지 않음')], [t('모델'), info.model || t('연결 전')],
    [t('Codex가 불러온 시작 문서'), (info.instruction_sources || []).join('\n') || t('연결 후 표시')],
    [t('대시보드 지침 파일'), info.instruction_bundle?.path || t('연결 후 표시')],
    [t('대시보드 지침 버전'), info.instruction_bundle ? `v${info.instruction_bundle.version}\nSHA-256: ${info.instruction_bundle.sha256}` : t('연결 후 표시')],
    [t('쓰기 허용 폴더'), (info.writable_roots || []).join('\n') || t('연결 전')],
    [t('폴더 밖 쓰기 승인'), t('허용하지 않음')]]) { list.append(element('dt', '', label), element('dd', '', value)); }
  $('environment').replaceChildren(list);
}

async function loadUsage() {
  const result = await api('usage'); $('quota-details').replaceChildren();
  if (!result.available) {
    $('quota-brief').textContent = t('사용량 정보 없음');
    $('quota-details').append(element('p', 'muted', t(result.message))); return;
  }
  const buckets = Object.values(result.rateLimitsByLimitId || {default: result.rateLimits});
  const brief = [];
  for (const bucket of buckets) {
    if (!bucket) continue;
    const card = element('div', 'quota-card'); card.append(element('h3', '', bucket.limitName || bucket.limitId || 'Codex'));
    for (const window of [bucket.primary, bucket.secondary]) {
      if (!window || typeof window.usedPercent !== 'number') continue;
      const remaining = Math.max(0, Math.min(100, 100 - window.usedPercent));
      const mins = window.windowDurationMins;
      const label = mins ? (mins % 1440 === 0 ? t('{0}일', mins / 1440) : mins % 60 === 0 ? t('{0}시간', mins / 60) : t('{0}분', mins)) : t('사용 한도');
      const reset = window.resetsAt ? new Date(window.resetsAt * 1000).toLocaleString(I18n.locale) : t('정보 없음');
      card.append(element('p', '', t('{0} 한도 · {1}% 남음', label, remaining)));
      const progress = element('progress'); progress.max = 100; progress.value = remaining; card.append(progress);
      card.append(element('small', 'muted', t('리셋: {0}', reset)));
      if (brief.length < 2) brief.push(t('{0} {1}% 남음', label, remaining));
    }
    if (bucket.credits?.unlimited) card.append(element('p', 'muted', t('크레딧: 무제한')));
    else if (bucket.credits?.balance != null) card.append(element('p', 'muted', t('크레딧 잔액: {0}', bucket.credits.balance)));
    if (bucket.rateLimitReachedType) card.append(element('p', 'muted', t('현재 사용 한도에 도달했습니다.')));
    $('quota-details').append(card);
  }
  $('quota-brief').textContent = brief.join(' · ') || t('사용량 정보 없음');
}

function renderContext(usage) {
  if (!usage) {
    $('context-brief').textContent = t('컨텍스트: 응답 대기');
    $('context-details').textContent = t('Codex가 토큰 정보를 보내면 표시합니다.'); return;
  }
  const input = usage.last?.inputTokens, limit = usage.modelContextWindow;
  const format = value => typeof value === 'number' ? value.toLocaleString(I18n.locale) : t('정보 없음');
  $('context-brief').textContent = t('컨텍스트 {0} / {1}', format(input), format(limit));
  $('context-details').textContent = t('최근 입력: {0} 토큰\n컨텍스트 한도: {1} 토큰\n최근 출력: {2} 토큰\n대화 누적 사용: {3} 토큰\n최근 요청 기준이며, 컨텍스트 압축 후에는 입력량이 달라집니다.', format(input), format(limit), format(usage.last?.outputTokens), format(usage.total?.totalTokens));
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
  const names = {user_decisions: t('사용자 결정'), work_decisions: t('작업 결정'), user_references: t('레퍼런스')};
  for (const [table, records] of Object.entries(result)) {
    $('records').append(element('h3', '', `${names[table]} · ${records.length}`));
    if (!records.length) $('records').append(element('p', 'muted', t('저장된 기록이 없습니다.')));
    for (const record of records) {
      const card = element('div', 'record');
      card.append(element('small', '', `${record.id} · ${record.category || record.area || record.kind} · ${record.status || ''}`));
      card.append(element('div', '', (record.topic ? record.topic + ': ' : '') + (record.decision || record.title_or_url)));
      const details = element('details'); details.append(element('summary', '', t('원문과 근거 보기')), element('pre', '', JSON.stringify(record, null, 2)));
      card.append(details); $('records').append(card);
    }
  }
}
function renderUploads() {
  $('attachments').replaceChildren();
  uploads.forEach((path, index) => $('attachments').append(button(path.split('/').pop() + ' ×', () => { uploads.splice(index, 1); renderUploads(); })));
}

$('new-project').onclick = $('welcome-create').onclick = () => { $('create-dialog').showModal(); $('project-name').focus(); };
$('cancel-create').onclick = () => $('create-dialog').close();
$('create-form').onsubmit = event => { event.preventDefault(); run(async () => {
  $('create-submit').disabled = true;
  try { selectedModel = $('model').value; const {project} = await api('projects', {name: $('project-name').value}); $('create-dialog').close(); $('project-name').value = ''; await openProject(project); }
  finally { $('create-submit').disabled = false; }
}); };
$('home-link').onclick = event => { event.preventDefault(); viewVersion++; current = null; $('home').hidden = false; $('workspace').hidden = true; $('folder').hidden = true; $('page-title').textContent = t('아이디어가 게임이 되는 곳'); $('connection-state').textContent = t('프로젝트를 선택하세요'); notice(''); run(loadProjects); };
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
  if (!current || !connected) { selectedModel = $('model').value; return; }
  await saveModelSettings();
});
async function saveModelSettings() {
  const result = await projectApi('model', {model: $('model').value, effort: $('effort').value || null});
  $('model').value = result.model; renderEfforts(result.effort);
  notice(t('다음 작업부터 {0} / 추론 수준 {1}을 사용합니다.', result.model, result.effort || t('기본값')));
}
$('effort').onchange = () => run(async () => { if (current && connected) await saveModelSettings(); });
$('login').onclick = () => {
  const popup = window.open('about:blank', '_blank');
  run(async () => { try {
    const result = await api('login', {}); $('login-link').href = result.url; $('login-link').hidden = false;
    if (popup) popup.location = result.url;
    notice(t('Codex 로그인 화면에서 로그인을 마친 후 대화 연결을 눌러 주세요.'));
  } catch (error) { popup?.close(); throw error; } });
};
$('folder').onclick = () => run(() => projectApi('folder', {}));
$('sandbox-setup').onclick = () => run(async () => { await api('sandbox', {}); notice(t('Windows 작업 권한을 준비합니다. 관리자 확인 창이 나타나면 설정을 완료해 주세요.')); await loadStatus(); });
$('composer').onsubmit = event => { event.preventDefault(); run(async () => {
  const text = $('message').value; if (!text.trim() && !uploads.length) return;
  $('send').disabled = true;
  try { await projectApi('message', {text, attachments: uploads}); $('message').value = ''; uploads = []; renderUploads(); notice(''); await poll(); }
  finally { $('send').disabled = !connected; }
}); };
$('message').onkeydown = event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229 && !event.repeat) { event.preventDefault(); if (!$('send').disabled) $('composer').requestSubmit(); } };
$('stop').onclick = () => run(() => projectApi('interrupt', {}));
$('upload').onchange = () => run(async () => {
  for (const file of $('upload').files) {
    if (file.size > 16 * 1024 * 1024) throw new Error(t('첨부는 16MB 이하로 선택하세요.'));
    const data = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.onerror = reject; reader.readAsDataURL(file); });
    const result = await projectApi('upload', {name: file.name, data}); uploads.push(result.path);
  }
  $('upload').value = ''; renderUploads(); await loadFiles();
});
$('refresh-files').onclick = () => run(loadFiles); $('refresh-records').onclick = () => run(loadRecords);
$('save-file').onclick = () => run(async () => { const result = await projectApi('file', {path: openFile, text: $('editor').value, digest: fileDigest}); fileDigest = result.digest; notice(t('파일을 저장했습니다.')); });
$('preview-button').onclick = () => run(async () => { const result = await projectApi('preview', {path: $('preview-path').value}); $('preview-frame').src = result.url; });
$('usage-button').onclick = () => { $('usage-dialog').showModal(); run(loadUsage); };
$('close-usage').onclick = () => $('usage-dialog').close();
$('refresh-usage').onclick = () => run(loadUsage);
for (const tab of document.querySelectorAll('[data-tab]')) tab.onclick = () => run(async () => {
  for (const node of document.querySelectorAll('[data-tab]')) node.classList.toggle('active', node === tab);
  for (const node of document.querySelectorAll('.tab-content')) node.hidden = node.id !== 'tab-' + tab.dataset.tab;
  if (tab.dataset.tab === 'records') await loadRecords();
  if (tab.dataset.tab === 'files') await loadFiles();
});
run(async () => {
  await I18n.load();
  if (!token) { I18n.apply(navigator.language); applyAppearance(); throw new Error(t('start.bat으로 대시보드를 열어 주세요.')); }
  let settings = await api('preferences');
  if (!settings.language) settings = await api('preferences', {language: I18n.normalize(navigator.language)});
  I18n.apply(settings.language); applyAppearance();
  $('app-version').textContent = 'v' + settings.version;
  await loadProjects(); await loadStatus();
});
setInterval(() => { if (current) run(poll); }, 900);
setInterval(() => { if (!$('login').hidden || !$('sandbox-setup').hidden || sandboxPending) run(loadStatus); }, 5000);
setInterval(() => { if (connected) run(loadUsage); }, 60000);
