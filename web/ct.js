// ----- ChurchTools -----
(() => {
  const d = new Date();
  document.getElementById('ctDatum').value = d.toISOString().split('T')[0];
})();

export async function ctStatus() {
  const msg = document.getElementById('ctMsg');
  try {
    const s = await (await fetch('/api/ct/status')).json();
    console.log('%cLobpreis-Planer Version: ' + (s.version||'?'), 'font-weight:bold;color:#2563eb');
    console.log('ctStatus', s);
    const vEl = document.getElementById('version');
    if (vEl) vEl.textContent = 'v' + (s.version || '?');
    if (!s.hat_token) {
      msg.className = 'hint';
      msg.textContent = s.config_vorhanden
        ? 'Kein Token in config.json – bitte unten eintragen.'
        : 'Kein Token – bitte unten eintragen.';
    } else if (s.token_ok === false) {
      msg.className = 'err';
      msg.textContent = 'Token in config.json ist ungültig oder abgelaufen.';
    } else {
      msg.className = 'okbox';
      msg.textContent = 'Verbunden mit ' + (s.base_url||'');
    }
  } catch (e) {
    msg.className = 'err';
    msg.textContent = 'ChurchTools nicht erreichbar.';
  }
}
document.getElementById('ctTokenSave').addEventListener('click', async () => {
  const j = await (await fetch('/api/ct/token', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({token: document.getElementById('ctToken').value})})).json();
  document.getElementById('ctTokenMsg').textContent = j.ok ? '✓ gespeichert' : ('Fehler: '+(j.error||''));
  ctStatus();
  if (j.ok) { cacheLeeren(); renderKalender(); }   // Dienste des neuen Tokens frisch laden
});
const ctEscHtml = s => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
// Passendes Icon je Dienst (rein kosmetisch, fällt auf 📋 zurück)
const DIENST_ICONS = [[/ton/i,'🎧'],[/licht/i,'💡'],[/beamer|video|kamera|stream|medien|regie|bildmisch/i,'📽️'],
  [/gesang|vocal|lobpreis/i,'🎤'],[/piano|keys|synth/i,'🎹'],[/drum|schlagzeug/i,'🥁'],
  [/\bbass\b/i,'🎸'],[/git/i,'🎸'],[/predigt|moderation|leitung|\bmd\b|koordin/i,'🎙️']];
const dienstIcon = namen => {
  for (const n of (namen || [])) for (const [re, ic] of DIENST_ICONS) if (re.test(n)) return ic;
  return '📋';
};

