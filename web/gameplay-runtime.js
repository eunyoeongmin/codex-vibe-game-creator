'use strict';
// Game-owned adapters keep engine objects and executable code out of save records.
(() => {
  if (window.GameCreatorPlay) return;
  let adapter = null, busy = false, catalog = {}, base = '', language = '';
  const clone = value => {
    const encoded = JSON.stringify(value);
    if (!encoded || encoded.length > 2000000) throw new Error(HarnessText.raw("js.gameplay.runtime.save.state.exceeds.mb"));
    return JSON.parse(encoded);
  };
  function available() { if (!adapter) throw new Error(HarnessText.raw("js.gameplay.runtime.save.adapter.is.not.connected")); return adapter; }
  async function locked(fn) {
    if (busy) throw new Error(HarnessText.raw("js.gameplay.runtime.a.play.state.operation.is.already.running"));
    busy = true; try { return await fn(); } finally { busy = false; }
  }
  async function capture() {
    const a = available(), state = clone(await a.capture());
    if (!state || typeof state !== 'object') throw new Error(HarnessText.raw("js.gameplay.runtime.state.must.be.a.json.object.or.array"));
    return {adapter: a.id, version: a.version, state};
  }
  async function migrate(saved) {
    const a = available(), value = clone(saved);
    if (value.adapter !== a.id) throw new Error(HarnessText.raw("js.gameplay.runtime.this.save.belongs.to.a.different.game.adapter"));
    if (!Number.isInteger(value.version) || value.version < 1 || value.version > a.version) throw new Error(HarnessText.raw("js.gameplay.runtime.unsupported.save.version"));
    let state = value.state;
    for (let version = value.version; version < a.version; version++) {
      const migration = a.migrations?.[version];
      if (typeof migration !== 'function') throw new Error(HarnessText.raw("js.gameplay.runtime.missing.migration.from.save.version") + version);
      state = clone(await migration(clone(state)));
    }
    if (!state || typeof state !== 'object') throw new Error(HarnessText.raw("js.gameplay.runtime.state.must.be.a.json.object.or.array"));
    if (a.validate && await a.validate(clone(state)) !== true) throw new Error(HarnessText.raw("js.gameplay.runtime.save.validation.failed"));
    return {adapter: a.id, version: a.version, state};
  }
  window.GameCreatorPlay = {
    register(value) {
      if (busy) throw new Error(HarnessText.raw("js.gameplay.runtime.cannot.replace.the.save.adapter.during.an.operation"));
      if (!value || typeof value.id !== 'string' || !value.id || !Number.isInteger(value.version) || value.version < 1 || typeof value.capture !== 'function' || typeof value.restore !== 'function') throw new Error(HarnessText.raw("js.gameplay.runtime.invalid.save.adapter"));
      adapter = value;
    },
    info: () => adapter ? {adapter: adapter.id, version: adapter.version} : null,
    capture: () => locked(capture),
    migrate: saved => locked(() => migrate(saved)),
    restore: saved => locked(async () => {
      const next = await migrate(saved), previous = await capture();
      try { await adapter.restore(clone(next.state)); }
      catch (error) {
        try { await adapter.restore(previous.state); }
        catch (rollback) { throw new Error(HarnessText.raw("js.gameplay.runtime.restore.and.rollback.failed") + error.message + ' / ' + rollback.message); }
        throw error;
      }
      return next;
    })
  };
  window.GameCreatorStrings = {
    async load(url, options = {}) {
      const response = await fetch(url); if (!response.ok) throw new Error(HarnessText.raw("js.gameplay.runtime.cannot.load.game.strings"));
      const data = await response.json();
      if (!data[options.base]) throw new Error(HarnessText.raw("js.gameplay.runtime.missing.base.language"));
      catalog = data; base = options.base; language = options.locale || base;
      window.dispatchEvent(new CustomEvent('game-language-change', {detail: language}));
    },
    setLanguage(locale) {
      if (!catalog[locale]) throw new Error(HarnessText.raw("js.gameplay.runtime.unknown.game.language"));
      language = locale; window.dispatchEvent(new CustomEvent('game-language-change', {detail: locale}));
    },
    languages: () => Object.keys(catalog),
    text(key, values = {}) {
      const source = catalog[language]?.[key] || catalog[base]?.[key];
      if (typeof source !== 'string') throw new Error(HarnessText.raw("js.gameplay.runtime.missing.game.string") + key);
      return source.replace(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g, (_, name) => {
        if (!Object.hasOwn(values, name)) throw new Error(HarnessText.raw("js.gameplay.runtime.missing.string.variable") + name);
        return String(values[name]);
      });
    },
    issues() {
      const found = [];
      for (const node of document.querySelectorAll('[data-game-string]')) {
        if (node.getClientRects().length && (node.scrollWidth > node.clientWidth + 1 || node.scrollHeight > node.clientHeight + 1))
          found.push({key: node.dataset.gameString, locale: language, type: 'overflow', text: node.textContent?.slice(0, 300)});
      }
      return {locale: language, languages: Object.keys(catalog), issues: found,
        coverage: HarnessText.raw("js.gameplay.runtime.visible.dom.elements.with.data.game.string.only")};
    }
  };
})();
