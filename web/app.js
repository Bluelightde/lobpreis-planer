import { ctStatus, cacheLeeren, renderKalender } from './ct.js';
import { erzeugen, ladeRegeln, ladeMap, speichereMap, LETZTES, patchWertSpeichern, busWertSpeichern } from './ui.js';

// ----- Zentral: "Server nicht erreichbar"-Hinweis -----
// Alle API-Aufrufe laufen per fetch() gegen den eigenen lokalen Server. Schlaegt
// einer mit Netzwerkfehler fehl (Server beendet/abgestuerzt), zeigen wir eine
// klare Leiste statt stummer Konsolenfehler oder haengender Buttons. Der Wrapper
// sitzt zentral, damit jeder Aufruf in ui.js/ct.js automatisch abgedeckt ist.
const _origFetch = window.fetch.bind(window);
let _serverWegTimer = null;

window.fetch = async (...args) => {
  try {
    const antwort = await _origFetch(...args);
    serverErreichbar();        // erfolgreicher Call -> Hinweis ggf. wieder ausblenden
    return antwort;
  } catch (err) {
    zeigeServerWeg();
    throw err;                 // bestehende Handler verhalten sich unveraendert weiter
  }
};

function zeigeServerWeg() {
  const el = document.getElementById('serverWeg');
  if (el) el.hidden = false;
  // Im Hintergrund pruefen, ob der Server zurueck ist (eigenes fetch, damit der
  // Wrapper nicht erneut anschlaegt) -> dann automatisch ausblenden.
  if (!_serverWegTimer) {
    _serverWegTimer = setInterval(() => {
      _origFetch('/favicon.svg', { cache: 'no-store' }).then(serverErreichbar).catch(() => {});
    }, 2000);
  }
}

function serverErreichbar() {
  const el = document.getElementById('serverWeg');
  if (el && !el.hidden) el.hidden = true;
  if (_serverWegTimer) { clearInterval(_serverWegTimer); _serverWegTimer = null; }
}

document.getElementById('serverNeuLaden').addEventListener('click', () => location.reload());

// ----- Server beenden beim Schliessen des Browsers -----
// pagehide feuert nur beim tatsaechlichen Verlassen der Seite (Tab/Fenster
// schliessen, Navigation, Reload) -- NICHT beim blossen Tab-Wechsel oder
// Minimieren. visibilitychange:hidden waere falsch: es feuert auch beim
// Wegklicken auf einen anderen Tab und wuerde den Server toeten, waehrend der
// Nutzer nur kurz wegschaut (Folge: dauerhaftes rotes "Server weg"-Banner).
// Bei e.persisted (bfcache) bleibt die Seite am Leben -> kein Shutdown.
// Beim Reload feuert pagehide -> Shutdown wird geplant, aber der erste GET der
// neu geladenen Seite bricht den 3s-Timer wieder ab.
window.addEventListener('pagehide', (e) => {
  if (e.persisted) return;
  navigator.sendBeacon('/api/shutdown');
});

// ----- Dark Mode -----
// Klasse liegt auf <html> (documentElement); das Theme wird bereits im <head>
// (Inline-Script) vor dem ersten Rendern gesetzt -> kein Aufblitzen im Light Mode.
function setzeTheme(dark) {
  document.documentElement.classList.toggle('dark', dark);
  document.getElementById('theme').textContent = dark ? '☀️ Light' : '🌙 Dark';
  try { localStorage.setItem('lp-theme', dark ? 'dark' : 'light'); } catch (e) {}
}
document.getElementById('theme').addEventListener('click',
  () => setzeTheme(!document.documentElement.classList.contains('dark')));
// Button-Text mit dem bereits angewandten Zustand synchronisieren.
setzeTheme(document.documentElement.classList.contains('dark'));

// ----- Einstellungen-Modal -----
const modal = document.getElementById('modal');
document.getElementById('openSettings').addEventListener('click', () => { modal.hidden = false; ladeRegeln(); });
document.getElementById('closeSettings').addEventListener('click', () => { modal.hidden = true; });
modal.addEventListener('click', e => { if (e.target === modal) modal.hidden = true; });
document.addEventListener('keydown', e => { if (e.key === 'Escape') modal.hidden = true; });

document.getElementById('go').addEventListener('click', erzeugen);


// Patchliste zurücksetzen: erzeugt den Plan neu aus dem Text (löscht alle
// manuellen Edits an Label, Mic, Stagebox-Slots).
document.getElementById('patchReset').addEventListener('click', () => {
  if (confirm('Patchliste wirklich zurücksetzen? Alle manuellen Änderungen gehen verloren.')) {
    erzeugen();
  }
});

