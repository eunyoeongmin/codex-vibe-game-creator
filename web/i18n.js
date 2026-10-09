'use strict';
// Bind only explicit interface text. User content is never translated implicitly.
const I18n = {
  locale: 'ko', bindings: [],
  normalize(value) {
    const code = String(value || '').toLowerCase();
    if (code.startsWith('zh')) return /hant|tw|hk|mo/.test(code) ? 'zh-Hant' : 'zh-Hans';
    return ['ko', 'en', 'ja'].find(v => code.startsWith(v)) || 'en';
  },
  async load() {
    for (const node of document.querySelectorAll('[data-message], [data-message-placeholder], [data-message-aria-label], [data-message-title]')) {
      if (node.dataset.message) this.bindings.push({node, key: node.dataset.message, last: node.textContent});
      for (const attr of ['placeholder', 'aria-label', 'title']) {
        const key = node.getAttribute('data-message-' + attr);
        if (key) this.bindings.push({node, attr, key});
      }
    }
  },
  apply(language) {
    this.locale = this.normalize(language);
    document.documentElement.lang = this.locale;
    document.getElementById('language').value = this.locale;
    for (const binding of this.bindings) {
      const {node, attr, key} = binding;
      if (!node.isConnected) continue;
      if (attr) node.setAttribute(attr, t(key));
      else if (!binding.replaced && node.textContent === binding.last) {
        node.textContent = binding.last = t(key);
      } else binding.replaced = true; // A renderer now owns this title or status.
    }
  }
};
function t(key, ...args) { return HarnessText.text(key, I18n.locale, ...args); }