// Termin-Liste eines Tages rendern (eigene Dienste zuerst, hervorgehoben, der
// erste eigene wird vorausgewaehlt). Bekommt die Events direkt (aus dem Cache).
export function renderEventList(events) {
  // Meldung kommt ins Popover (ctPopMsg), nicht in ctMsg -> die Kartenhoehe im
  // Layout-Fluss bleibt konstant, die Setliste wandert beim Datums-Klick nicht.
  const popover = document.getElementById('ctPopover');
  const msg = document.getElementById('ctPopMsg');
  const list = document.getElementById('ctEventsList');
  const ladenRow = document.getElementById('ctLadenRow');
  list.innerHTML = ''; ladenRow.style.display = 'none';
  popover.style.display = 'block';   // ein Tag wurde angeklickt -> Overlay zeigen
  positioniereTerminPopover();
  if (!events || events.length === 0) {
    list.style.display = 'none';
    msg.textContent = 'Keine Termine an diesem Tag.'; return;
  }
  list.style.display = 'flex';
  // Eigene Dienste zuerst (stabiler Sort -> innerhalb chronologisch)
  const evs = events.slice().sort((a, b) => (b.meins ? 1 : 0) - (a.meins ? 1 : 0));
  const meineAnzahl = evs.filter(e => e.meins).length;
  let ersterEigener = null;

  const macheItem = e => {
    const div = document.createElement('div');
    div.className = 'ev-item' + (e.meins ? ' mine' : '');
    const parts = e.label.split(' – ');
    const badge = e.meins
      ? '<span class="ev-badge">' + dienstIcon(e.dienste) + ' ' + ctEscHtml((e.dienste || []).join(', ')) + '</span>'
      : '';
    div.innerHTML = '<span class="date">' + ctEscHtml(parts[0]) + '</span><span class="name">'
      + ctEscHtml(parts.slice(1).join(' – ')) + badge + '</span>';
    div.setAttribute('data-id', e.id);
    div.setAttribute('data-label', e.label);
    div.onclick = () => {
      document.querySelectorAll('.ev-item').forEach(i => i.classList.remove('active'));
      div.classList.add('active');
      ladenRow.style.display = 'flex';
      ladenRow.scrollIntoView({behavior:'smooth', block:'nearest'});
    };
    return div;
  };

  let trennerGesetzt = false;
  evs.forEach(e => {
    if (meineAnzahl > 0 && !e.meins && !trennerGesetzt) {
      const sep = document.createElement('div');
      sep.className = 'ev-sep'; sep.textContent = 'Weitere Termine';
      list.appendChild(sep); trennerGesetzt = true;
    }
    const div = macheItem(e);
    list.appendChild(div);
    if (e.meins && !ersterEigener) ersterEigener = div;
  });

  // Eigenen Dienst sofort vorauswählen (schneller auswählbar)
  if (ersterEigener) { ersterEigener.classList.add('active'); ladenRow.style.display = 'flex'; }
  msg.textContent = events.length + ' Termin(e)'
    + (meineAnzahl ? ', davon ' + meineAnzahl + ' mit deinem Dienst (vorausgewählt).' : '.');
}

// ----- Termin-Cache (RAM + localStorage), spart wiederholte API-Abfragen ----
const monatsCache = {};     // 'YYYY-MM' -> [events]  (RAM, gilt nur fuer diese Sitzung)
const monatGeprueft = {};   // 'YYYY-MM' -> true: in dieser Sitzung schon mit der API abgeglichen
const CACHE_PREFIX = 'lpct_';
const CACHE_TTL_MS = 12 * 60 * 60 * 1000;  // localStorage-Eintraege laufen nach 12 h ab

function cacheLesen(key) {
  if (monatsCache[key]) return monatsCache[key];
  try {
    const r = localStorage.getItem(CACHE_PREFIX + key);
    if (!r) return null;
    const obj = JSON.parse(r);
    // Format {ts, v}: bei Ablauf verwerfen. Altes Format (reines Array, ohne ts)
    // gilt als abgelaufen -> wird einmal frisch geholt und neu gespeichert.
    if (obj && typeof obj.ts === 'number' && Array.isArray(obj.v)) {
      if (Date.now() - obj.ts > CACHE_TTL_MS) { localStorage.removeItem(CACHE_PREFIX + key); return null; }
      return (monatsCache[key] = obj.v);
    }
    localStorage.removeItem(CACHE_PREFIX + key);  // unbekanntes/altes Format -> verwerfen
  } catch (e) {}
  return null;
}
function cacheSchreiben(key, events) {
  monatsCache[key] = events;
  try { localStorage.setItem(CACHE_PREFIX + key, JSON.stringify({ts: Date.now(), v: events})); } catch (e) {}
}
export function cacheLeeren() {  // z.B. nach Token-Wechsel: Dienste koennen sich aendern
  for (const k in monatsCache) delete monatsCache[k];
  for (const k in monatGeprueft) delete monatGeprueft[k];
  try { Object.keys(localStorage).filter(k => k.indexOf(CACHE_PREFIX) === 0).forEach(k => localStorage.removeItem(k)); } catch (e) {}
}

// Liefert die Events eines Monats. Nutzt den Cache und gleicht je Monat nur EINMAL
// pro Sitzung mit der API ab; onUpdate wird NUR aufgerufen, wenn sich gegenueber dem
// Cache wirklich etwas geaendert hat.
const monatLaedt = {};      // 'YYYY-MM' -> true: laeuft gerade eine API-Abfrage
function spinnerAktualisieren() {
  const sp = document.getElementById('calSpinner');
  if (sp) sp.hidden = !monatLaedt[monatKey(kal.d.getFullYear(), kal.d.getMonth())];
}

