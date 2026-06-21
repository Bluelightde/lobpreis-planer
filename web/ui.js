export let LETZTES = null;

// ----- Setliste (Tabelle) -----
const slTbody = document.querySelector('#slTable tbody');
const slEditTbody = document.querySelector('#slTableEdit tbody');
const slEditModal = document.getElementById('slEditModal');
const mischModus = document.getElementById('mischModus');
const mischTbody = document.querySelector('#mischTable tbody');

export function slAddRow(data = {}) {
  const rowIdx = slTbody.children.length;
  const nr = data.nr || (rowIdx + 1);

  // Zeile für Sidebar
  const trSidebar = document.createElement('tr');
  trSidebar.innerHTML = `
    <td><input type="text" value="${esc(nr)}" data-key="nr"></td>
    <td><input type="text" value="${esc(data.lied || '')}" data-key="lied"></td>
    <td><input type="text" value="${esc(data.stimme || '')}" data-key="stimme"></td>
    <td><input type="text" value="${esc(data.instrument || '')}" data-key="instrument"></td>
    <td><input type="text" value="${esc(data.bemerkung || '')}" data-key="bemerkung"></td>
    <td class="sl-del-td"><button class="sek sl-del" title="Zeile entfernen">✕</button></td>
  `;

  // Zeile für Edit-Modal
  const trEdit = document.createElement('tr');
  trEdit.innerHTML = trSidebar.innerHTML;

  // Sync-Funktion
  const setupSync = (sourceTr, targetTr) => {
    sourceTr.querySelectorAll('input').forEach(input => {
      input.oninput = (e) => {
        const key = e.target.getAttribute('data-key');
        const targetInput = targetTr.querySelector(`[data-key="${key}"]`);
        if (targetInput) targetInput.value = e.target.value;
      };
    });
  };

  setupSync(trSidebar, trEdit);
  setupSync(trEdit, trSidebar);

  // Loeschen: beide Ansichten (Sidebar + Edit-Modal) gemeinsam entfernen.
  const entferne = () => { trSidebar.remove(); trEdit.remove(); };
  trSidebar.querySelector('.sl-del').onclick = entferne;
  trEdit.querySelector('.sl-del').onclick = entferne;

  slTbody.appendChild(trSidebar);
  slEditTbody.appendChild(trEdit);
}

document.getElementById('slEditAddRow').onclick = () => slAddRow();
document.getElementById('slOpenEdit').onclick = () => slEditModal.hidden = false;
document.getElementById('closeSlEdit').onclick = () => slEditModal.hidden = true;
slEditModal.onclick = e => { if (e.target === slEditModal) slEditModal.hidden = true; };

