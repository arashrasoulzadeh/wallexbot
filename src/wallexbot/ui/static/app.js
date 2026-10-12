/* Shared helpers for every page: translations, API calls, safe DOM building, saved config.
   No third-party scripts: everything the UI needs is served from /static. */
(function () {
  'use strict';

  const KEYS = { lang: 'wb.lang', config: 'wb.config', paperRun: 'wb.paperRun' };

  function read(key) { try { return window.localStorage.getItem(key); } catch (e) { return null; } }
  function write(key, value) { try { window.localStorage.setItem(key, value); } catch (e) { /* private mode */ } }
  function remove(key) { try { window.localStorage.removeItem(key); } catch (e) { /* private mode */ } }

  let dictionary = { en: {}, fa: {} };

  const wb = {
    KEYS: KEYS,
    read: read, write: write, remove: remove,

    lang() { return read(KEYS.lang) === 'fa' ? 'fa' : 'en'; },

    /* Translate a key; {name} placeholders are filled from vars. Falls back to English, then the key. */
    t(key, vars) {
      const table = dictionary[wb.lang()] || {};
      let text = table[key] !== undefined ? table[key] : (dictionary.en[key] !== undefined ? dictionary.en[key] : key);
      if (vars) { Object.keys(vars).forEach(function (k) { text = text.split('{' + k + '}').join(vars[k]); }); }
      return text;
    },

    /* Apply the current language to the page: text, direction, the language selector. */
    apply() {
      const lang = wb.lang();
      document.documentElement.lang = lang;
      document.documentElement.dir = lang === 'fa' ? 'rtl' : 'ltr';
      document.querySelectorAll('[data-i18n]').forEach(function (node) {
        node.textContent = wb.t(node.getAttribute('data-i18n'));
      });
      document.querySelectorAll('[data-i18n-title]').forEach(function (node) {
        node.title = wb.t(node.getAttribute('data-i18n-title'));
      });
      const select = document.getElementById('lang-select');
      if (select) { select.value = lang; }
      document.dispatchEvent(new CustomEvent('wb:lang', { detail: lang }));
    },

    setLang(lang) { write(KEYS.lang, lang === 'fa' ? 'fa' : 'en'); wb.apply(); },

    /* JSON request; throws an Error with a readable message on any non-2xx answer. */
    async api(path, options) {
      const response = await fetch(path, options);
      const text = await response.text();
      let body = text;
      try { body = JSON.parse(text); } catch (e) { /* keep text */ }
      if (!response.ok) { throw new Error(wb.describeError(body, response.status)); }
      return body;
    },

    post(path, body) {
      return wb.api(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {})
      });
    },

    describeError(body, status) {
      if (body && typeof body === 'object' && body.detail !== undefined) {
        const detail = body.detail;
        if (Array.isArray(detail)) {
          return detail.map(function (d) { return d.msg || JSON.stringify(d); }).join('; ');
        }
        return String(detail);
      }
      return typeof body === 'string' && body ? body : 'HTTP ' + status;
    },

    /* Build a DOM node from plain text only, so nothing from the API can inject markup. */
    el(tag, props) {
      const node = document.createElement(tag);
      Object.keys(props || {}).forEach(function (name) {
        if (name === 'class') { node.className = props[name]; }
        else if (name === 'text') { node.textContent = props[name]; }
        else if (name.indexOf('on') === 0) { node.addEventListener(name.slice(2), props[name]); }
        else { node.setAttribute(name, props[name]); }
      });
      for (let i = 2; i < arguments.length; i++) {
        const child = arguments[i];
        if (child === null || child === undefined) { continue; }
        node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
      }
      return node;
    },

    clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } return node; },

    /* Number formatting for display only (the server keeps exact decimals). */
    num(value, maxFraction) {
      if (value === null || value === undefined || value === '') { return '--'; }
      const n = Number(value);
      if (!isFinite(n)) { return String(value); }
      return n.toLocaleString('en-US', { maximumFractionDigits: maxFraction === undefined ? 2 : maxFraction });
    },
    pct(value, digits) {
      if (value === null || value === undefined) { return '--'; }
      const n = Number(value);
      return (n >= 0 ? '+' : '') + n.toFixed(digits === undefined ? 2 : digits) + '%';
    },
    signClass(value) { const n = Number(value); return n > 0 ? 'pos' : (n < 0 ? 'neg' : ''); },
    time(ms) { return ms ? new Date(Number(ms)).toLocaleString() : '--'; },

    badge(state) {
      return wb.el('span', { class: 'badge ' + state, text: wb.t('state.' + state) });
    },

    /* The configuration the user saved (or the server's defaults). */
    config: {
      load() {
        const raw = read(KEYS.config);
        if (!raw) { return null; }
        try { return JSON.parse(raw); } catch (e) { return null; }
      },
      save(cfg) { write(KEYS.config, JSON.stringify(cfg)); },
      clear() { remove(KEYS.config); },
      async current() { return wb.config.load() || wb.api('/api/config/default'); }
    }
  };

  window.wb = wb;
  wb.ready = new Promise(function (resolve) {
    document.addEventListener('DOMContentLoaded', function () {
      fetch('/static/i18n.json').then(function (r) { return r.json(); }).then(function (data) {
        dictionary = data;
      }).catch(function () { /* keys are shown as-is */ }).then(function () {
        const select = document.getElementById('lang-select');
        if (select) { select.addEventListener('change', function () { wb.setLang(select.value); }); }
        wb.apply();
        resolve();
      });
    });
  });
})();
