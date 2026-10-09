'use strict';
window.Workbench = (() => {
  let chosen = null, owner = null, statusKey = '', discardBusy = false;
  function reset() {
    chosen = null; owner = current?.id; statusKey = '';
    $('request-target').replaceChildren(); $('work-status').replaceChildren();
    $('discard-list').replaceChildren();
  }
  function sync() { if (owner !== current?.id) reset(); }
  async function select(kind, id) {
    sync(); const version = viewVersion;
    const value = await projectApi(`target?kind=${encodeURIComponent(kind)}&id=${encodeURIComponent(id)}`);
    if (version !== viewVersion) return;
    chosen = value;
    $('request-target').replaceChildren(element('span', '', t("ui.target", `${id} · ${value.record.title || value.record.topic || value.record.name || value.record.title_or_url || value.record.decision}`)),
      button(t("ui.clear.target"), () => { chosen = null; $('request-target').replaceChildren(); }));
    $('message').focus();
  }
  function targetButton(kind, id) { return button(t("ui.modify.this.item"), () => select(kind, id)); }
  function currentTarget() { sync(); return chosen && {kind: chosen.kind, id: chosen.id, fingerprint: chosen.fingerprint}; }
  function clear(sent) {
    if (sent && chosen?.fingerprint === sent.fingerprint && chosen?.id === sent.id) {
      chosen = null; $('request-target').replaceChildren();
    }
  }
  function render(result) {
    sync();
    const status = result.work_status, info = result.project.info || {}, production = result.progress?.production;
    const key = JSON.stringify([status, result.working, result.activity, production?.current, info.last_request, info.last_context, I18n.locale]);
    if (key === statusKey) return; statusKey = key;
    const box = $('work-status'); box.replaceChildren();
    const title = production?.current ? `${production.current.id} · ${production.current.title}` : t("ui.no.active.milestone.2");
    box.append(element('strong', '', title));
    const active = status?.plan?.find(step => step.status === 'inProgress');
    const action = active?.step || info.last_request?.slice(0, 180) || t("ui.no.task.recorded");
    box.append(element('div', '', t(active ? HarnessText.raw("ui.current.task") : HarnessText.raw("ui.latest.request"), action)));
    const phase = !result.connected ? t("ui.not.connected") : status?.waiting_for_answer || result.questions?.length ? t("ui.waiting.for.your.answer") :
      result.working ? (result.activity ? t("ui.working.2", activityLabel(result.activity)) : t("ui.codex.is.working")) : t("ui.waiting.for.your.review");
    box.append(element('small', '', phase));
    if (status?.agents?.length) {
      const agents = element('details'); agents.append(element('summary', '', t("ui.agents.actual.tool.events")));
      for (const agent of status.agents) agents.append(element('div', '',
        `${agent.role || agent.name || agent.id} · ${agent.tool || ''} · ${agent.status}`));
      box.append(agents);
    }
    if (status?.plan?.length) {
      const plan = element('details'); plan.append(element('summary', '', t("ui.current.task.plan")));
      for (const step of status.plan) plan.append(element('div', '', `${step.status} · ${step.step}`));
      box.append(plan);
    }
    const context = info.last_context;
    if (context) {
      const details = element('details'); details.append(element('summary', '', t("ui.related.evidence.sent.to.ai")));
      details.append(element('small', 'muted', t("ui.keyword.matches.the.assigned.agent.checks.the.actual")));
      if (context.target) details.append(element('div', '', t("ui.target", context.target.id)));
      for (const record of context.records || []) {
        const item = element('details'); item.append(element('summary', '', `${record.id} · ${record.record.topic || record.record.decision || record.record.name || record.record.title_or_url || record.table}`),
          element('pre', '', JSON.stringify(record.record, null, 2))); details.append(item);
      }
      for (const code of context.code || []) details.append(button(`${code.path}:${code.line}`, async () => {
        document.querySelector('[data-tab="files"]').click(); await readFile(code.path);
        const start = $('editor').value.split('\n').slice(0, code.line - 1).join('\n').length;
        $('editor').focus(); $('editor').setSelectionRange(start, start + code.text.length + 1);
      }), element('pre', '', code.text));
      details.append(element('small', 'muted', t("ui.searched.records.files.bounded.search", context.coverage.records_scanned, context.coverage.files_scanned)));
      box.append(details);
    }
  }
  function activityLabel(value) {
    const names = {thinking: t("ui.thinking"), responding: t("ui.writing.a.reply"), reading: t("ui.reading.files"),
      editing: t("ui.editing.files"), command: t("ui.running.a.command"), planning: t("ui.preparing.the.plan"),
      file_search: t("ui.searching.files"), web_search: t("ui.searching.the.web"), waiting: t("ui.waiting.for.your.answer")};
    return names[value] || t("ui.codex.is.working");
  }
  async function loadDiscards() {
    sync(); const version = viewVersion;
    const result = await projectApi('discards');
    if (version === viewVersion) renderDiscards(result.candidates);
  }
  function renderDiscards(rows) {
    const box = $('discard-list'); box.replaceChildren();
    const labels = {pending: t("ui.awaiting.move"), moved: t("ui.moved.to.discarded.folder"), kept: t("ui.keep"), deleted: t("ui.deleted"),
      moving: t("ui.check.file.state"), deleting: t("ui.check.file.state"), needs_attention: t("ui.check.file.state")};
    const active = rows.filter(row => ['pending', 'moved'].includes(row.state));
    $('discard-total').textContent = t("ui.candidates.mb", active.length, (active.reduce((sum, r) => sum + r.size, 0) / 1048576).toFixed(2));
    if (!rows.length) box.append(element('p', 'muted', t("ui.no.discard.candidates.registered")));
    for (const row of rows) {
      const card = element('article', 'record');
      card.append(element('strong', '', row.path), element('p', '', row.reason),
        element('small', '', `${labels[row.state] || row.state} · ${(row.size / 1024).toFixed(1)} KB · ${row.record_ids}`));
      if (row.destination) card.append(element('div', 'muted', row.destination));
      const actions = element('div', 'workbench-actions');
      for (const [action, label] of row.state === 'pending' ? [['move', t("ui.move.to.discarded")], ['keep', t("ui.keep")]] : row.state === 'moved' ? [['delete', t("ui.delete.permanently")]] : []) {
        const control = button(label, async () => {
          if (discardBusy) return;
          const prompt = action === 'delete' ? t("ui.permanently.delete.this.file.this.cannot.be.undone", row.destination) :
            action === 'move' ? t("ui.move.this.file.to.discarded.moving.a.file", row.path) : '';
          if (prompt && !window.confirm(prompt)) return;
          const version = viewVersion;
          discardBusy = true; control.disabled = true;
          try {
            const result = await projectApi('discard-action', {id: row.id, action, digest: row.digest, confirmation: `${action}:${row.id}:${row.digest}`});
            if (version === viewVersion) renderDiscards(result.candidates);
          } finally { discardBusy = false; control.disabled = false; }
        }); actions.append(control);
      }
      card.append(actions); box.append(card);
    }
  }
  $('discard-refresh').onclick = () => run(loadDiscards);
  $('discard-form').onsubmit = event => { event.preventDefault(); run(async () => {
    const version = viewVersion;
    await projectApi('discard-propose', {path: $('discard-path').value, reason: $('discard-reason').value});
    if (version === viewVersion) { $('discard-form').reset(); await loadDiscards(); }
  }); };
  return {reset, select, targetButton, currentTarget, clear, render, loadDiscards};
})();
