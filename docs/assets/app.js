/* Climat 2050 : quels seront les aléas climatiques dominants sur votre territoire ?
   Données : DRIAS TRACC-2023 (Q50), IGN ADMIN EXPRESS. Auteur : Josselin Thonnelier, 2026. */
(function () {
  'use strict';

  var THEMES = [
    { k: 'chaleur', label: 'Chaleur' },
    { k: 'secheresse', label: 'Sécheresse' },
    { k: 'feux', label: 'Feux de forêt' },
    { k: 'pluies', label: 'Pluies extrêmes' }
  ];
  // Synthèse nationale (communes) : part de surface et population cumulant ≥ 3 aléas
  var NATIONAL = {
    '30_27': { s3: 14.1, p3: 14.7 }, '10_27': { s3: 6.1, p3: 8.0 },
    '30_40': { s3: 14.6, p3: 13.5 }, '10_40': { s3: 5.7, p3: 7.3 }
  };
  var RAMP = { breaks: [5, 25, 50, 75], colors: ['#ffffff', '#efede7', '#dcd8cd', '#c2bdaf', '#a19b8b'],
               labels: ['< 5 %', '5 à 25', '25 à 50', '50 à 75', '> 75 %'] };
  var HORIZON = { '27': '2050 (+2,7 °C)', '40': '2100 (+4 °C)' };
  var EPCI_BARS_ZOOM = 8;

  var state = { scale: 'departements', q: '30', h: '27', sel: null };
  var data = {};
  var map, polyLayer, barsLayer, hoverFeature = null;
  var $ = function (s) { return document.querySelector(s); };
  var isMobile = function () { return window.matchMedia('(max-width: 820px)').matches; };
  var key = function () { return state.q + '_' + state.h; };
  var fmt = new Intl.NumberFormat('fr-FR');

  // ---------- état dans l'URL (partage) ----------
  (function readUrl() {
    var p = new URLSearchParams(location.search);
    if (p.get('echelle') === 'epci') state.scale = 'epcis';
    if (p.get('seuil') === '10') state.q = '10';
    if (p.get('horizon') === '2100') state.h = '40';
  })();
  function writeUrl() {
    var p = new URLSearchParams();
    if (state.scale === 'epcis') p.set('echelle', 'epci');
    if (state.q === '10') p.set('seuil', '10');
    if (state.h === '40') p.set('horizon', '2100');
    var qs = p.toString();
    history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '') + location.hash);
  }

  // ---------- carte ----------
  function initMap() {
    map = L.map('map', { zoomControl: false, preferCanvas: true, minZoom: 5, maxZoom: 11,
      maxBounds: [[39.5, -8.5], [53, 12.5]], maxBoundsViscosity: 0.8, attributionControl: false });
    L.control.attribution({ position: isMobile() ? 'topleft' : 'bottomright', prefix: '<a href="https://leafletjs.com">Leaflet</a>' }).addTo(map);
    L.control.zoom({ position: 'topright' }).addTo(map);
    // Fond de carte : Plan IGN (Géoplateforme IGN, sans clé d'API), affiché en gris clair via CSS
    L.tileLayer('https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal&TILEMATRIXSET=PM&FORMAT=image/png&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}', {
      maxZoom: 19, maxNativeZoom: 19, className: 'fond-ign',
      attribution: 'Fond : <a href="https://geoservices.ign.fr/">© IGN Plan IGN</a> · DRIAS / Météo-France · IGN ADMIN EXPRESS'
    }).addTo(map);
    fitFrance();
    map.on('zoomend', function () { renderBars(); updateHint(); });
    map.on('click', function () { /* clic dans le vide */ });
  }

  function fitFrance() {
    var peek = isMobile() ? parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--peek')) || 220 : 0;
    map.fitBounds([[41.3, -5.2], [51.1, 9.6]], { paddingTopLeft: [8, 8], paddingBottomRight: [8, peek + 8] });
  }
  function fillColor(v) {
    for (var i = 0; i < RAMP.breaks.length; i++) if (v < RAMP.breaks[i]) return RAMP.colors[i];
    return RAMP.colors[RAMP.colors.length - 1];
  }
  function baseStyle(f) {
    var dep = state.scale === 'departements';
    var selected = state.sel && state.sel === f.properties.c;
    return { fillColor: fillColor(f.properties.s3[key()]), fillOpacity: 0.88,
      color: selected ? '#14213d' : (dep ? '#8b909a' : '#a3a8b0'),
      weight: selected ? 3 : (dep ? 0.9 : 0.45), opacity: 1 };
  }

  function renderPolys() {
    if (polyLayer) map.removeLayer(polyLayer);
    polyLayer = L.geoJSON(data[state.scale], {
      style: baseStyle,
      onEachFeature: function (f, layer) {
        layer.on({
          mouseover: function (e) { if (isMobile()) return; hoverFeature = f; layer.setStyle({ weight: 2.2, color: '#14213d' }); showTip(e.originalEvent, f); if (!state.sel) renderDetail(f); },
          mousemove: function (e) { if (!isMobile()) moveTip(e.originalEvent); },
          mouseout: function () { hoverFeature = null; polyLayer.resetStyle(layer); hideTip(); if (!state.sel) renderDetail(null); },
          click: function (e) { L.DomEvent.stopPropagation(e); select(f, false); }
        });
      }
    }).addTo(map);
  }

  function barsHtml(v, h) {
    return '<div class="bars" style="height:' + h + 'px">' + v.map(function (x) {
      return '<i style="height:' + Math.max(0, Math.min(100, x)) + '%"></i>'; }).join('') + '</div>';
  }
  function barsSize() {
    var z = map.getZoom(), dep = state.scale === 'departements';
    if (dep) return z <= 5 ? [18, 24] : z === 6 ? [24, 32] : z === 7 ? [32, 42] : [40, 52];
    return z <= 8 ? [18, 24] : z === 9 ? [24, 32] : [32, 42];
  }
  function renderBars() {
    if (!data[state.scale]) return;
    if (!barsLayer) barsLayer = L.layerGroup().addTo(map);
    barsLayer.clearLayers();
    if (state.scale === 'epcis' && map.getZoom() < EPCI_BARS_ZOOM) return;
    var sz = barsSize(), k = key(), b = map.getBounds().pad(0.2);
    data[state.scale].features.forEach(function (f) {
      var a = f.properties.a, ll = L.latLng(a[1], a[0]);
      if (state.scale === 'epcis' && !b.contains(ll)) return;
      var icon = L.divIcon({ className: 'bars-icon', html: barsHtml(f.properties.pt[k], sz[1]), iconSize: sz, iconAnchor: [sz[0] / 2, sz[1]] });
      L.marker(ll, { icon: icon, interactive: false, keyboard: false }).addTo(barsLayer);
    });
  }
  function updateHint() {
    if (!map) return;
    $('#mapHint').hidden = !(state.scale === 'epcis' && map.getZoom() < EPCI_BARS_ZOOM);
  }

  // ---------- infobulle ----------
  var tip = $('#tip');
  function tipHtml(f) {
    var v = f.properties.pt[key()];
    return '<h4>' + esc(f.properties.n) + '</h4>' + THEMES.map(function (t, i) {
      return '<div class="row"><span><i class="sw ' + t.k + '"></i>' + t.label + '</span><b>' + v[i] + ' %</b></div>'; }).join('');
  }
  function showTip(ev, f) { tip.innerHTML = tipHtml(f); tip.hidden = false; moveTip(ev); }
  function moveTip(ev) {
    var x = ev.clientX + 16, y = ev.clientY + 16, w = tip.offsetWidth, h = tip.offsetHeight;
    if (x + w > window.innerWidth - 8) x = ev.clientX - w - 16;
    if (y + h > window.innerHeight - 8) y = ev.clientY - h - 16;
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  }
  function hideTip() { tip.hidden = true; }

  // ---------- panneau ----------
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  function renderKpi() {
    var n = NATIONAL[key()];
    $('#kpi').innerHTML = '<p class="k-title">Hexagone · ' + state.q + ' % les plus exposés · ' + HORIZON[state.h] + '</p>' +
      '<div><div class="k-val">' + n.s3.toFixed(1).replace('.', ',') + ' %</div><div class="k-lab">du territoire cumule au moins 3 aléas</div></div>' +
      '<div><div class="k-val">' + n.p3.toFixed(1).replace('.', ',') + ' M</div><div class="k-lab">d\'habitants concernés</div></div>';
  }

  function renderDetail(f) {
    var el = $('#detail');
    if (!f) { el.innerHTML = '<p class="detail-empty">Survolez ou touchez un territoire pour afficher son profil.</p>'; return; }
    var p = f.properties, k = key(), v = p.pt[k];
    var dep = state.scale === 'departements';
    var max = Math.max.apply(null, v), dom;
    if (max < 5) dom = 'Aucun aléa ne ressort parmi les ' + state.q + ' % les plus exposés.';
    else {
      var names = THEMES.filter(function (t, i) { return v[i] >= max - 5 && v[i] >= 5; }).map(function (t) { return t.label.toLowerCase(); });
      dom = 'Aléa' + (names.length > 1 ? 's' : '') + ' dominant' + (names.length > 1 ? 's' : '') + ' : <b>' + names.join(', ') + '</b>';
    }
    el.innerHTML = '<h2>' + esc(p.n) + '</h2>' +
      '<p class="meta">' + (dep ? 'Département ' + esc(p.c) : 'Intercommunalité (EPCI)') + ' · ' + fmt.format(p.p) + ' hab. · ' + HORIZON[state.h] + '</p>' +
      '<ul class="hbars" aria-label="Part de la surface dans les ' + state.q + ' % les plus exposés">' +
      THEMES.map(function (t, i) {
        return '<li><span>' + t.label + '</span><span class="track"><span class="fill ' + t.k + '" style="width:' + v[i] + '%"></span></span><span class="v">' + v[i] + ' %</span></li>';
      }).join('') + '</ul>' +
      '<div class="cumul"><div><b>' + p.s2[k] + ' %</b><span>de la surface cumule ≥ 2 aléas</span></div>' +
      '<div><b>' + p.s3[k] + ' %</b><span>de la surface cumule ≥ 3 aléas</span></div>' +
      '<div><b>' + p.p3[k] + ' %</b><span>de la population cumule ≥ 3 aléas</span></div></div>' +
      '<p class="dominant">' + dom + '</p>';
  }

  function renderLegend() {
    $('#ramp').innerHTML = RAMP.colors.map(function (c, i) { return '<li><i style="background:' + c + '"></i>' + RAMP.labels[i] + '</li>'; }).join('');
    document.querySelectorAll('.q-label').forEach(function (e) { e.textContent = state.q + ' %'; });
  }

  function fillSearch() {
    var names = data[state.scale].features.map(function (f) { return f.properties.n; }).sort(function (a, b) { return a.localeCompare(b, 'fr'); });
    $('#territoires').innerHTML = names.map(function (n) { return '<option value="' + esc(n) + '">'; }).join('');
    $('#search').placeholder = state.scale === 'departements' ? 'Ex. Gironde, Hérault…' : 'Ex. Métropole de Lyon, CA du Pays Basque…';
  }

  function findFeature(name) {
    var n = name.trim().toLowerCase(); if (!n) return null;
    var fs = data[state.scale].features;
    return fs.find(function (f) { return f.properties.n.toLowerCase() === n; }) ||
           fs.find(function (f) { return f.properties.n.toLowerCase().indexOf(n) !== -1; });
  }

  function select(f, zoom) {
    state.sel = f ? f.properties.c : null;
    polyLayer.setStyle(baseStyle);
    renderDetail(f);
    if (f && zoom) {
      var lyr = polyLayer.getLayers().find(function (l) { return l.feature.properties.c === f.properties.c; });
      if (lyr) map.flyToBounds(lyr.getBounds(), { padding: [40, 40], maxZoom: state.scale === 'epcis' ? 9 : 8, duration: 0.8 });
    }
    if (f && isMobile()) openSheet(true);
  }

  function refresh(scaleChanged) {
    renderKpi(); renderLegend();
    if (scaleChanged) { state.sel = null; renderPolys(); fillSearch(); renderDetail(null); }
    else {
      polyLayer.setStyle(baseStyle);
      var f = state.sel && data[state.scale].features.find(function (x) { return x.properties.c === state.sel; });
      renderDetail(f || hoverFeature || null);
    }
    renderBars(); updateHint(); writeUrl();
  }

  // ---------- contrôles ----------
  function initControls() {
    document.querySelectorAll('.seg').forEach(function (seg) {
      var k = seg.dataset.key;
      var sync = function () { seg.querySelectorAll('button').forEach(function (b) { b.setAttribute('aria-checked', String(b.dataset.value === state[k])); }); };
      sync();
      seg.addEventListener('click', function (e) {
        var b = e.target.closest('button'); if (!b || b.dataset.value === state[k]) return;
        state[k] = b.dataset.value; sync(); refresh(k === 'scale');
      });
      seg.addEventListener('keydown', function (e) {
        if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
        var bs = Array.prototype.slice.call(seg.querySelectorAll('button'));
        var i = bs.findIndex(function (b) { return b.dataset.value === state[k]; });
        var n = bs[(i + (e.key === 'ArrowRight' ? 1 : bs.length - 1)) % bs.length];
        n.click(); n.focus(); e.preventDefault();
      });
    });
    var s = $('#search');
    var go = function () { var f = findFeature(s.value); if (f) { select(f, true); s.blur(); } };
    s.addEventListener('change', go);
    s.addEventListener('keydown', function (e) { if (e.key === 'Enter') go(); });

    document.querySelectorAll('.info').forEach(function (b) {
      b.addEventListener('mouseenter', function (e) { tip.innerHTML = '<p style="margin:0;max-width:240px">' + b.dataset.tip + '</p>'; tip.hidden = false; moveTip(e); });
      b.addEventListener('mouseleave', hideTip);
      b.addEventListener('click', function (e) { e.preventDefault(); alertTip(b); });
    });
    function alertTip(b) { var d = $('#detail'); d.innerHTML = '<p class="detail-empty">' + b.dataset.tip + '</p>'; }

    // bottom sheet mobile
    $('#sheetHandle').addEventListener('click', function () { openSheet(!$('#panel').classList.contains('open')); });
    var startY = null;
    $('#sheetHandle').addEventListener('touchstart', function (e) { startY = e.touches[0].clientY; }, { passive: true });
    $('#sheetHandle').addEventListener('touchend', function (e) {
      if (startY === null) return; var dy = e.changedTouches[0].clientY - startY; startY = null;
      if (Math.abs(dy) > 30) openSheet(dy < 0);
    });

    // tableau
    $('#openTable').addEventListener('click', openTable);
    $('#closeTable').addEventListener('click', function () { $('#tableDialog').close(); });
    $('#tableDialog').addEventListener('click', function (e) { if (e.target === this) this.close(); });

    // navigation active
    var links = document.querySelectorAll('.nav a');
    var obs = new IntersectionObserver(function (es) {
      es.forEach(function (en) { if (en.isIntersecting) links.forEach(function (a) { a.classList.toggle('active', a.getAttribute('href') === '#' + en.target.id); }); });
    }, { threshold: 0.4 });
    ['carte', 'methode', 'sources'].forEach(function (id) { obs.observe(document.getElementById(id)); });
  }
  function openSheet(open) {
    $('#panel').classList.toggle('open', open);
    $('#sheetHandle').setAttribute('aria-expanded', String(open));
  }
  function setPeek() {
    // hauteur visible du panneau replié : poignée + contrôles + chiffres clés
    var c = document.querySelector('.controls'), k = $('#kpi');
    if (!isMobile()) return;
    var h = 22 + 4 + c.offsetHeight + 16;
    document.documentElement.style.setProperty('--peek', Math.min(h, window.innerHeight * 0.45) + 'px');
  }

  // ---------- tableau accessible ----------
  var sortCol = 6, sortDir = -1;
  function openTable() {
    var k = key(), dep = state.scale === 'departements';
    $('#tableTitle').textContent = (dep ? 'Départements' : 'EPCI') + ' · ' + state.q + ' % les plus exposés · ' + HORIZON[state.h];
    $('#tableSub').textContent = 'Part de la surface (%) comprise dans les ' + state.q + ' % de l\'Hexagone les plus exposés, par aléa. Cliquez sur un en-tête pour trier.';
    var cols = ['Territoire', 'Population'].concat(THEMES.map(function (t) { return t.label; })).concat(['≥ 3 aléas (surface)']);
    var thead = $('#dataTable thead');
    thead.innerHTML = '<tr>' + cols.map(function (c, i) { return '<th scope="col" data-i="' + i + '">' + c + '</th>'; }).join('') + '</tr>';
    thead.querySelectorAll('th').forEach(function (th) {
      th.addEventListener('click', function () { var i = +th.dataset.i; sortDir = (sortCol === i) ? -sortDir : (i === 0 ? 1 : -1); sortCol = i; fillRows(); });
    });
    fillRows();
    $('#tableDialog').showModal();
    function fillRows() {
      var rows = data[state.scale].features.map(function (f) { var p = f.properties; return [p.n, p.p].concat(p.pt[k]).concat([p.s3[k]]); });
      rows.sort(function (a, b) { var x = a[sortCol], y = b[sortCol]; return (typeof x === 'string' ? x.localeCompare(y, 'fr') : x - y) * sortDir; });
      thead.querySelectorAll('th').forEach(function (th) { th.removeAttribute('aria-sort'); if (+th.dataset.i === sortCol) th.setAttribute('aria-sort', sortDir > 0 ? 'ascending' : 'descending'); });
      $('#dataTable tbody').innerHTML = rows.map(function (r) {
        return '<tr><td>' + esc(r[0]) + '</td><td>' + fmt.format(r[1]) + '</td>' +
          r.slice(2, 6).map(function (v, i) { return '<td><span class="dot sw ' + THEMES[i].k + '"></span>' + v + ' %</td>'; }).join('') +
          '<td><b>' + r[6] + ' %</b></td></tr>';
      }).join('');
    }
  }


  // ---------- fenêtre d'accueil ----------
  function initIntro() {
    var dlg = $('#introDialog'), hide = false;
    try { hide = localStorage.getItem('climat2050_intro_vu') === '1'; } catch (e) { hide = false; }
    var close = function () {
      try { if ($('#introHide').checked) localStorage.setItem('climat2050_intro_vu', '1'); } catch (e) { /* stockage indisponible */ }
      dlg.close();
    };
    $('#closeIntro').addEventListener('click', close);
    $('#introMethode').addEventListener('click', close);
    dlg.addEventListener('cancel', close);
    dlg.addEventListener('click', function (e) { if (e.target === dlg) close(); });
    $('#openIntro').addEventListener('click', function () { dlg.showModal(); });
    if (!hide && !location.hash.match(/methode|sources/)) dlg.showModal();
  }

  // ---------- démarrage ----------
  initMap(); initControls(); initIntro(); renderKpi(); renderLegend();
  Promise.all(['departements', 'epcis'].map(function (n) {
    return fetch('data/' + n + '.geojson').then(function (r) { if (!r.ok) throw new Error(n); return r.json(); }).then(function (j) { data[n] = j; });
  })).then(function () {
    renderPolys(); fillSearch(); renderBars(); updateHint(); renderDetail(null);
    $('#loader').classList.add('done'); setPeek(); if (isMobile()) { map.invalidateSize(); fitFrance(); }
  }).catch(function (e) {
    $('#loader').innerHTML = 'Impossible de charger les données (' + e.message + ').';
  });
  window.addEventListener('resize', function () { setPeek(); });
})();