export async function holeMonat(key, von, bis, onUpdate) {
  const cached = cacheLesen(key);
  if (cached && monatGeprueft[key]) return cached;     // schon geprueft -> keine API-Abfrage
  // Spinner NUR beim Kaltstart (keine Daten zum Anzeigen). Sind bereits Termine aus
  // dem Cache sichtbar, laeuft der Abgleich still im Hintergrund -> kein Spinner.
  const kalt = !cached;
  if (kalt) { monatLaedt[key] = true; spinnerAktualisieren(); }
  let frisch = null;
  let fehler = null;
  try {
    const r = await fetch('/api/ct/events?von=' + von + '&bis=' + bis);
    const j = await r.json();
    if (j.ok) frisch = j.events || [];
    else fehler = j.error || 'Unbekannter Fehler';
  } catch (e) {
    fehler = 'ChurchTools nicht erreichbar.';
  } finally { if (kalt) { monatLaedt[key] = false; spinnerAktualisieren(); } }
  monatGeprueft[key] = true;
  if (fehler && !cached) {
    // Fehlermeldung im Kalender anzeigen
    const msg = document.getElementById('ctMsg');
    if (msg) {
      msg.textContent = fehler;
      msg.className = fehler === 'Kein Token konfiguriert.' ? 'hint' : 'err';
    }
  }
  if (frisch === null) return cached || [];            // API-Fehler -> Cache behalten
  if (!cached || JSON.stringify(cached) !== JSON.stringify(frisch)) {
    cacheSchreiben(key, frisch);
    if (onUpdate) onUpdate(frisch);                    // nur bei echter Aenderung
  }
  return frisch;
}

// ----- Mini-Kalender mit Dienst-Markierung -----
export const kal = { d: new Date() };
kal.d.setDate(1);
const zwei = n => String(n).padStart(2, '0');
const ymd = date => date.getFullYear() + '-' + zwei(date.getMonth() + 1) + '-' + zwei(date.getDate());
const monatKey = (y, m) => y + '-' + zwei(m + 1);

// Tage markieren: eigener Dienst (mine) hat Vorrang vor anderen Terminen (has-event)
function markiere(zellen, events) {
  const duty = new Set((events || []).filter(e => e.meins).map(e => e.datum));
  const evt = new Set((events || []).map(e => e.datum));
  Object.keys(zellen).forEach(ds => {
    const c = zellen[ds];
    c.classList.remove('mine', 'has-event');
    if (duty.has(ds)) c.classList.add('mine');
    else if (evt.has(ds)) c.classList.add('has-event');
  });
}

// Termine eines Tages anzeigen -- aus dem Monats-Cache (kein API-Call, falls vorhanden)
export async function zeigeTag(ds) {
  const key = ds.slice(0, 7);
  let events = cacheLesen(key);
  if (!events) {
    const last = new Date(+ds.slice(0, 4), +ds.slice(5, 7), 0).getDate();
    events = await holeMonat(key, key + '-01', key + '-' + zwei(last));
  }
  renderEventList((events || []).filter(e => e.datum === ds));
}

// Das Overlay ist position:fixed -> Position aus dem Kalender-Rechteck berechnen
// (escaped so das Multi-Column-Clipping der Spalten).
function positioniereTerminPopover() {
  const pop = document.getElementById('ctPopover');
  const kalEl = document.getElementById('ctKalender');
  if (!pop || pop.style.display === 'none' || !kalEl) return;
  const r = kalEl.getBoundingClientRect();
  pop.style.left = r.left + 'px';
  pop.style.top = (r.bottom + 6) + 'px';
  pop.style.width = r.width + 'px';
}
function schliesseTerminPopover() {
  const pop = document.getElementById('ctPopover');
  if (pop) pop.style.display = 'none';
  document.querySelectorAll('.cal-day.selected').forEach(x => x.classList.remove('selected'));
}
// Beim Scrollen/Resize mitführen, solange das Overlay offen ist.
window.addEventListener('scroll', positioniereTerminPopover, true);
window.addEventListener('resize', positioniereTerminPopover);

