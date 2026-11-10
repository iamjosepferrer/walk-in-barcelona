/* @ds-bundle: {"format":4,"namespace":"JF","components":[{"name":"ChartCard"},{"name":"Annotation"},{"name":"Chapters"}]} */
/* Josep Ferrer Dataviz theme. Plain script, no dependencies. Works with or without D3. */
(function () {
  var FALLBACK = {
    page: '#f5efe3', card: '#ebe3d4', raised: '#ffffff', rule: '#dfd5c3', grid: '#dad0bf',
    ink: '#1f2433', 'ink-2': '#4b5060', muted: '#5e6170',
    blue: '#2e5a93', apricot: '#b36f1e', mauve: '#954a7c', sage: '#3a8758',
    context: '#a8a196', 'context-light': '#cfc5b3'
  };
  var CATEGORICAL = ['blue', 'apricot', 'sage'];
  var NS = 'http://www.w3.org/2000/svg';

  /* The palette as hex values, read from the CSS tokens so a page edit wins. */
  function colors(scope) {
    var cs = getComputedStyle(scope || document.documentElement), out = {};
    for (var k in FALLBACK) {
      var v = cs.getPropertyValue('--' + k).trim();
      out[k] = v || FALLBACK[k];
    }
    return out;
  }

  /* Up to three category colours, always in the same order. More categories fold into "Other". */
  function categorical(n) {
    var c = colors();
    return CATEGORICAL.slice(0, Math.max(0, Math.min(n, CATEGORICAL.length))).map(function (k) { return c[k]; });
  }

  function svgNode(target) { return target && target.node ? target.node() : target; }
  function make(parent, tag, attrs) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    parent.appendChild(e);
    return e;
  }

  /* One handwritten note with a curved arrow landing on the mark.
     o.from: arrow start [x, y], next to the note
     o.to: arrow tip [x, y], on or just beside the mark
     o.at: note anchor [x, y]; o.anchor: 'start' | 'middle' | 'end'
     o.lines: array of short lines (or o.text for one line)
     o.bend: curve strength, -0.6 to 0.6, sign picks the side (default 0.3) */
  function annotate(target, o) {
    var g = make(svgNode(target), 'g', { 'class': 'jf-anno' });
    var x1 = o.from[0], y1 = o.from[1], x2 = o.to[0], y2 = o.to[1];
    var dx = x2 - x1, dy = y2 - y1, len = Math.sqrt(dx * dx + dy * dy) || 1;
    var b = (o.bend == null ? 0.3 : o.bend) * len;
    var cx = (x1 + x2) / 2 - dy / len * b, cy = (y1 + y2) / 2 + dx / len * b;
    make(g, 'path', { 'class': 'jf-arrow', d: 'M' + x1 + ',' + y1 + 'Q' + cx + ',' + cy + ' ' + x2 + ',' + y2 });
    var a = Math.atan2(y2 - cy, x2 - cx), h = 8, s = 0.45;
    make(g, 'path', { 'class': 'jf-arrow', d: 'M' + (x2 - h * Math.cos(a - s)) + ',' + (y2 - h * Math.sin(a - s)) + 'L' + x2 + ',' + y2 + 'L' + (x2 - h * Math.cos(a + s)) + ',' + (y2 - h * Math.sin(a + s)) });
    var t = make(g, 'text', { 'class': 'jf-note', x: o.at[0], y: o.at[1], 'text-anchor': o.anchor || 'start' });
    (o.lines || [o.text]).forEach(function (line, i) {
      var span = make(t, 'tspan', { x: o.at[0], dy: i ? '1.15em' : '0' });
      span.textContent = line;
    });
    return g;
  }

  /* A single shared tooltip: JF.tooltip().show(event, html) and .hide() */
  var tipEl = null;
  function tooltip() {
    if (!tipEl) {
      tipEl = document.createElement('div');
      tipEl.className = 'jf-tip';
      tipEl.hidden = true;
      document.body.appendChild(tipEl);
    }
    return {
      show: function (ev, html) {
        tipEl.innerHTML = html; tipEl.hidden = false;
        var pad = 14, r = tipEl.getBoundingClientRect();
        var x = ev.clientX + pad, y = ev.clientY + pad;
        if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - pad;
        if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - pad;
        tipEl.style.left = x + 'px'; tipEl.style.top = y + 'px';
      },
      hide: function () { tipEl.hidden = true; }
    };
  }

  /* Number formatting per language: JF.fmt.num(6.659, 1, 'es') gives "6,7" */
  var LOCALES = { en: 'en-GB', es: 'es-ES', ca: 'ca-ES', nl: 'nl-NL' };
  var fmt = {
    num: function (v, digits, lang) {
      return new Intl.NumberFormat(LOCALES[lang || 'en'] || lang, { minimumFractionDigits: digits || 0, maximumFractionDigits: digits || 0 }).format(v);
    },
    pct: function (v, digits, lang) { return fmt.num(v, digits, lang) + '%'; },
    int: function (v, lang) { return fmt.num(Math.round(v), 0, lang); }
  };

  window.JF = { colors: colors, categorical: categorical, annotate: annotate, tooltip: tooltip, fmt: fmt, order: CATEGORICAL.slice() };
})();