// Pfeiltasten-Navigation in der Patchliste: ←→ wechseln das Feld, ↑↓ die Zeile.
// contenteditable frisst Pfeiltasten selbst (Cursor-Wanderung) — unser
// preventDefault() unterdrückt das. Nach dem Fokus-Wechsel den ganzen
// Inhalt des Ziels selektieren, damit direktes Tippen ihn ersetzt.
function _selectAll(el) {
  const r = document.createRange();
  r.selectNodeContents(el);
  const s = window.getSelection();
  s.removeAllRanges();
  s.addRange(r);
}
document.getElementById('tInputs').addEventListener('keydown', (e) => {
  if (!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key)) return;
  const el = e.target;
  if (!el || !el.dataset.zeile || !el.dataset.feld) return;
  e.preventDefault();
  const zeile = +el.dataset.zeile;
  const feld = el.dataset.feld;
  const rows = Array.from(document.querySelectorAll('#tInputs tbody tr'));
  const currentIdx = rows.findIndex(tr => tr.querySelector(`[data-zeile="${zeile}"]`));
  if (currentIdx === -1) return;
  let nextEl = null;
  if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    const felder = ['label', 'mic', 'sb1', 'sb2'];
    const fi = felder.indexOf(feld);
    const delta = e.key === 'ArrowRight' ? 1 : -1;
    const nextFi = fi + delta;
    if (nextFi < 0 || nextFi >= felder.length) return;
    nextEl = rows[currentIdx].querySelector(`[data-feld="${felder[nextFi]}"]`);
  } else {
    const delta = e.key === 'ArrowUp' ? -1 : 1;
    const nextIdx = currentIdx + delta;
    if (nextIdx < 0 || nextIdx >= rows.length) return;
    nextEl = rows[nextIdx].querySelector(`[data-feld="${feld}"]`);
  }
  if (!nextEl) return;
  // Wert der aktuellen Zelle ggf. speichern, BEVOR der Fokus weitergeht.
  // Der blur-Handler wuerde das normalerweise tun, aber wir setzen gleich
  // _arrowMoving und ueberspringen ihn.
  const inp = LETZTES.excel.inputs.find(x => x.zeile === zeile);
  // Wert speichern BEVOR der Fokus weitergeht (blur-Handler wird durch
  // _arrowMoving uebersprungen). patchWertSpeichern ist die gemeinsame
  // Logik aus ui.js, kein Duplikat des blur-Handlers.
  if (inp) patchWertSpeichern(el);
  window._arrowMoving = true;
  nextEl.focus();
  requestAnimationFrame(() => {
    window._arrowMoving = false;
    if (nextEl) _selectAll(nextEl);
  });
});
// Outputs (Monitor-Namen): nur eine editierbare Spalte -> Hoch/Runter zwischen
// den Bus-Zeilen. Gleiche Logik wie bei den Inputs (Wert vor dem Fokuswechsel
// speichern, blur ueberspringen, Ziel-Inhalt selektieren).
document.getElementById('tOutputs').addEventListener('keydown', (e) => {
  if (!['ArrowUp', 'ArrowDown'].includes(e.key)) return;
  const el = e.target;
  if (!el || !el.dataset.bus) return;
  e.preventDefault();
  const rows = Array.from(document.querySelectorAll('#tOutputs tbody tr'));
  const bus = +el.dataset.bus;
  const currentIdx = rows.findIndex(tr => tr.querySelector(`[data-bus="${bus}"]`));
  if (currentIdx === -1) return;
  const delta = e.key === 'ArrowUp' ? -1 : 1;
  const nextIdx = currentIdx + delta;
  if (nextIdx < 0 || nextIdx >= rows.length) return;
  const nextEl = rows[nextIdx].querySelector('[data-bus]');
  if (!nextEl) return;
  busWertSpeichern(el);   // Wert speichern, BEVOR der Fokus weitergeht
  window._arrowMoving = true;
  nextEl.focus();
  requestAnimationFrame(() => {
    window._arrowMoving = false;
    _selectAll(nextEl);
  });
});
// ChurchTools-Status aktualisieren
ctStatus();

ladeMap('/api/spitznamen', 'spitznamen', 'spitz');
ladeMap('/api/solo_personen', 'solo_personen', 'solo');
ladeRegeln();
if (new URLSearchParams(location.search).get('settings') === '1') modal.hidden = false;

// Optionaler Deep-Link ?auto=NAME (lädt eine Datei aus besetzungen/ und erzeugt direkt).
(async () => {
  const auto = new URLSearchParams(location.search).get('auto');
  if (!auto) return;
  const r = await fetch('/api/laden?name=' + encodeURIComponent(auto));
  const j = await r.json();
  if (j.text) {
    document.getElementById('txt').value = j.text;
    document.getElementById('name').value = auto.replace(/\.txt$/, '');
    erzeugen();
  }
})();
