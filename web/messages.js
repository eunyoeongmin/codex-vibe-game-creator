'use strict';
// The JSON catalog is the sole source of wording. This helper also runs offline.
globalThis.HarnessText = (() => {
  const sourceKeys = new Map(Object.entries(globalThis.HarnessMessages).map(([key, entry]) => [entry.source, key]));
  const format = (value, args) => value.replace(/\{(\d+)\}/g,
    (match, index) => index < args.length ? String(args[index]) : match);
  function keyOf(value) {
    if (Object.hasOwn(globalThis.HarnessMessages, value)) return value;
    return sourceKeys.get(value);
  }
  return {
    raw(key, ...args) { return format(globalThis.HarnessMessages[key].source, args); },
    text(value, locale = 'ko', ...args) {
      if (typeof value !== 'string') return value;
      const entry = globalThis.HarnessMessages[keyOf(value)];
      return format(entry?.[locale] ?? entry?.source ?? value, args);
    }
  };
})();