export function renderKalender() {
  schliesseTerminPopover();   // Monatswechsel/Neuaufbau -> altes Tages-Overlay schliessen
  const grid = document.getElementById('calGrid');
  const dowRow = document.getElementById('calDow');
  const y = kal.d.getFullYear(), m = kal.d.getMonth();
  document.getElementById('calTitle').textContent =
    kal.d.toLocaleDateString('de-DE', { month: 'long', year: 'numeric' });
  if (!dowRow.children.length)
    ['Mo','Di','Mi','Do','Fr','Sa','So'].forEach(t => {
      const c = document.createElement('div'); c.className = 'cal-dow'; c.textContent = t; dowRow.appendChild(c);
    });

  // 1) Raster sofort zeichnen (Kalender ist sofort sichtbar, auch ohne geladene Termine)
  const last = new Date(y, m + 1, 0).getDate();
  grid.innerHTML = '';
  const firstDow = (new Date(y, m, 1).getDay() + 6) % 7; // Mo=0 … So=6
  for (let i = 0; i < firstDow; i++) {
    const c = document.createElement('div'); c.className = 'cal-day empty'; grid.appendChild(c);
  }
  const todayStr = ymd(new Date());
  const zellen = {};
  for (let day = 1; day <= last; day++) {
    const ds = y + '-' + zwei(m + 1) + '-' + zwei(day);
    const c = document.createElement('div');
    c.className = 'cal-day'; c.textContent = day;
    if (ds === todayStr) c.classList.add('today');
    c.title = 'Termine an diesem Tag anzeigen';
    c.onclick = () => {
      document.querySelectorAll('.cal-day.selected').forEach(x => x.classList.remove('selected'));
      c.classList.add('selected');
      document.getElementById('ctDatum').value = ds;
      zeigeTag(ds);
    };
    grid.appendChild(c);
    zellen[ds] = c;
  }

  // 2) Markierungen: sofort aus dem Cache, dann je Monat einmal abgleichen
  //    und nur bei tatsaechlicher Aenderung neu markieren.
  const key = monatKey(y, m);
  const von = y + '-' + zwei(m + 1) + '-01';
  const bis = y + '-' + zwei(m + 1) + '-' + zwei(last);
  const cached = cacheLesen(key);
  if (cached) markiere(zellen, cached);
  holeMonat(key, von, bis, frisch => {
    if (monatKey(kal.d.getFullYear(), kal.d.getMonth()) === key) markiere(zellen, frisch);
  });
  spinnerAktualisieren();   // Spinner-Zustand fuer den jetzt sichtbaren Monat setzen
}
document.getElementById('calPrev').addEventListener('click', () => { kal.d.setMonth(kal.d.getMonth() - 1); renderKalender(); });
document.getElementById('calNext').addEventListener('click', () => { kal.d.setMonth(kal.d.getMonth() + 1); renderKalender(); });

// Overlay an <body> haengen: sonst verschiebt ein transformierter Vorfahre
// (.card:hover -> transform) den Bezugsrahmen von position:fixed und das Popover
// springt beim Drueberfahren herum.
(() => { const p = document.getElementById('ctPopover'); if (p) document.body.appendChild(p); })();

// Klick ausserhalb von Kalender UND Overlay schliesst das Termin-Overlay wieder.
document.addEventListener('click', e => {
  const pop = document.getElementById('ctPopover');
  const kalEl = document.getElementById('ctKalender');
  if (pop && pop.style.display !== 'none' && kalEl
      && !kalEl.contains(e.target) && !pop.contains(e.target))
    schliesseTerminPopover();
});

// Kalender immer beim Laden anzeigen (ohne Token ohne Dienst-Markierung)
renderKalender();
