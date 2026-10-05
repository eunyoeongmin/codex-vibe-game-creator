'use strict';
// Only explicit UI strings and the initial static markup use this catalog.
// Conversation text, filenames, decision values and editor contents stay untouched.
const I18n = {
  locale: 'ko', catalog: {}, bindings: [],
  normalize(value) {
    const code = String(value || '').toLowerCase();
    if (code.startsWith('zh')) return /hant|tw|hk|mo/.test(code) ? 'zh-Hant' : 'zh-Hans';
    return ['ko', 'en', 'ja'].find(v => code.startsWith(v)) || 'en';
  },
  async load() {
    const response = await fetch('/locales.json');
    if (!response.ok) throw new Error('Cannot load interface translations.');
    this.catalog = await response.json();
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode, original = node.textContent;
      if (this.catalog[original.trim()]) this.bindings.push({node, original});
    }
    for (const node of document.querySelectorAll('[placeholder], [aria-label], [title]')) {
      for (const attr of ['placeholder', 'aria-label', 'title']) {
        const original = node.getAttribute(attr);
        if (this.catalog[original]) this.bindings.push({node, attr, original});
      }
    }
  },
  apply(language) {
    this.locale = this.normalize(language);
    document.documentElement.lang = this.locale;
    document.getElementById('language').value = this.locale;
    for (const {node, attr, original} of this.bindings) {
      if (!node.isConnected) continue;
      if (attr) node.setAttribute(attr, t(original));
      else node.textContent = original.replace(original.trim(), t(original.trim()));
    }
  }
};
function t(key, ...args) {
  if (typeof key !== 'string') return key;
  const translated = I18n.catalog[key]?.[I18n.locale] || key;
  return translated.replace(/\{(\d+)\}/g, (match, index) => index < args.length ? String(args[index]) : match);
}
