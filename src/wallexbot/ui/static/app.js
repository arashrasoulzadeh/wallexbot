/* Shared helpers for every page: translations, API calls, safe DOM building, saved config.
   No third-party scripts: everything the UI needs is served from /static. */
(function () {
  'use strict';

  const LRM = '\u200E';
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
    /* A left-to-right mark in front keeps a sign with its number on right-to-left pages. */
    num(value, maxFraction) {
      if (value === null || value === undefined || value === '') { return '--'; }
      const n = Number(value);
      if (!isFinite(n)) { return String(value); }
      if (n !== 0 && Math.abs(n) < 0.01) {   // tiny prices (meme coins): significant digits, not decimals
        return LRM + n.toLocaleString('en-US', { maximumSignificantDigits: 4, maximumFractionDigits: 12 });
      }
      return LRM + n.toLocaleString('en-US', { maximumFractionDigits: maxFraction === undefined ? 2 : maxFraction });
    },
    pct(value, digits) {
      if (value === null || value === undefined) { return '--'; }
      const n = Number(value);
      return LRM + (n >= 0 ? '+' : '') + n.toFixed(digits === undefined ? 2 : digits) + '%';
    },
    signClass(value) { const n = Number(value); return n > 0 ? 'pos' : (n < 0 ? 'neg' : ''); },
    /* Times are shown in Tehran time (decision D15); everything is stored in UTC. */
    time(ms) {
      if (!ms) { return '--'; }
      return new Date(Number(ms)).toLocaleString('en-GB', {
        timeZone: 'Asia/Tehran', year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
      });
    },
    shortTime(ms) {
      return new Date(Number(ms)).toLocaleString('en-GB', {
        timeZone: 'Asia/Tehran', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false
      });
    },

    /* A line chart as SVG. series: [{points: [{x, y}], cls}]; markers: [{x, y, kind: 'buy'|'sell', title}].
       x is a timestamp (ms). Returns {svg, readout} where readout(text) shows the value under the cursor. */
    chart(options) {
      const ns = 'http://www.w3.org/2000/svg';
      const W = 640, H = 230, L = 74, R = 12, T = 12, B = 28;
      const all = [];
      options.series.forEach(function (s) { s.points.forEach(function (p) { all.push(p); }); });
      const svg = document.createElementNS(ns, 'svg');
      svg.setAttribute('class', 'chart'); svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
      svg.setAttribute('role', 'img');
      function node(name, attrs, text) {
        const n = document.createElementNS(ns, name);
        Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
        if (text !== undefined) { n.textContent = text; }
        return n;
      }
      if (!all.length) { return { svg: svg, readout: function () {} }; }
      let x0 = Math.min.apply(null, all.map(function (p) { return p.x; }));
      let x1 = Math.max.apply(null, all.map(function (p) { return p.x; }));
      let lo = Math.min.apply(null, all.map(function (p) { return p.y; }));
      let hi = Math.max.apply(null, all.map(function (p) { return p.y; }));
      if (options.markers) { options.markers.forEach(function (m) { lo = Math.min(lo, m.y); hi = Math.max(hi, m.y); }); }
      if (hi === lo) { hi += 1; lo -= 1; }
      const pad = (hi - lo) * 0.05; hi += pad; lo -= pad;
      if (x1 === x0) { x1 += 1; }
      const X = function (x) { return L + (x - x0) / (x1 - x0) * (W - L - R); };
      const Y = function (y) { return T + (1 - (y - lo) / (hi - lo)) * (H - T - B); };
      for (let i = 0; i <= 3; i++) {                              // horizontal grid + y labels
        const v = lo + (hi - lo) * i / 3, y = Y(v);
        svg.appendChild(node('line', { x1: L, x2: W - R, y1: y, y2: y, class: 'chart-grid' }));
        svg.appendChild(node('text', { x: L - 6, y: y + 4, 'text-anchor': 'end', class: 'chart-label' },
          wb.num(v, options.digits === undefined ? 2 : options.digits)));
      }
      svg.appendChild(node('text', { x: L, y: H - 8, class: 'chart-label' }, wb.shortTime(x0)));
      svg.appendChild(node('text', { x: W - R, y: H - 8, 'text-anchor': 'end', class: 'chart-label' }, wb.shortTime(x1)));
      options.series.forEach(function (s) {
        const pts = s.points.map(function (p) { return X(p.x).toFixed(1) + ',' + Y(p.y).toFixed(1); }).join(' ');
        svg.appendChild(node('polyline', { points: pts, class: 'chart-line ' + (s.cls || '') }));
      });
      (options.markers || []).forEach(function (m) {
        const cx = X(m.x), cy = Y(m.y);
        const shape = m.kind === 'buy'
          ? node('polygon', { points: (cx - 5) + ',' + (cy + 5) + ' ' + (cx + 5) + ',' + (cy + 5) + ' ' + cx + ',' + (cy - 6), class: 'marker-buy' })
          : node('polygon', { points: (cx - 5) + ',' + (cy - 5) + ' ' + (cx + 5) + ',' + (cy - 5) + ' ' + cx + ',' + (cy + 6), class: 'marker-sell' });
        shape.appendChild(node('title', {}, m.title || ''));
        svg.appendChild(shape);
      });
      const first = options.series[0].points;
      const cursor = node('line', { y1: T, y2: H - B, class: 'chart-cursor', visibility: 'hidden' });
      svg.appendChild(cursor);
      let readoutNode = null;
      function show(clientX) {
        const box = svg.getBoundingClientRect();
        const x = (clientX - box.left) / box.width * W;
        let best = first[0];
        first.forEach(function (p) { if (Math.abs(X(p.x) - x) < Math.abs(X(best.x) - x)) { best = p; } });
        cursor.setAttribute('x1', X(best.x)); cursor.setAttribute('x2', X(best.x)); cursor.setAttribute('visibility', 'visible');
        if (readoutNode) { readoutNode.textContent = wb.time(best.x) + '   ' + wb.num(best.y, options.digits === undefined ? 2 : options.digits); }
      }
      svg.addEventListener('mousemove', function (e) { show(e.clientX); });
      svg.addEventListener('mouseleave', function () {
        cursor.setAttribute('visibility', 'hidden'); if (readoutNode) { readoutNode.textContent = ''; }
      });
      return { svg: svg, readout: function (n) { readoutNode = n; } };
    },

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

  /* Click a column header to sort a table (again to reverse). Tables are rebuilt on every refresh,
     so the choice is remembered per table and re-applied after each rebuild. A cell can carry a
     data-sort attribute when its text does not sort right (dates). Empty cells always go last. */
  const sortState = new WeakMap();
  const sortWatch = new WeakMap();
  const NUMBER = /^([+-]?\d*\.?\d+(?:e[+-]?\d+)?)\s*%?\s*[A-Za-z]*$/i;

  function sortKey(cell) {
    const attr = cell.getAttribute('data-sort');
    const text = (attr !== null ? attr : cell.textContent).replace(/\u200E/g, '').trim();
    if (text === '' || text === '-' || text === '--') { return null; }
    const m = NUMBER.exec(text.replace(/,/g, ''));
    return m ? Number(m[1]) : text.toLowerCase();
  }

  function applySort(table) {
    const state = sortState.get(table);
    const body = table.tBodies[0];
    const head = table.tHead && table.tHead.rows[0];
    if (!state || !body || !head) { return; }
    Array.prototype.forEach.call(head.cells, function (th, i) {
      if (i === state.col) { th.setAttribute('aria-sort', state.dir === 1 ? 'ascending' : 'descending'); }
      else { th.removeAttribute('aria-sort'); }
    });
    const rows = Array.prototype.slice.call(body.rows).map(function (row, index) {
      return { row: row, index: index, key: row.cells[state.col] ? sortKey(row.cells[state.col]) : null };
    });
    rows.sort(function (a, b) {
      if (a.key === null || b.key === null) { return a.key === b.key ? a.index - b.index : (a.key === null ? 1 : -1); }
      if (typeof a.key !== typeof b.key) { return typeof a.key === 'number' ? -1 : 1; }
      const c = a.key < b.key ? -1 : (a.key > b.key ? 1 : 0);
      return c ? c * state.dir : a.index - b.index;
    });
    rows.forEach(function (r) { body.appendChild(r.row); });
  }

  function watch(table) {
    if (sortWatch.has(table)) { return; }
    const observer = new MutationObserver(function () {
      observer.takeRecords();
      applySort(table);
      observer.takeRecords();   // our own reordering is not a rebuild
    });
    observer.observe(table, { childList: true });
    sortWatch.set(table, observer);
  }

  wb.resetSort = function (table) {
    sortState.delete(table);
    if (table.tHead) { Array.prototype.forEach.call(table.tHead.rows[0].cells, function (th) { th.removeAttribute('aria-sort'); }); }
  };

  document.addEventListener('click', function (event) {
    const th = event.target.closest ? event.target.closest('th') : null;
    const table = th && th.closest('table');
    if (!table || table.hasAttribute('data-nosort') || !table.tHead || th.parentNode.parentNode !== table.tHead || !th.textContent.trim()) { return; }
    const previous = sortState.get(table);
    const dir = previous && previous.col === th.cellIndex ? -previous.dir : 1;
    sortState.set(table, { col: th.cellIndex, dir: dir });
    watch(table);
    applySort(table);
  });

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
