/* Reference provenance is read from the DB, never inferred from chat text. */
function referenceDetails(record) {
  const details = element('details', 'reference-details');
  details.append(element('summary', '', t('조사·해석·적용 보기')));
  const content = element('div', 'reference-trace');
  details.append(content);
  let loading = false, loaded = false;
  async function load() {
    if (!details.open || loading || loaded || !current) return;
    loading = true;
    const projectId = current.id, version = viewVersion;
    content.replaceChildren(element('p', 'muted', t('불러오는 중…')));
    try {
      const data = await api(`projects/${projectId}/reference?id=${encodeURIComponent(record.id)}`);
      if (version !== viewVersion || current?.id !== projectId) return;
      renderReferenceTrace(content, data, projectId);
      loaded = true;
    } catch (error) {
      content.replaceChildren(element('p', 'muted', error.message));
      content.append(button(t('다시 시도'), load));
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
      row.append(button(t('이미지 보기'), () => run(async () => {
        const result = await api(`projects/${projectId}/image?path=${encodeURIComponent(path)}`);
        if (current?.id !== projectId || !row.isConnected) return;
        row.querySelector('img')?.remove();
        const img = element('img', 'reference-image');
        img.src = `data:${result.mime};base64,${result.data}`; img.alt = path;
        row.append(img);
      })));
    } else {
      row.append(button(t('파일 보기'), () => run(async () => {
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
      a.href = value; a.target = '_blank'; a.rel = 'noopener noreferrer'; parent.append(a);
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
  field(container, t('사용자 원문'), record.user_note);
  field(container, t('참고 요소'), record.aspects.join(' · '));
  if (record.file_path) file(container, record.file_path);
  const stageNames = {research: t('조사 근거'), interpretation: t('참고 해석'), application: t('적용 연결')};
  const stateNames = {planned: t('적용 예정'), applied: t('적용 기록'), dropped: t('채택하지 않음')};
  const trace = record.trace || [];
  function entry(row) {
    const card = element('article', 'reference-entry'); card.tabIndex = -1; card.dataset.traceId = row.id;
    card.append(element('h4', '', `${row.id} · ${row.topic}`), element('small', 'muted', new Date(row.created_at).toLocaleString(I18n.locale)));
    if (row.superseded_by) field(card, t('대체한 기록'), row.superseded_by);
    if (row.outdated_basis) card.append(element('p', 'reference-review', t('근거가 변경됨 · 적용 재검토 필요')));
    const p = row.payload;
    if (row.stage === 'research') {
      source(card, p.source);
      field(card, t('근거 위치'), p.locator);
      field(card, t('관찰 내용'), p.observation);
      field(card, t('확인하지 못한 부분'), p.limitations);
    } else if (row.stage === 'interpretation') {
      links(card, t('조사 근거'), p.research_ids);
      field(card, t('AI 해석'), p.meaning);
    } else {
      links(card, t('참고 해석'), p.interpretation_ids);
      field(card, t('적용 상태'), stateNames[p.state]);
      field(card, t('적용 설계'), p.plan);
      field(card, t('원본·설계와의 차이'), p.differences);
      for (const f of p.files) file(card, f.path, f.location);
      field(card, t('연결된 결정'), p.decision_ids.join(' · '));
      field(card, t('연결된 에셋'), p.asset_ids.join(' · '));
      if (p.asset_versions && Object.keys(p.asset_versions).length) field(card, t('에셋 기록 버전'),
        Object.entries(p.asset_versions).map(([id, revision]) => `${id} · v${revision}`).join(' / '));
    }
    field(card, t('선택·변경 이유'), row.reason);
    const quote = element('details'); quote.append(element('summary', '', t('원문과 근거 보기')));
    field(quote, t('사용자 원문'), row.user_quote);
    field(quote, t('AI 답변 원문'), row.assistant_reply);
    card.append(quote);
    return card;
  }
  for (const [stage, name] of Object.entries(stageNames)) {
    container.append(element('h3', '', name));
    const rows = trace.filter(r => r.stage === stage && !r.superseded_by);
    if (!rows.length) container.append(element('p', 'muted', t('아직 기록되지 않았습니다.')));
    for (const row of rows) container.append(entry(row));
  }
  const past = trace.filter(r => r.superseded_by);
  if (past.length) {
    const history = element('details'); history.append(element('summary', '', t('이전 기록과 변경 이력')));
    for (const row of past) history.append(entry(row));
    container.append(history);
  }
  container.append(element('h3', '', t('연결된 결정·에셋')));
  if (!record.linked_decisions.length && !record.linked_assets.length) container.append(element('p', 'muted', t('아직 기록되지 않았습니다.')));
  for (const decision of record.linked_decisions) {
    const card = element('details', 'reference-entry');
    card.append(element('summary', '', `${decision.id} · ${decision.topic || decision.area} · ${decision.decision}`));
    field(card, t('상태'), decision.status);
    field(card, t('대체한 기록'), decision.superseded_by);
    field(card, t('사용자 원문'), decision.user_quote);
    field(card, t('AI 답변 원문'), decision.assistant_reply);
    field(card, t('선택·변경 이유'), decision.reason);
    container.append(card);
  }
  for (const asset of record.linked_assets) {
    const card = element('details', 'reference-entry');
    card.append(element('summary', '', `${asset.id} · v${asset.revision} · ${asset.name}`));
    field(card, t('상태'), asset.status);
    field(card, t('사용 상황·용도'), asset.usage);
    for (const path of asset.files) file(card, path);
    container.append(card);
  }
}