export function renderMischModus() {
  mischTbody.innerHTML = '';
  slGetRows().forEach(r => {
    if (!r.lied.trim()) return;
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="nr">${esc(r.nr)}</td>
      <td class="lied">${esc(r.lied)}</td>
      <td>${esc(r.stimme)}</td>
      <td>${esc(r.instrument)}</td>
      <td class="bemerkung">${esc(r.bemerkung)}</td>
    `;
    mischTbody.appendChild(tr);
  });
}

document.getElementById('slOpenMisch').onclick = () => {
  renderMischModus();
  mischModus.classList.add('active');
};
document.getElementById('closeMisch').onclick = () => mischModus.classList.remove('active');
document.addEventListener('keydown', e => { 
  if (e.key === 'Escape') {
    mischModus.classList.remove('active');
    slEditModal.hidden = true;
  }
});

export function slGetRows() {
  return Array.from(slTbody.children).map(tr => {
    const row = {};
    tr.querySelectorAll('input').forEach(i => row[i.getAttribute('data-key')] = i.value);
    return row;
  });
}

// ----- Konfigurationen (Sitzungen) speichern/laden/loeschen -----
const profilSelect = document.getElementById('profilSelect');
const profilMsg = document.getElementById('profilMsg');

export async function ladeSitzungen() {
  try {
    const r = await fetch('/api/sitzungen');
    const j = await r.json();
    return j.sitzungen || {};
  } catch (e) { return {}; }
}

export function aktualisiereProfilDropdown(sitzungen) {
  const cur = profilSelect.value;
  profilSelect.innerHTML = '<option value="">— Profil wählen —</option>';
  Object.keys(sitzungen).sort().forEach(name => {
    const o = document.createElement('option');
    o.value = name; o.textContent = name;
    profilSelect.appendChild(o);
  });
  if (cur && sitzungen[cur]) profilSelect.value = cur;
}

export async function speichereSitzung() {
  const name = document.getElementById('profilName').value.trim();
  if (!name) { profilMsg.textContent = 'Bitte Profil-Name eingeben.'; profilMsg.className = 'err'; return; }
  // Snapshot: Besetzungstext, Setlist, Dateiname, Buehnenpositionen, Edits.
  const inputEdits = (LETZTES && LETZTES.excel && LETZTES.excel.inputs || []).map(e => ({
    zeile: e.zeile, label: e.label, mic: e.mic, sb1: e.sb1, sb2: e.sb2,
  }));
  const busEdits = (LETZTES && LETZTES.excel && LETZTES.excel.busse || []).map(b => ({
    bus: b.bus, name: b.name,
  }));
  try {
    const r = await fetch('/api/sitzungen', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        aktion: 'speichern', name,
        besetzung_text: document.getElementById('txt').value,
        setlist: slGetRows(),
        dateiname: document.getElementById('name').value,
        haupt_pos: HAUPT_POS,
        input_edits: inputEdits,
        bus_edits: busEdits,
      })});
    const j = await r.json();
    if (!j.ok) { profilMsg.textContent = j.error || 'Fehler'; profilMsg.className = 'err'; return; }
    profilMsg.textContent = '✓ Profil „' + name + '“ gespeichert.';
    profilMsg.className = 'okbox';
    aktualisiereProfilDropdown(await ladeSitzungen());
    profilSelect.value = name;
  } catch (e) {
    profilMsg.textContent = 'Fehler beim Speichern.'; profilMsg.className = 'err';
  }
}

export async function ladeSitzung() {
  const name = profilSelect.value;
  if (!name) { profilMsg.textContent = 'Bitte Profil wählen.'; profilMsg.className = 'err'; return; }
  const sitzungen = await ladeSitzungen();
  const s = sitzungen[name];
  if (!s) { profilMsg.textContent = 'Profil nicht gefunden.'; profilMsg.className = 'err'; return; }
  // Besetzung + Dateiname + Setlist wiederherstellen.
  document.getElementById('txt').value = s.besetzung_text || '';
  document.getElementById('name').value = s.dateiname || name;
  slTbody.innerHTML = '';
  slEditTbody.innerHTML = '';
  (s.setlist || []).forEach(r => slAddRow(r));
  // Transiente Buehnenpositionen setzen, dann erzeugen().
  HAUPT_POS = s.haupt_pos ? JSON.parse(JSON.stringify(s.haupt_pos)) : {};
  LETZTES = null;  // alter Stand verwerfen, damit Edits nicht aufs falsche Layout greifen
  await erzeugen();
  // Edits ueber zeile/bus matchen (stabil auch bei veraenderter Besetzung).
  if (LETZTES && LETZTES.excel) {
    const inputs = LETZTES.excel.inputs || [];
    (s.input_edits || []).forEach(e => {
      const inp = inputs.find(x => x.zeile === e.zeile);
      if (inp) {
        inp.label = e.label; inp.mic = e.mic;
        inp.sb1 = e.sb1; inp.sb2 = e.sb2;
      }
    });
    const busse = LETZTES.excel.busse || [];
    (s.bus_edits || []).forEach(be => {
      const b = busse.find(x => x.bus === be.bus);
      if (b) b.name = be.name;
    });
    // Patchliste + Outputs neu rendern, damit Edits sichtbar werden.
    renderePatchliste(LETZTES);
    rendereStagebox('tSB1', LETZTES.excel.stagebox1);
    rendereStagebox('tSB2', LETZTES.excel.stagebox2);
    rendereOutputs(LETZTES);
    regeneriereDownload();
  }
  profilMsg.textContent = '✓ Profil „' + name + '“ geladen.';
  profilMsg.className = 'okbox';
}

export async function loescheSitzung() {
  const name = profilSelect.value;
  if (!name) { profilMsg.textContent = 'Bitte Profil wählen.'; profilMsg.className = 'err'; return; }
  try {
    const r = await fetch('/api/sitzungen', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({aktion: 'loeschen', name})});
    const j = await r.json();
    if (!j.ok) { profilMsg.textContent = j.error || 'Fehler'; profilMsg.className = 'err'; return; }
    profilMsg.textContent = '✓ Profil „' + name + '“ gelöscht.';
    profilMsg.className = 'okbox';
    aktualisiereProfilDropdown(await ladeSitzungen());
    document.getElementById('profilName').value = '';
  } catch (e) {
    profilMsg.textContent = 'Fehler beim Löschen.'; profilMsg.className = 'err';
  }
}

document.getElementById('profilSpeichern').addEventListener('click', speichereSitzung);
document.getElementById('profilLaden').addEventListener('click', ladeSitzung);
document.getElementById('profilLoeschen').addEventListener('click', loescheSitzung);

export function parseSetlisteText(text) {
  // Parst das Format: "- Titel (Stimme, Instrument, [Bemerkung])"
  const rows = [];
  text.split('\n').forEach((line, idx) => {
    line = line.trim();
    if (!line.startsWith('-')) return;
    let liedRaw = line.substring(1).trim();
    let lied = liedRaw, stimme = '', instrument = '', bemerkung = '';
    
    if (liedRaw.endsWith(')')) {
      // Den Metadaten-Block (...) am Ende per Klammer-Tiefe finden, damit Klammern
      // IM Text (z.B. eine Notiz "(laut machen!)") ihn nicht falsch zerschneiden.
      let tiefe = 0, metaOpen = -1;
      for (let i = liedRaw.length - 1; i >= 0; i--) {
        const c = liedRaw[i];
        if (c === ')') tiefe++;
        else if (c === '(') { tiefe--; if (tiefe === 0) { metaOpen = i; break; } }
      }
      if (metaOpen !== -1) {
        lied = liedRaw.substring(0, metaOpen).trim();
        const extraStr = liedRaw.substring(metaOpen + 1, liedRaw.length - 1);
        
        // Suche nach Bemerkungen in eckigen Klammern [ ... ]
        let finalExtraStr = extraStr;
        const mRem = extraStr.match(/\[(.*?)\]/);
        if (mRem) {
          bemerkung = mRem[1].trim();
          finalExtraStr = extraStr.replace(mRem[0], '').trim();
        }
        
        const parts = finalExtraStr.split(',').map(s => s.trim()).filter(s => s !== '');
        // Wir nehmen an: 1. Part ist Stimme, Rest ist Instrument
        if (parts.length > 0) stimme = parts[0];
        if (parts.length > 1) instrument = parts.slice(1).join(', ');
      }
    }
    rows.push({nr: idx + 1, lied, stimme, instrument, bemerkung});
  });
  return rows;
}

document.getElementById('ctLaden').addEventListener('click', async () => {
  const active = document.querySelector('.ev-item.active');
  const eid = active ? active.getAttribute('data-id') : null;
  const msg = document.getElementById('ctMsg');
  if (!eid) { msg.textContent = 'Bitte einen Termin wählen.'; msg.className = 'hint'; return; }
  
  msg.textContent = 'Lade…'; msg.className = 'hint';
  try {
    const [jBes, jSet] = await Promise.all([
      fetch('/api/ct/laden?event=' + encodeURIComponent(eid)).then(r => r.json()),
      fetch('/api/ct/setliste?event=' + encodeURIComponent(eid)).then(r => r.json())
    ]);

    if (!jBes.ok) { msg.textContent = jBes.error || 'Fehler'; msg.className = 'err'; return; }
    document.getElementById('txt').value = jBes.text;
    
    slTbody.innerHTML = '';
    slEditTbody.innerHTML = '';
    if (jSet.ok && jSet.text) {
      const rows = parseSetlisteText(jSet.text);
      rows.forEach(r => slAddRow(r));
    }

    // Datum für den Dateinamen im deutschen Format TT.MM.JJJJ
    const label = active.getAttribute('data-label') || '';
    const m = label.match(/(\d{4})-(\d{2})-(\d{2})/);
    if (m) document.getElementById('name').value = m[3] + '.' + m[2] + '.' + m[1];
    
    msg.textContent = '✓ Besetzung ' + (jSet.text ? '& Setliste ' : '') + 'geladen.';
    msg.className = 'okbox';
    document.getElementById('txt').scrollIntoView({behavior:'smooth', block:'start'});
  } catch (e) {
    msg.textContent = 'Fehler beim Laden.';
    msg.className = 'err';
  }
});

// ----- Name=Wert-Zuordnungen (Spitznamen, Solo-Instrument) laden/speichern -----
function textZuMap(id) {
  const map = {};
  document.getElementById(id).value.split('\n').forEach(line => {
    const i = line.indexOf('=');
    if (i > 0) { const k = line.slice(0, i).trim(); const v = line.slice(i + 1).trim();
                 if (k && v) map[k] = v; }
  });
  return map;
}
export async function ladeMap(api, key, id) {
  const r = await fetch(api); const j = await r.json();
  document.getElementById(id).value = Object.entries(j[key] || {}).map(([k, v]) => k + ' = ' + v).join('\n');
}
export async function speichereMap(api, key, id, msgId) {
  const r = await fetch(api, {method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({[key]: textZuMap(id)})});
  const j = await r.json();
  document.getElementById(msgId).textContent =
    j.ok ? ('✓ ' + j.anzahl + ' gespeichert') : ('Fehler: ' + (j.error||''));
  if (LETZTES) erzeugen();  // Vorschau aktualisieren
}
document.getElementById('spitzSave').addEventListener('click',
  () => speichereMap('/api/spitznamen', 'spitznamen', 'spitz', 'spitzMsg'));
document.getElementById('soloSave').addEventListener('click',
  () => speichereMap('/api/solo_personen', 'solo_personen', 'solo', 'soloMsg'));

// ----- Regeln / Einstellungen -----
export let REGELN = null;
let KAP = 16;  // Stagebox-Kapazitaet (Inputs/Box), aus Einstellungen; mirror fuer rederiveStageboxen
let HAUPT_POS = {};  // transiente Box-Positionen der Hauptseite (NICHT als Default gespeichert)
const MODUS_LABELS = {
  leiter_links: 'Leiter ganz links',
  reine_saenger_mitte: 'Reine Sänger in die Mitte',
  singende_instrumentalisten_vorne: 'Singende Instrumentalisten vorne'
};
const FELD_LABELS = {offset_y:'Abstand', dy:'Zeilenhöhe', w:'Breite', h:'Höhe', x:'x', y:'y',
  stapel_dy:'Stapel-Δy', min_box_w:'min. Breite', max_box_w:'max. Breite', rand:'Rand', luecke:'Lücke'};
function tinp(path, val) {
  return '<input type="text" data-path="' + path + '" value="' + (val == null ? '' : val) + '">';
}
function gruppe(titel, sec, obj) {
  let h = '<h4>' + titel + '</h4><div class="grp">';
  for (const k in obj) h += '<span>' + (FELD_LABELS[k] || k) + '</span>' + tinp(sec + '.' + k, obj[k]);
  return h + '</div>';
}
export async function ladeRegeln() {
  REGELN = await (await fetch('/api/einstellungen')).json();
  KAP = REGELN.stagebox_kapazitaet || 16;
  aktualisiereSbRange();
  let h = '<div class="hint" style="margin-bottom:8px">💡 <b>Positionen</b> der Felder werden direkt in der Vorschau per <b>Ziehen mit der Maus</b> angepasst (automatisch gespeichert).</div>';
  h += '<div class="modus"><h4>Modus</h4>';
  for (const k in REGELN.modus)
    h += '<label><input type="checkbox" data-path="modus.' + k + '" ' + (REGELN.modus[k] ? 'checked' : '') + '> ' + (MODUS_LABELS[k] || k) + '</label>';
  const stapelRollen = (REGELN.unter_drums && REGELN.unter_drums.rollen) || [];
  h += '</div><h4>Backline (hinten)</h4>'
     + '<div class="hint" style="margin-bottom:4px">„im Stapel" = liegt im verschiebbaren Cluster unter den Drums; sonst eigene Position.</div>'
     + '<table><tbody>'
     + '<tr><th>Instrument</th><th>immer hinten</th><th>ab N&nbsp;Sängern hinten</th><th>im Stapel</th></tr>';
  (REGELN.backline_reihenfolge || []).forEach(n => {
    const b = REGELN.backline[n]; if (!b) return;
    h += '<tr><td>' + n + '</td>'
       + '<td><input type="checkbox" data-path="backline.' + n + '.immer" ' + (b.immer ? 'checked' : '') + '></td>'
       + '<td>' + tinp('backline.' + n + '.backline_ab_saengern', b.backline_ab_saengern) + '</td>'
       + '<td><input type="checkbox" class="stapel-cb" data-instr="' + n + '" ' + (stapelRollen.includes(n) ? 'checked' : '') + '></td></tr>';
  });
  h += '</tbody></table>';
  h += '<h4>Stagebox</h4><div class="grp"><span>Inputs pro Box</span>'
     + '<input type="number" min="1" max="16" data-path="stagebox_kapazitaet" value="'
     + (REGELN.stagebox_kapazitaet || 16) + '"></div>';
  const d = REGELN.dimensionen || {};
  h += '<h4>Bühne</h4><div class="grp"><span>Breite</span>'
     + '<input type="number" min="100" step="10" data-path="dimensionen.breite" value="' + (d.breite || '') + '">'
     + '<span>Höhe</span>'
     + '<input type="number" min="100" step="10" data-path="dimensionen.hoehe" value="' + (d.hoehe || '') + '"></div>';
  h += '<div class="row" style="margin-top:10px"><button class="sek" id="posReset">↺ Positionen zurücksetzen</button></div>';
  document.getElementById('regeln').innerHTML = h;
  const pr = document.getElementById('posReset');
  if (pr) pr.addEventListener('click', positionenZuruecksetzen);
  ladeBasisSkizze();
}
async function ladeBasisSkizze() {
  const el = document.getElementById('regelnSvg');
  if (!el) return;
  try {
    const r = await (await fetch('/api/basis_skizze')).json();
    el.innerHTML = r.svg || '';
    initStapel('regelnSvg');
  } catch (e) { el.innerHTML = ''; }
}
// Ebenen-Schalter fuer z-gestapelte Instrumente (data-stack): es ist IMMER nur
// EINE Ebene sichtbar (die anderen komplett ausgeblendet -> kein sichtbares
// Ueberlappen). Ein Klick auf die Box ODER das Zaehler-Badge schaltet zur
// naechsten Ebene; das Badge ("1/4 ▸") zeigt an, dass mehrere uebereinander liegen.
function initStapel(wrapId) {
  const svg = document.querySelector('#' + wrapId + ' svg');
  if (!svg) return;
  const gruppen = {};
  svg.querySelectorAll('[data-stack]').forEach(el => {
    const g = el.getAttribute('data-stack');
    (gruppen[g] = gruppen[g] || []).push(el);
  });
  for (const g in gruppen) {
    const els = gruppen[g];
    const ebenen = [...new Set(els.map(e => +e.getAttribute('data-layer')))].sort((a, b) => a - b);
    if (ebenen.length < 2) continue;
    let aktiv = ebenen[0];
    const badge = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    badge.setAttribute('class', 'stapel-badge');
    svg.appendChild(badge);
    const anwenden = () => {
      let rect = null;
      els.forEach(e => {
        const vorne = +e.getAttribute('data-layer') === aktiv;
        e.style.display = vorne ? '' : 'none';   // nur aktive Ebene sichtbar
        e.style.cursor = 'pointer';
        if (vorne) { e.parentNode.appendChild(e); if (e.tagName.toLowerCase() === 'rect') rect = e; }
      });
      if (rect) {
        badge.setAttribute('x', +rect.getAttribute('x') + +rect.getAttribute('width') - 5);
        badge.setAttribute('y', +rect.getAttribute('y') + 15);
        badge.textContent = (ebenen.indexOf(aktiv) + 1) + '/' + ebenen.length + ' \u25B8';
        svg.appendChild(badge);  // Badge nach vorn
      }
    };
    anwenden();
    const naechste = ev => {
      if (ev.shiftKey) return;   // Shift+Klick = markieren, nicht Ebene wechseln
      ev.stopPropagation();
      aktiv = ebenen[(ebenen.indexOf(aktiv) + 1) % ebenen.length];
      anwenden();
    };
    els.forEach(e => e.addEventListener('click', naechste));
    badge.style.cursor = 'pointer';
    badge.addEventListener('click', naechste);
  }
}
function aktualisiereSbRange() {
  const s1 = document.getElementById('sb1Range'), s2 = document.getElementById('sb2Range');
  if (s1) s1.textContent = '(A1–A' + KAP + ')';
  if (s2) s2.textContent = '(A' + (KAP + 1) + '–A' + (2 * KAP) + ')';
}
// Bestaetigungsdialog (eigenes Fenster) -> Promise<boolean>
function bestaetige(text) {
  return new Promise(resolve => {
    const ov = document.getElementById('confirmModal');
    document.getElementById('confirmText').textContent = text;
    ov.hidden = false;
    const ja = document.getElementById('confirmJa'), nein = document.getElementById('confirmNein');
    const fertig = v => { ov.hidden = true; ja.onclick = null; nein.onclick = null; resolve(v); };
    ja.onclick = () => fertig(true);
    nein.onclick = () => fertig(false);
  });
}
// Default-Positionen (einstellungen.json) zuruecksetzen -- mit Bestaetigung.
async function positionenZuruecksetzen() {
  if (!await bestaetige('Alle gespeicherten Standard-Positionen zurücksetzen? Das kann nicht rückgängig gemacht werden.')) return;
  await fetch('/api/einstellungen', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({aktion: 'reset_positionen'})});
  document.getElementById('regelnMsg').textContent = '✓ Positionen zurückgesetzt';
  ladeBasisSkizze();
  if (LETZTES) erzeugen();
}
// Nur die transienten Verschiebungen DIESER Besetzung verwerfen (Hauptseite) --
// der Default in den Einstellungen bleibt unberuehrt.
function hauptSkizzeReset() {
  HAUPT_POS = {};
  if (LETZTES) erzeugen();
}
function setPath(o, path, val) {
  const ks = path.split('.'); let c = o;
  for (let i = 0; i < ks.length - 1; i++) { c[ks[i]] = c[ks[i]] || {}; c = c[ks[i]]; }
  c[ks[ks.length - 1]] = val;
}
document.getElementById('regeln').addEventListener('change', e => {
  const path = e.target.getAttribute('data-path'); if (!path || !REGELN) return;
  const val = e.target.type === 'checkbox' ? e.target.checked
            : (e.target.value.trim() === '' ? null : Number(e.target.value));
  setPath(REGELN, path, val);
});
document.getElementById('regelnSave').addEventListener('click', async () => {
  const bl = {};
  for (const n in REGELN.backline)
    bl[n] = {immer: !!REGELN.backline[n].immer, backline_ab_saengern: REGELN.backline[n].backline_ab_saengern};
  // Stapel-Mitglieder in backline_reihenfolge-Ordnung sammeln (Reihenfolge = Stapel-Ordnung).
  const stapelRollen = (REGELN.backline_reihenfolge || []).filter(n =>
    document.querySelector('.stapel-cb[data-instr="' + n + '"]:checked'));
  REGELN.unter_drums = Object.assign({}, REGELN.unter_drums, {rollen: stapelRollen});
  const j = await (await fetch('/api/einstellungen', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({aktion: 'form', modus: REGELN.modus, backline: bl,
                          stagebox_kapazitaet: REGELN.stagebox_kapazitaet,
                          dimensionen: REGELN.dimensionen,
                          stapel_rollen: stapelRollen})})).json();
  KAP = REGELN.stagebox_kapazitaet || 16;
  aktualisiereSbRange();
  document.getElementById('regelnMsg').textContent = j.ok ? '✓ gespeichert' : ('Fehler: ' + (j.error||''));
  ladeBasisSkizze();
  if (LETZTES) erzeugen();
});

export async function speicherePosition(key, x, y) {
  const body = {aktion: 'position', key: key, x: Math.round(x), y: Math.round(y)};
  await fetch('/api/einstellungen', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify(body)});
}

// Stagebox-Kapazitaet laden (fuer SB-Bereichspruefung). Der Track-Status wird
// NICHT hier initialisiert: er ist ein abgeleiteter Wert (Multitrack-Zeile) und
// wird nach jedem erzeugen() aus j.track_aktiv gesetzt. Initial bleibt der
// (disabled) Schalter aus.
(async () => {
  try {
    const s = await (await fetch('/api/einstellungen')).json();
    KAP = s.stagebox_kapazitaet || 16;
    aktualisiereSbRange();
  } catch (e) {}
})();

function zeile(zellen) {
  const tr = document.createElement('tr');
  tr.innerHTML = zellen.map(c => '<td>'+c+'</td>').join('');
  return tr;
}

const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const txtZelle = s => (s && String(s).length) ? esc(s) : '<span class="hint">–</span>';
const aPill = s => '<span class="pill">' + s + '</span>';
const td = c => '<td>'+c+'</td>';
const tdN = c => '<td class="num">'+c+'</td>';

function rendereStagebox(tabId, eintraege, stale=false) {
  const tb = document.querySelector('#' + tabId + ' tbody');
  tb.innerHTML = '';
  tb.parentElement.classList.toggle('stale', stale);
  if (!eintraege.length) {
    tb.innerHTML = '<tr><td colspan="4" class="hint">leer</td></tr>';
    return;
  }
  eintraege.forEach(e => {
    const tr = document.createElement('tr');
    tr.innerHTML = tdN(e.nr) + tdN(aPill(e.source)) + td(txtZelle(e.label)) + td(txtZelle(e.mic));
    tb.appendChild(tr);
  });
}

function ersetzeInSkizze(alt, neu) {
  if (!alt) return;
  const svg = document.querySelector('#svg svg'); if (!svg) return;
  svg.querySelectorAll('text').forEach(t => {
    if (t.textContent === alt) t.textContent = neu;
  });
}

function skizze_data_update(alt, neu) {
  if (!alt || !LETZTES || !LETZTES.skizze_doc) return;
  const doc = LETZTES.skizze_doc;
  const elems = doc.elements || (doc.scenes && doc.scenes[0] && doc.scenes[0].elements) || [];
  elems.forEach(e => {
    if (e.type === 'text' && (e.text === alt || e.originalText === alt)) {
      e.text = neu;
      e.originalText = neu;
    }
  });
}

function rederiveStageboxen(j) {
  const box = (sbField, offset) => {
    const out = [];
    for (let k = 1; k <= KAP; k++) {
      const inp = j.excel.inputs.find(x => x[sbField] === k);
      if (inp && (inp.label || inp.mic))
        out.push({nr: k, source: 'A' + (k + offset), label: inp.label, mic: inp.mic});
    }
    return out;
  };
  j.excel.stagebox1 = box('sb1', 0);
  j.excel.stagebox2 = box('sb2', KAP);
}

function findeDuplikate(j) {
  // Sucht doppelte Stagebox-Slots. Schlüssel ist die Excel-Zeile, nicht
 // der Listen-Index, damit die Logik stabil bleibt, wenn die inputs-
 // Liste die volle Excel-Tabelle enthaelt (32 Zeilen, belegt oder leer).
 const dupe = (feld) => {
    const counts = new Map();
    (j.excel.inputs || []).forEach((inp) => {
      if (inp[feld] != null) {
        if (!counts.has(inp[feld])) counts.set(inp[feld], []);
        counts.get(inp[feld]).push(inp.zeile);
      }
    });
    const zDupes = new Set();
    for (const arr of counts.values()) if (arr.length > 1) arr.forEach(z => zDupes.add(z));
    return {zeilen: [...zDupes], werte: [...counts].filter(([,a]) => a.length > 1).map(([w]) => w).sort((a,b) => a-b)};
  };
  return {sb1: dupe('sb1'), sb2: dupe('sb2')};
}

// Speichert den aktuellen DOM-Wert eines Patchlisten-Feldes in
// LETZTES.excel.inputs (ohne renderePatchliste / regeneriereDownload).
// Wird vom blur-Handler UND von der Pfeiltasten-Navigation genutzt.
export function patchWertSpeichern(el) {
  const zeile = +el.dataset.zeile, feld = el.dataset.feld;
  const inp = LETZTES.excel.inputs.find(x => x.zeile === zeile);
  if (!inp) return;
  const t = el.textContent.trim();
  if (feld === 'sb1' || feld === 'sb2') {
    let v = null;
    if (t && t !== '–') { const n = parseInt(t, 10); if (Number.isFinite(n) && n >= 1 && n <= 16) v = n; }
    if (inp[feld] !== v) { inp[feld] = v; if (v != null) { const a = feld === 'sb1' ? 'sb2' : 'sb1'; inp[a] = null; } }
  } else {
    if (inp[feld] !== t && t !== '–') { inp[feld] = t; }
  }
}

// Speichert den aktuellen DOM-Wert eines Output-/Bus-Feldes in
// LETZTES.excel.busse. Wird von der Pfeiltasten-Navigation genutzt
// (analog zu patchWertSpeichern fuer die Inputs).
export function busWertSpeichern(el) {
  const bus = +el.dataset.bus;
  const b = (LETZTES.excel.busse || []).find(x => x.bus === bus);
  if (!b) return;
  const t = el.textContent.trim();
  if (b.name !== t) b.name = t;
}
function renderePatchliste(j) {
  const tb = document.querySelector('#tInputs tbody');
  tb.innerHTML = '';
  const inputs = j.excel.inputs || [];
  if (!inputs.length) {
    tb.innerHTML = '<tr><td colspan="4" class="hint">keine Inputs</td></tr>';
    return;
  }
  const dupes = findeDuplikate(j);
  const showNr = n => (n != null) ? String(n) : '–';
  inputs.forEach((e) => {
    // e.zeile ist die stabile Identitaet (Excel-Zeile 5..38). Frueher
 // hatten wir data-idx=Listen-Index; sobald die Liste sortiert/erweitert
 // wurde, zeigten die Edits auf den falschen Kanal. Mit data-zeile bleibt
 // jedes <span> fest an seine Excel-Zeile gebunden.
    const z = e.zeile;
    const leer = !e.label && !e.mic && e.sb1 == null && e.sb2 == null;
    const tr = document.createElement('tr');
    if (leer) tr.classList.add('leer');
    const labelHtml = e.label
      ? '<span class="editable" contenteditable="true" data-zeile="'+z+'" data-feld="label" title="klicken zum Ändern">'
        + esc(e.label) + '</span>'
      : '<span class="editable hint" contenteditable="true" data-zeile="'+z+'" data-feld="label" title="klicken zum Ändern">–</span>';
    const micHtml = e.mic
      ? '<span class="editable" contenteditable="true" data-zeile="'+z+'" data-feld="mic" title="klicken zum Ändern">'
        + esc(e.mic) + '</span>'
      : '<span class="editable hint" contenteditable="true" data-zeile="'+z+'" data-feld="mic" title="klicken zum Ändern">–</span>';
    const sb1Class = 'pill edit' + (dupes.sb1.zeilen.includes(z) ? ' dup' : '');
    const sb2Class = 'pill edit' + (dupes.sb2.zeilen.includes(z) ? ' dup' : '');
    tr.innerHTML = '<td>' + labelHtml + '</td>' + '<td>' + micHtml + '</td>'
      + '<td class="num"><span class="'+sb1Class+'" contenteditable="true" data-zeile="'+z+'" data-feld="sb1" title="SB1 (1–16)">'
      + showNr(e.sb1) + '</span></td>'
      + '<td class="num"><span class="'+sb2Class+'" contenteditable="true" data-zeile="'+z+'" data-feld="sb2" title="SB2 (1–16)">'
      + showNr(e.sb2) + '</span></td>';
    tb.appendChild(tr);
  });

  tb.querySelectorAll('.pill.edit').forEach(el => {
    el.addEventListener('keydown', ev => { if (ev.key === 'Enter') { ev.preventDefault(); el.blur(); } });
    el.addEventListener('blur', () => {
      if (window._arrowMoving) return;  // Pfeiltasten-Navigation: kein blur-Handler
      const zeile = +el.dataset.zeile, feld = el.dataset.feld;
      const inp = LETZTES.excel.inputs.find(x => x.zeile === zeile);
      if (!inp) return;
      const t = el.textContent.trim();
      let val = null;
      if (t && t !== '–') {
        const n = parseInt(t, 10);
        if (Number.isFinite(n) && n >= 1 && n <= 16) val = n;
      }
      if (inp[feld] !== val) {
        inp[feld] = val;
        const andere = (feld === 'sb1') ? 'sb2' : 'sb1';
        if (val != null) inp[andere] = null;
        const d = findeDuplikate(LETZTES);
        const stale = (d.sb1.zeilen.length > 0 || d.sb2.zeilen.length > 0);
        if (!stale) rederiveStageboxen(LETZTES);
        rendereStagebox('tSB1', LETZTES.excel.stagebox1, stale);
        rendereStagebox('tSB2', LETZTES.excel.stagebox2, stale);
        renderePatchliste(LETZTES);
        zeigePatchWarn(d);
        regeneriereDownload();
      }
    });
  });
  tb.querySelectorAll('.editable').forEach(el => {
    el.addEventListener('keydown', ev => { if (ev.key === 'Enter') { ev.preventDefault(); el.blur(); } });
    el.addEventListener('focus', () => { el.classList.remove('hint'); });
    el.addEventListener('blur', () => {
      if (window._arrowMoving) return;  // Pfeiltasten-Navigation
      const zeile = +el.dataset.zeile, feld = el.dataset.feld;
      const inp = LETZTES.excel.inputs.find(x => x.zeile === zeile);
      const newVal = el.textContent.trim();
      if (newVal === '–') el.classList.add('hint');
      const altVal = inp[feld] || '';
      if (altVal === newVal) return;
      if (feld === 'label' && altVal) {
        ersetzeInSkizze(altVal, newVal);
        skizze_data_update(altVal, newVal);
      }
      inp[feld] = newVal;
      rederiveStageboxen(LETZTES);
      renderePatchliste(LETZTES);
      rendereStagebox('tSB1', LETZTES.excel.stagebox1);
      rendereStagebox('tSB2', LETZTES.excel.stagebox2);
      regeneriereDownload();
    });
  });
  zeigePatchWarn(dupes);
}

// Outputs (Monitor -> Mix-Bus): Bus-Namen editierbar. Aenderung landet in
// LETZTES.excel.busse und wird via regeneriereDownload() an Excel (J-Spalte)
// und X32-Scene (Bus-Config) propagiert.
function rendereOutputs(j) {
  const outT = document.querySelector('#tOutputs tbody');
  outT.innerHTML = '';
  const busse = j.excel.busse || [];
  if (!busse.length) {
    outT.innerHTML = '<tr><td colspan="2" class="hint">keine Monitor-Busse</td></tr>';
    return;
  }
  busse.forEach(b => {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>' + aPill('Mix ' + b.bus) + '</td>'
      + '<td><span class="editable" contenteditable="true" data-bus="' + b.bus
      + '" title="klicken zum Ändern">' + esc(b.name) + '</span></td>';
    outT.appendChild(tr);
  });
  outT.querySelectorAll('.editable[data-bus]').forEach(el => {
    el.addEventListener('keydown', ev => { if (ev.key === 'Enter') { ev.preventDefault(); el.blur(); } });
    el.addEventListener('blur', () => {
      if (window._arrowMoving) return;  // Pfeiltasten-Navigation: kein blur-Handler
      const bus = +el.dataset.bus;
      const b = (LETZTES.excel.busse || []).find(x => x.bus === bus);
      if (!b) return;
      const neu = el.textContent.trim();
      if (b.name === neu) return;
      b.name = neu;
      regeneriereDownload();
    });
  });
}

function zeigePatchWarn(d) {
  const el = document.getElementById('patchWarn');
  const msgs = [];
  if (d.sb1.werte.length) msgs.push('<b>SB1:</b> doppelte A-Nummer ' + d.sb1.werte.join(', '));
  if (d.sb2.werte.length) msgs.push('<b>SB2:</b> doppelte A-Nummer ' + d.sb2.werte.join(', '));
  if (msgs.length) {
    el.innerHTML = '⚠ ' + msgs.join(' &nbsp;·&nbsp; ') + ' &nbsp;–&nbsp; Stageboxen werden erst aktualisiert, wenn das behoben ist.';
    el.hidden = false;
  } else el.hidden = true;
}

export async function erzeugen() {
  const text = document.getElementById('txt').value;
  const name = document.getElementById('name').value || 'besetzung';
  const btn = document.getElementById('go'); btn.disabled = true; btn.textContent = 'Erzeuge…';
  const erg = document.getElementById('ergebnis'); erg.style.display = 'block';
  const fehler = document.getElementById('fehler'); fehler.innerHTML = '';
  try {
    const r = await fetch('/api/erzeugen', {method:'POST', headers:{'Content-Type':'application/json'},
              body: JSON.stringify({text, name, positionen: HAUPT_POS})});
    const j = await r.json();
    if (!j.ok) { fehler.innerHTML = '<div class="err">'+ (j.error||'Fehler') +'</div>'; return; }
    LETZTES = j;
    // Unveraenderliche Referenz auf den initialen inputs-Stand. Wird im
    // Regen-Pfad an den Server geschickt, damit der Server die Zeile
 // (F/G-Spalte) findet, an der der Input urspruenglich sass -- sonst
 // mutieren die blur-Handler die gleichen inputs[], der Server sieht
 // nur den Endstand und kann keine Excel-Zeile mehr zuordnen.
    LETZTES.basis_inputs = JSON.parse(JSON.stringify(j.excel.inputs));
    LETZTES.basis_setzwerte = JSON.parse(JSON.stringify(j.setzwerte));
    document.getElementById('kuerzel').textContent = j.kuerzel ? ('Kürzel: '+j.kuerzel) : '';
    document.getElementById('svg').innerHTML = j.svg;
    initStapel('svg');
    // Multitrack in der Besetzung? Server hat track_aktiv automatisch gesetzt.
    document.getElementById('trackAktiv').checked = !!j.track_aktiv;

    const pt = document.querySelector('#tPersonen tbody'); pt.innerHTML = '';
    j.personen.forEach(p => pt.appendChild(zeile([esc(p.name), '<span class="hint">'+esc(p.rollen.join(', '))+'</span>'])));

    // ----- Patchliste wie im Belegungsplan: Inputs (mit A-Nr), Stageboxen, Outputs -----
    const nrZelle = n => (n != null) ? '<span class="pill">'+n+'</span>' : '';
    const rowH = html => { const tr = document.createElement('tr'); tr.innerHTML = html; return tr; };
    renderePatchliste(j);
    rendereStagebox('tSB1', j.excel.stagebox1);
    rendereStagebox('tSB2', j.excel.stagebox2);
    rendereOutputs(j);

    const sc = j.scene || {};
    const si = document.getElementById('sceneInfo');
    if (sc.busse && (sc.busse.length || (sc.voc||[]).length)) {
      let s = 'Busse: ' + (sc.busse.length ? sc.busse.map(b => 'B'+b.bus+'='+esc(b.name)).join(', ') : '–');
      if (sc.engpass && sc.engpass.length)
        s += '<br><span class="frei">⚠ SB2-Engpass: ' + sc.engpass.map(e=>'Ch'+e.kanal+'=A'+e.source).join(', ')
           + ' (max. 16/Stagebox – in der Skizze etwas nach links ziehen).</span>';
      si.innerHTML = s;
    } else si.innerHTML = '';

    // ----- Kapazitäts-Status: passt das Setting aufs Pult? -----
    const ew = document.getElementById('excelWarn');
    const vocAnz = (j.excel.voc || []).length;
    const sb1n = (j.excel.stagebox1 || []).length, sb2n = (j.excel.stagebox2 || []).length;
    const probleme = [];
    (j.excel.ueberzaehlige_saenger || []).forEach(s =>
      probleme.push('Sänger ' + s.nr + ' („' + esc(s.name) + '“) bekommt keinen Voc-Kanal (nur ' + vocAnz + ' Voc-Kanäle).'));
    (j.excel.monitor_ueberlauf || []).forEach(m =>
      probleme.push('Monitor-Überlauf ' + m.seite + ': ' + m.anzahl + ' Personen, aber nur ' + m.plaetze + ' Mix-Plätze.'));
    if (sc.engpass && sc.engpass.length)
      probleme.push('Stagebox-Engpass: mehr als 16 Eingänge auf einer Box (' + sc.engpass.map(e => 'A' + e.source).join(', ') + ').');
    let warn = '';
    if (probleme.length)
      warn += '<div class="warnbox"><b>⚠ Passt so nicht vollständig aufs Mischpult:</b><ul>'
        + probleme.map(p => '<li>' + p + '</li>').join('') + '</ul></div>';
    else
      warn += '<div class="okbox">✓ Passt aufs Mischpult — Stagebox 1: ' + sb1n + '/16, Stagebox 2: ' + sb2n + '/16, ' + vocAnz + ' Voc-Kanäle.</div>';
    if (j.excel.balance && j.excel.balance.length)
      warn += '<div class="hint">⚖ Automatischer Stagebox-Ausgleich: '
        + j.excel.balance.map(b => b.label + ' ' + b.anzahl + '× ' + b.von + '→' + b.nach).join(', ') + '</div>';
    ew.innerHTML = warn;
    erg.scrollIntoView({behavior:'smooth', block:'start'});
  } catch (err) {
    fehler.innerHTML = '<div class="err">'+ err +'</div>';
  } finally {
    btn.disabled = false; btn.textContent = 'Erzeugen';
  }
}
// ----- Regenerate-Pfad: UI-Edits -> neue Excel/Scene-Bytes -----
// Wird nach jeder Label/Mic/SB-Aenderung in der Patchliste aufgerufen
// (debounced), damit dlExcel/dlScene die frischen Bytes liefern, ohne
// dass der Server plane() neu durchlaufen muss.
let regenTimer = null;
function regeneriereDownload() {
  if (!LETZTES || !LETZTES.setzwerte) return;   // vor erstem erzeugen()
  clearTimeout(regenTimer);
  regenTimer = setTimeout(async () => {
    try {
      // plane_erg: alles, was regeneriere_excel_und_scene braucht.
      // setzwerte + excel reichen; skizze_doc wuerde nur Bandbreite kosten.
      // basis_inputs/basis_setzwerte sind der UNVERAENDERLICHE Initial-Stand
      // -- darauf arbeitet der Server, weil die blur-Handler die normalen
      // inputs[]/setzwerte zwischenzeitlich mutieren.
      const plane_erg = {
        setzwerte: LETZTES.basis_setzwerte || LETZTES.setzwerte,
        basis_inputs: LETZTES.basis_inputs || LETZTES.excel.inputs,
        excel: LETZTES.excel,
        // Skizzendaten mitschicken, damit der Server die Buehnenskizze auch in
        // die regenerierte .xlsx einbettet (sonst fehlt sie nach jedem Edit).
        skizze_data: LETZTES.skizze_data,
      };
      // Edits = aktuelle inputs-Liste (komplett, nur label/mic/sb1/sb2) und
      // die Monitor-Bus-Namen (Outputs-Tabelle).
      const edits = {
        inputs: (LETZTES.excel.inputs || []).map(e => ({
          label: e.label, mic: e.mic, sb1: e.sb1, sb2: e.sb2,
        })),
        busse: (LETZTES.excel.busse || []).map(b => ({ bus: b.bus, name: b.name })),
      };
      const r = await fetch('/api/regenerate', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({plane_erg, edits}),
      });
      const j = await r.json();
      if (!j.ok) {
        // Server-Fehler still ignorieren -- der sichtbare Tabellen-State
        // stimmt ja, nur der Download waere veraltet. Beim naechsten
        // plane() passts wieder.
        return;
      }
      LETZTES.excel_b64 = j.excel_b64;
      LETZTES.scene_data = j.scene_data;
      // setzwerte spiegeln -- Folge-Edits muessen auf dem aktuellen Stand
      // aufsetzen, sonst gehen vorherige Aenderungen verloren.
      if (j.setzwerte && Object.keys(j.setzwerte).length) {
        LETZTES.setzwerte = j.setzwerte;
      }
      // excel-Bericht-Dict aktualisieren (stagebox1/2, inputs)
      if (j.excel) {
        LETZTES.excel.inputs = j.excel.inputs || LETZTES.excel.inputs;
        LETZTES.excel.stagebox1 = j.excel.stagebox1 || LETZTES.excel.stagebox1;
        LETZTES.excel.stagebox2 = j.excel.stagebox2 || LETZTES.excel.stagebox2;
      }
    } catch (e) { /* still ignorieren */ }
  }, 200);  // 200ms debounce -- schneller als der User tippen kann
}
// ----- Auswahl + Drag&Drop der Felder (Hauptseite #svg + Einstellungs-Skizze #regelnSvg) -----
// Markieren: Shift+Klick auf ein Feld (toggelt) ODER Auswahlrechteck auf freier
// Flaeche aufziehen. Ein markiertes Feld ziehen verschiebt ALLE markierten gemeinsam.
function dragSetup(wrapId, onDrop, speicherFn) {
  const wrap = document.getElementById(wrapId);
  if (!wrap) return;
  let z = null;        // Zieh-Status
  let band = null;     // Auswahlrechteck-Status
  const sel = new Set();  // markierte Box-Schluessel
  const aktSvg = () => wrap.querySelector('svg');
  function pt(svg, e) {
    const r = svg.getBoundingClientRect(), vb = svg.viewBox.baseVal;
    return {x: vb.x + (e.clientX - r.left) * vb.width / r.width,
            y: vb.y + (e.clientY - r.top) * vb.height / r.height};
  }
  function markiere() {
    const svg = aktSvg(); if (!svg) return;
    svg.querySelectorAll('rect.markiert').forEach(r => r.classList.remove('markiert'));
    sel.forEach(k => svg.querySelectorAll('rect[data-key="' + (window.CSS ? CSS.escape(k) : k) + '"]')
      .forEach(r => r.classList.add('markiert')));
  }
  function zugElemente(svg, keys) {
    return keys.map(k => {
      const r = svg.querySelector('rect[data-key="' + (window.CSS ? CSS.escape(k) : k) + '"]');
      return r ? {k, els: svg.querySelectorAll('[data-key="' + (window.CSS ? CSS.escape(k) : k) + '"]'),
                  baseX: parseFloat(r.getAttribute('x')), baseY: parseFloat(r.getAttribute('y'))} : null;
    }).filter(Boolean);
  }
  wrap.addEventListener('mousedown', e => {
    const svg = aktSvg(); if (!svg) return;
    const t = e.target.closest('[data-key]');
    const key = t && t.getAttribute('data-key');
    if (e.shiftKey) {                       // Einzel-Markierung toggeln
      if (key) { sel.has(key) ? sel.delete(key) : sel.add(key); markiere(); }
      e.preventDefault(); return;
    }
    if (!t) {                               // freie Flaeche -> Auswahlrechteck
      const r = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      r.setAttribute('class', 'auswahl-band');
      svg.appendChild(r);
      band = {start: pt(svg, e), el: r};
      e.preventDefault(); return;
    }
    // Gestapelte Box (data-stack, Einstellungs-Skizze): den GANZEN Stapel als Gruppe
    // verschieben und als EIN Anker ("Stapel") speichern -> kein Einzel-Pinning, die
    // Hauptseite bleibt nebeneinander. Reiner Klick (kein Move) schaltet die Ebene.
    if (t.hasAttribute('data-stack')) {
      const grp = t.getAttribute('data-stack');
      const anker = svg.querySelector('rect[data-stack="' + grp + '"][data-layer="0"]') || t;
      z = {teile: [{k: 'Stapel', els: svg.querySelectorAll('[data-stack="' + grp + '"]'),
                    baseX: parseFloat(anker.getAttribute('x')), baseY: parseFloat(anker.getAttribute('y'))}],
           start: pt(svg, e)};
      e.preventDefault(); return;
    }
    const keys = (sel.has(key) && sel.size > 1) ? [...sel] : [key];
    z = {teile: zugElemente(svg, keys), start: pt(svg, e)};
    e.preventDefault();
  });
  window.addEventListener('mousemove', e => {
    const svg = aktSvg(); if (!svg) return;
    if (band) {
      const p = pt(svg, e), x0 = Math.min(p.x, band.start.x), y0 = Math.min(p.y, band.start.y);
      band.el.setAttribute('x', x0); band.el.setAttribute('y', y0);
      band.el.setAttribute('width', Math.abs(p.x - band.start.x));
      band.el.setAttribute('height', Math.abs(p.y - band.start.y));
      return;
    }
    if (!z) return;
    const p = pt(svg, e); z.dx = p.x - z.start.x; z.dy = p.y - z.start.y;
    z.teile.forEach(t => t.els.forEach(el =>
      el.setAttribute('transform', 'translate(' + z.dx + ',' + z.dy + ')')));
  });
  window.addEventListener('mouseup', async () => {
    const svg = aktSvg();
    if (band) {                             // Felder im Rechteck markieren
      const b = band.el.getBBox(); band.el.remove(); band = null;
      if (b.width < 3 && b.height < 3) { sel.clear(); markiere(); return; }  // reiner Klick = Auswahl loeschen
      if (svg) svg.querySelectorAll('rect[data-key]').forEach(r => {
        const cx = +r.getAttribute('x') + r.getAttribute('width') / 2;
        const cy = +r.getAttribute('y') + r.getAttribute('height') / 2;
        if (cx >= b.x && cx <= b.x + b.width && cy >= b.y && cy <= b.y + b.height)
          sel.add(r.getAttribute('data-key'));   // additiv -- bestehende Markierung bleibt
      });
      markiere(); return;
    }
    if (!z) return; const cur = z; z = null;
    if (cur.dx === undefined || (Math.abs(cur.dx) < 1 && Math.abs(cur.dy) < 1)) return;
    for (const t of cur.teile) await speicherFn(t.k, t.baseX + cur.dx, t.baseY + cur.dy);
    await onDrop();
    markiere();   // Markierung nach dem Neu-Rendern wieder anzeigen (bleibt bestehen)
  });
}
// Hauptseite: Drags sind TRANSIENT (nur fuer diese Besetzung, kein Default-Write).
dragSetup('svg', () => erzeugen(),
  (key, x, y) => { HAUPT_POS[key] = {x: Math.round(x), y: Math.round(y)}; });
// Einstellungen: Drags definieren den Default (-> einstellungen.json).
dragSetup('regelnSvg', () => ladeBasisSkizze(), speicherePosition);

function download(name, blob) {
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = name; a.click(); URL.revokeObjectURL(a.href);
}
document.getElementById('skizzeReset').addEventListener('click', hauptSkizzeReset);

document.getElementById('dlSkizze').addEventListener('click', () => {
  if (!LETZTES) return;
  download(LETZTES.skizze_name, new Blob([LETZTES.skizze_data], {type:'application/json'}));
});
document.getElementById('dlExcel').addEventListener('click', () => {
  if (!LETZTES) return;
  const bin = atob(LETZTES.excel_b64); const arr = new Uint8Array(bin.length);
  for (let i=0;i<bin.length;i++) arr[i]=bin.charCodeAt(i);
  download(LETZTES.excel_name,
    new Blob([arr], {type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}));
});
document.getElementById('dlScene').addEventListener('click', () => {
  if (!LETZTES || !LETZTES.scene_data) { alert('Keine Szenen-Vorlage gefunden.'); return; }
  download(LETZTES.scene_name, new Blob([LETZTES.scene_data], {type:'text/plain'}));
});

// Profil-Dropdown beim Start füllen.
(async () => { aktualisiereProfilDropdown(await ladeSitzungen()); })();
