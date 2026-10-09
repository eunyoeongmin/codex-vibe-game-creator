/* Reference provenance is read from the DB, never inferred from chat text. */
function referenceDetails(record) {
  const details = element('details', 'reference-details');
  details.append(element('summary', '', t("ui.research.interpretation.and.use")));
  const content = element('div', 'reference-trace');
  details.append(content);
  let loading = false, loaded = false;
  async function load() {
    if (!details.open || loading || loaded || !current) return;
    loading = true;
    const projectId = current.id, version = viewVersion;
    content.replaceChildren(element('p', 'muted', t("ui.loading")));
    try {
      const data = await api(`projects/${projectId}/reference?id=${encodeURIComponent(record.id)}`);
      if (version !== viewVersion || current?.id !== projectId) return;
      renderReferenceTrace(content, data, projectId);
      loaded = true;
    } catch (error) {
      content.replaceChildren(element('p', 'muted', error.message));
      content.append(button(t("ui.retry"), load));
    } finally { loading = false; }
  }
  details.addEventListener('toggle', () => { if (details.open) load(); });
  return details;
}

function renderReferenceTrace(container, record, projectId) {
  container.replaceChildren();
  function field(parent, label, value) {
    if (value === undefined || value === null || value === '') return;
    const block = element('div', 'reference-field');
    block.append(element('strong', '', label), element('div', '', value));
    parent.append(block);
  }
  function file(parent, path, location = '') {
    const row = element('div', 'reference-file');
    row.append(element('span', '', path + (location ? ` · ${location}` : '')));
    if (/\.(png|jpe?g|webp|gif|bmp|avif)$/i.test(path)) {
      row.append(button(t("ui.view.image"), () => run(async () => {
        const result = await api(`projects/${projectId}/image?path=${encodeURIComponent(path)}`);
        if (current?.id !== projectId || !row.isConnected) return;
        row.querySelector('img')?.remove();
        const img = element('img', 'reference-image');
        img.src = `data:${result.mime};base64,${result.data}`; img.alt = path;
        row.append(img);
      })));
    } else {
      row.append(button(t("ui.view.file"), () => run(async () => {
        if (current?.id !== projectId) return;
        document.querySelector('[data-tab="files"]').click();
        await readFile(path);
      })));
    }
    parent.append(row);
  }
  function source(parent, value) {
    if (/^https?:\/\//i.test(value)) {
      const a = element('a', '', value);
      a.href = value; a.target = '_blank'; a.rel = HarnessText.raw("js.creator.noopener.noreferrer"); parent.append(a);
    } else if (value) file(parent, value);
  }
  function links(parent, label, ids) {
    if (!ids?.length) return;
    const row = element('div', 'reference-links'); row.append(element('strong', '', label));
    for (const id of ids) row.append(button(id, () => {
      const target = container.querySelector(`[data-trace-id="${CSS.escape(id)}"]`);
      if (!target) return;
      for (let node = target.parentElement; node && node !== container; node = node.parentElement) {
        if (node.tagName === 'DETAILS') node.open = true;
      }
      target.scrollIntoView({block: 'nearest'}); target.focus({preventScroll: true});
    }));
    parent.append(row);
  }
  field(container, t("ui.original.user.statement"), record.user_note);
  field(container, t("ui.selected.aspects"), record.aspects.join(' · '));
  if (record.file_path) file(container, record.file_path);
  const stageNames = {research: t("ui.research.evidence"), interpretation: t("ui.reference.interpretation"), application: t("ui.application.links")};
  const stateNames = {planned: t("ui.planned"), applied: t("ui.recorded.application"), dropped: t("ui.not.adopted")};
  const trace = record.trace || [];
  function entry(row) {
    const card = element('article', 'reference-entry'); card.tabIndex = -1; card.dataset.traceId = row.id;
    card.append(element('h4', '', `${row.id} · ${row.topic}`), element('small', 'muted', new Date(row.created_at).toLocaleString(I18n.locale)));
    if (row.superseded_by) field(card, t("ui.superseded.by"), row.superseded_by);
    if (row.outdated_basis) card.append(element('p', 'reference-review', t("ui.basis.changed.review.application")));
    const p = row.payload;
    if (row.stage === 'research') {
      source(card, p.source);
      field(card, t("ui.evidence.location"), p.locator);
      field(card, t("ui.observed.facts"), p.observation);
      field(card, t("ui.not.established"), p.limitations);
    } else if (row.stage === 'interpretation') {
      links(card, t("ui.research.evidence"), p.research_ids);
      field(card, t("ui.ai.interpretation"), p.meaning);
    } else {
      links(card, t("ui.reference.interpretation"), p.interpretation_ids);
      field(card, t("ui.usage.state"), stateNames[p.state]);
      field(card, t("ui.application.design"), p.plan);
      field(card, t("ui.differences.from.source.or.plan"), p.differences);
      for (const f of p.files) file(card, f.path, f.location);
      field(card, t("ui.linked.decisions"), p.decision_ids.join(' · '));
      field(card, t("ui.linked.assets"), p.asset_ids.join(' · '));
      if (p.asset_versions && Object.keys(p.asset_versions).length) field(card, t("ui.recorded.asset.versions"),
        Object.entries(p.asset_versions).map(([id, revision]) => `${id} · v${revision}`).join(' / '));
    }
    field(card, t("ui.selection.or.change.reason"), row.reason);
    const quote = element('details'); quote.append(element('summary', '', t("ui.view.original.text.and.reasoning")));
    field(quote, t("ui.original.user.statement"), row.user_quote);
    field(quote, t("ui.original.ai.response"), row.assistant_reply);
    card.append(quote);
    return card;
  }
  for (const [stage, name] of Object.entries(stageNames)) {
    container.append(element('h3', '', name));
    const rows = trace.filter(r => r.stage === stage && !r.superseded_by);
    if (!rows.length) container.append(element('p', 'muted', t("ui.not.recorded.yet")));
    for (const row of rows) container.append(entry(row));
  }
  const past = trace.filter(r => r.superseded_by);
  if (past.length) {
    const history = element('details'); history.append(element('summary', '', t("ui.previous.records.and.changes")));
    for (const row of past) history.append(entry(row));
    container.append(history);
  }
  container.append(element('h3', '', t("ui.linked.decisions.and.assets")));
  if (!record.linked_decisions.length && !record.linked_assets.length) container.append(element('p', 'muted', t("ui.not.recorded.yet")));
  for (const decision of record.linked_decisions) {
    const card = element('details', 'reference-entry');
    card.append(element('summary', '', `${decision.id} · ${decision.topic || decision.area} · ${decision.decision}`));
    field(card, t("ui.status"), decision.status);
    field(card, t("ui.superseded.by"), decision.superseded_by);
    field(card, t("ui.original.user.statement"), decision.user_quote);
    field(card, t("ui.original.ai.response"), decision.assistant_reply);
    field(card, t("ui.selection.or.change.reason"), decision.reason);
    container.append(card);
  }
  for (const asset of record.linked_assets) {
    const card = element('details', 'reference-entry');
    card.append(element('summary', '', `${asset.id} · v${asset.revision} · ${asset.name}`));
    field(card, t("ui.status"), asset.status);
    field(card, t("ui.where.and.when.it.is.used"), asset.usage);
    for (const path of asset.files) file(card, path);
    container.append(card);
  }
}
