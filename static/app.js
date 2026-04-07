// ── Simple keyboard mapping ─────────────────────────────────────────────────
const SIMPLE_KEY_ORDER = ['KeyA', 'KeyS', 'KeyD', 'KeyJ', 'KeyK', 'KeyL', 'Semicolon'];
const SIMPLE_KEY_LAYOUT = {
  KeyA:      { label: 'a', natural: 0, naturalName: 'C' },
  KeyS:      { label: 's', natural: 2, naturalName: 'D' },
  KeyD:      { label: 'd', natural: 4, naturalName: 'E' },
  KeyJ:      { label: 'j', natural: 5, naturalName: 'F' },
  KeyK:      { label: 'k', natural: 7, naturalName: 'G' },
  KeyL:      { label: 'l', natural: 9, naturalName: 'A' },
  Semicolon: { label: ';', natural: 11, naturalName: 'B' },
};
const SHARPABLE_CODES = new Set(['KeyA', 'KeyS', 'KeyJ', 'KeyK', 'KeyL']);
const NOTE_NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
function pitchName(midi) { return NOTE_NAMES[midi % 12] + (Math.floor(midi/12)-1); }

const INSTRUMENTS = ['piano','violin','viola','cello','strings','flute','clarinet','oboe'];
const INSTRUMENT_EMOJI = {
  piano:'🎹', violin:'🎻', viola:'🎻', cello:'🎻', strings:'🎻',
  flute:'🪈', clarinet:'🎷', oboe:'🎷',
};

// ── Playback engines ────────────────────────────────────────────────────────
let _audioCtx = null;
function audioCtx() {
  if (!_audioCtx) _audioCtx = new AudioContext({ latencyHint: 'interactive' });
  return _audioCtx;
}

const SAMPLE_ALIAS = {
  viola: 'violin',
  strings: 'violin',
  oboe: 'clarinet',
};

const SAMPLE_LIBRARY = {
  piano: {
    baseUrl: 'https://tonejs.github.io/audio/salamander/',
    release: 0.45,
    noteDuration: 0.5,
    urls: {
      A0: 'A0.mp3',
      C1: 'C1.mp3',
      'D#1': 'Ds1.mp3',
      'F#1': 'Fs1.mp3',
      A1: 'A1.mp3',
      C2: 'C2.mp3',
      'D#2': 'Ds2.mp3',
      'F#2': 'Fs2.mp3',
      A2: 'A2.mp3',
      C3: 'C3.mp3',
      'D#3': 'Ds3.mp3',
      'F#3': 'Fs3.mp3',
      A3: 'A3.mp3',
      C4: 'C4.mp3',
      'D#4': 'Ds4.mp3',
      'F#4': 'Fs4.mp3',
      A4: 'A4.mp3',
      C5: 'C5.mp3',
      'D#5': 'Ds5.mp3',
      'F#5': 'Fs5.mp3',
      A5: 'A5.mp3',
      C6: 'C6.mp3',
      'D#6': 'Ds6.mp3',
      'F#6': 'Fs6.mp3',
      A6: 'A6.mp3',
      C7: 'C7.mp3',
      'D#7': 'Ds7.mp3',
      'F#7': 'Fs7.mp3',
      A7: 'A7.mp3',
      C8: 'C8.mp3',
    },
  },
  violin: {
    baseUrl: 'https://cdn.jsdelivr.net/npm/tonejs-instrument-violin-mp3@1.1.1/',
    release: 0.35,
    noteDuration: 0.45,
    urls: {
      A3: 'A3.mp3',
      A4: 'A4.mp3',
      A5: 'A5.mp3',
      A6: 'A6.mp3',
      C4: 'C4.mp3',
      C5: 'C5.mp3',
      C6: 'C6.mp3',
      C7: 'C7.mp3',
      E4: 'E4.mp3',
      E5: 'E5.mp3',
      E6: 'E6.mp3',
      G3: 'G3.mp3',
      G4: 'G4.mp3',
      G5: 'G5.mp3',
      G6: 'G6.mp3',
    },
  },
  cello: {
    baseUrl: 'https://cdn.jsdelivr.net/npm/tonejs-instrument-cello-mp3@1.1.1/',
    release: 0.4,
    noteDuration: 0.5,
    urls: {
      A2: 'A2.mp3',
      A3: 'A3.mp3',
      A4: 'A4.mp3',
      'A#2': 'As2.mp3',
      'A#3': 'As3.mp3',
      'A#4': 'As4.mp3',
      B2: 'B2.mp3',
      B3: 'B3.mp3',
      B4: 'B4.mp3',
      C2: 'C2.mp3',
      C3: 'C3.mp3',
      C4: 'C4.mp3',
      C5: 'C5.mp3',
      'C#3': 'Cs3.mp3',
      'C#4': 'Cs4.mp3',
      D2: 'D2.mp3',
      D3: 'D3.mp3',
      D4: 'D4.mp3',
      'D#2': 'Ds2.mp3',
      'D#3': 'Ds3.mp3',
      'D#4': 'Ds4.mp3',
      E2: 'E2.mp3',
      E3: 'E3.mp3',
      E4: 'E4.mp3',
      F3: 'F3.mp3',
      F4: 'F4.mp3',
      'F#3': 'Fs3.mp3',
      'F#4': 'Fs4.mp3',
      G2: 'G2.mp3',
      G3: 'G3.mp3',
      G4: 'G4.mp3',
      'G#2': 'Gs2.mp3',
      'G#3': 'Gs3.mp3',
      'G#4': 'Gs4.mp3',
    },
  },
  flute: {
    baseUrl: 'https://cdn.jsdelivr.net/npm/tonejs-instrument-flute-mp3@1.1.2/',
    release: 0.25,
    noteDuration: 0.4,
    urls: {
      A4: 'A4.mp3',
      A5: 'A5.mp3',
      A6: 'A6.mp3',
      C4: 'C4.mp3',
      C5: 'C5.mp3',
      C6: 'C6.mp3',
      C7: 'C7.mp3',
      E4: 'E4.mp3',
      E5: 'E5.mp3',
      E6: 'E6.mp3',
    },
  },
  clarinet: {
    baseUrl: 'https://cdn.jsdelivr.net/npm/tonejs-instrument-clarinet-ogg@1.1.0/',
    release: 0.3,
    noteDuration: 0.42,
    urls: {
      'A#3': 'As3.ogg',
      'A#4': 'As4.ogg',
      'A#5': 'As5.ogg',
      D3: 'D3.ogg',
      D4: 'D4.ogg',
      D5: 'D5.ogg',
      D6: 'D6.ogg',
      F3: 'F3.ogg',
      F4: 'F4.ogg',
      F5: 'F5.ogg',
      'F#6': 'Fs6.ogg',
    },
  },
};

let _toneReady = false;
const _sampleSamplers = {};
const _sampleSamplerReady = {};

// instrument presets: { harmonics: [[mult, amp]], attack, decay, sustain, release, type }
const INSTRUMENT_PRESETS = {
  piano:    { harmonics:[[1,.7],[2,.2],[3,.1]], attack:.008, decay:3.5,  type:'sine'    },
  violin:   { harmonics:[[1,.5],[2,.25],[3,.15],[4,.07],[5,.03]], attack:.06, decay:.4, type:'sawtooth', vibrato:true },
  viola:    { harmonics:[[1,.55],[2,.25],[3,.13],[4,.05],[5,.02]], attack:.07, decay:.35, type:'sawtooth', vibrato:true },
  cello:    { harmonics:[[1,.6],[2,.22],[3,.12],[4,.04],[5,.02]], attack:.08, decay:.3,  type:'sawtooth', vibrato:true },
  strings:  { harmonics:[[1,.5],[2,.2],[3,.15],[4,.1],[5,.05]],  attack:.09, decay:.25, type:'sawtooth', vibrato:true },
  flute:    { harmonics:[[1,.85],[2,.12],[3,.03]], attack:.04, decay:.4,  type:'sine',  noise:.04  },
  clarinet: { harmonics:[[1,.7],[3,.25],[5,.08],[7,.03]], attack:.025, decay:.5, type:'sine' },
  oboe:     { harmonics:[[1,.5],[2,.3],[3,.15],[4,.05]], attack:.02,  decay:.6,  type:'sine' },
};

function midiToToneNote(midi) {
  return `${NOTE_NAMES[midi % 12]}${Math.floor(midi / 12) - 1}`;
}

function currentBps() {
  if (state.tracker) return state.tracker.bps();
  if (state.accompanist) return state.accompanist._bps;
  const bpm = parseFloat(document.getElementById('bpm-input')?.value) || 120;
  return bpm / 60;
}

function noteDurationSeconds(instrument, baseSeconds) {
  const sampledInstrument = SAMPLE_ALIAS[instrument] || instrument;
  const bps = Math.max(0.5, currentBps());
  const tempoScale = Math.max(0.75, Math.min(1.9, 2 / bps));
  const familyBoost = ['violin', 'viola', 'cello', 'strings'].includes(instrument) ? 1.15 : 1.0;
  const aliasBoost = ['violin', 'cello'].includes(sampledInstrument) ? 1.1 : 1.0;
  return Math.max(0.18, Math.min(1.25, baseSeconds * tempoScale * familyBoost * aliasBoost));
}

async function ensureSamplePlayback(instruments = []) {
  const requested = [...new Set(instruments
    .map(ins => SAMPLE_ALIAS[ins] || ins)
    .filter(ins => SAMPLE_LIBRARY[ins]))];
  if (!requested.length || typeof Tone === 'undefined') return false;

  if (!_toneReady) {
    await Tone.start();
    _toneReady = true;
  }

  const loaded = await Promise.all(requested.map(async (instrument) => {
    if (!_sampleSamplerReady[instrument]) {
      const config = SAMPLE_LIBRARY[instrument];
      _sampleSamplerReady[instrument] = new Promise((resolve, reject) => {
        _sampleSamplers[instrument] = new Tone.Sampler({
          urls: config.urls,
          baseUrl: config.baseUrl,
          release: config.release,
          onload: resolve,
          onerror: reject,
        }).toDestination();
      }).catch((error) => {
        console.warn(`Tone sampler load failed for ${instrument}:`, error);
        _sampleSamplerReady[instrument] = null;
        _sampleSamplers[instrument] = null;
        return false;
      });
    }
    const ready = await _sampleSamplerReady[instrument];
    return ready !== false && !!_sampleSamplers[instrument];
  }));

  return loaded.some(Boolean);
}

function playSynthNote(midi, velocity = 0.6, instrument = 'piano') {
  const ctx    = audioCtx();
  const freq   = 440 * Math.pow(2, (midi - 69) / 12);
  const preset = INSTRUMENT_PRESETS[instrument] || INSTRUMENT_PRESETS.piano;
  const now    = ctx.currentTime;
  const baseDur = instrument === 'piano' ? 0.55 : 0.5;
  const dur    = noteDurationSeconds(instrument, baseDur);

  const masterGain = ctx.createGain();
  masterGain.connect(ctx.destination);
  masterGain.gain.setValueAtTime(0, now);
  masterGain.gain.linearRampToValueAtTime(velocity * 0.35, now + preset.attack);
  masterGain.gain.exponentialRampToValueAtTime(0.0001, now + dur);

  preset.harmonics.forEach(([mult, amp]) => {
    const osc = ctx.createOscillator();
    const g   = ctx.createGain();
    g.gain.value = amp;
    osc.type = preset.type || 'sine';
    osc.frequency.value = freq * mult;

    // Vibrato for strings
    if (preset.vibrato) {
      const lfo  = ctx.createOscillator();
      const lfoG = ctx.createGain();
      lfo.frequency.value = 5.5;
      lfoG.gain.setValueAtTime(0, now);
      lfoG.gain.linearRampToValueAtTime(freq * 0.003, now + 0.15);
      lfo.connect(lfoG);
      lfoG.connect(osc.frequency);
      lfo.start(now); lfo.stop(now + dur);
    }
    osc.connect(g); g.connect(masterGain);
    osc.start(now); osc.stop(now + dur);
  });

  // Breath noise for flute
  if (preset.noise) {
    const buf    = ctx.createBuffer(1, ctx.sampleRate * dur, ctx.sampleRate);
    const data   = buf.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * preset.noise;
    const src  = ctx.createBufferSource();
    const noiseG = ctx.createGain();
    noiseG.gain.value = 0.3;
    src.buffer = buf;
    src.connect(noiseG); noiseG.connect(masterGain);
    src.start(now); src.stop(now + dur);
  }
}

function playNote(midi, velocity = 0.6, instrument = 'piano') {
  const sampledInstrument = SAMPLE_ALIAS[instrument] || instrument;
  const sampler = _sampleSamplers[sampledInstrument];
  if (sampler) {
    const baseDuration = SAMPLE_LIBRARY[sampledInstrument]?.noteDuration ?? 0.45;
    const duration = noteDurationSeconds(instrument, baseDuration);
    sampler.triggerAttackRelease(midiToToneNote(midi), duration, undefined, Math.min(1, velocity));
    return;
  }
  playSynthNote(midi, velocity, instrument);
}

function playChord(pitches, velocity = 0.5, instrument = 'piano') {
  pitches.forEach(p => playNote(p, velocity / pitches.length + 0.3, instrument));
}

// ── Tracker ──────────────────────────────────────────────────────────────────
class Tracker {
  constructor(rightHand, initialBps) {
    this.score      = rightHand;       // [[pitch, beat], ...]
    this.position   = 0;
    this.timestamps = [];              // [{time, beat}, ...]
    this._defaultBps = initialBps;
  }

  onNote(pitch) {
    const expected = this.score[this.position];
    if (!expected) return null;
    return expected[0] === pitch ? this._advance(this.position) : null;
  }

  // Mic mode: accept only the current note, with a small pitch tolerance.
  onNoteFuzzy(midi) {
    const expected = this.score[this.position];
    if (!expected) return null;
    return Math.abs(expected[0] - midi) <= 1 ? this._advance(this.position) : null;
  }

  _advance(i) {
    this.position = i + 1;
    const beat = this.score[i][1];
    this.timestamps.push({ time: performance.now() / 1000, beat });
    if (this.timestamps.length > 5) this.timestamps.shift();
    return beat;
  }

  bps() {
    const ts = this.timestamps;
    if (ts.length < 2) return this._defaultBps;
    const rates = [];
    for (let i = 1; i < ts.length; i++) {
      const dt = ts[i].time - ts[i-1].time;
      const db = ts[i].beat - ts[i-1].beat;
      if (dt > 0 && db > 0) rates.push(db / dt);
    }
    return rates.length ? rates.reduce((a,b)=>a+b)/rates.length : this._defaultBps;
  }

  isFinished() { return this.position >= this.score.length; }
  progress()   { return this.position / this.score.length; }
}

// ── Accompanist ──────────────────────────────────────────────────────────────
class Accompanist {
  constructor(leftHand, rightHand, initialBps, leftInstruments = []) {
    // leftInstruments: array of instrument names parallel to the non-selected parts
    // Each event gets the instrument of the source part it came from.
    // Since getLeftHand() merges parts in order, we track that here.
    this.events    = [...leftHand].sort((a,b) => a[1]-b[1]); // [[pitches,beat],...]
    this._instruments = leftInstruments;
    this.rhBeats   = [...new Set(rightHand.map(n=>n[1]))].sort((a,b)=>a-b);
    this._bps      = initialBps;
    this._syncBeat = 0;
    this._syncTime = null;   // null = waiting for first RH note
    this._nextSync = this.rhBeats[0] ?? Infinity;
    this._lhIdx    = 0;
    this._running  = false;
    this._raf      = null;
  }

  start() {
    this._running = true;
    this._tick();
  }

  stop() {
    this._running = false;
    if (this._raf) cancelAnimationFrame(this._raf);
  }

  onRhNote(beat, bps) {
    this._bps      = bps;
    this._syncBeat = beat;
    this._syncTime = performance.now() / 1000;
    this._nextSync = this.rhBeats.find(b => b > beat + 0.01) ?? Infinity;
    // Skip LH events now in the past
    while (this._lhIdx < this.events.length && this.events[this._lhIdx][1] < beat - 0.05)
      this._lhIdx++;
  }

  _currentBeat() {
    if (this._syncTime === null) return 0;
    return this._syncBeat + (performance.now()/1000 - this._syncTime) * this._bps;
  }

  _tick() {
    if (!this._running) return;

    if (this._syncTime !== null && this._lhIdx < this.events.length) {
      const [pitches, beat] = this.events[this._lhIdx];

      // Pause before next RH sync point
      if (beat < this._nextSync - 0.01) {
        const current = this._currentBeat();
        if (current >= beat - 0.005) {
          const instr = this._instruments[0] || 'piano';
          playChord(pitches, 0.5, instr);
          this._lhIdx++;
        }
      }
    }

    this._raf = requestAnimationFrame(() => this._tick());
  }
}

// ── App State ────────────────────────────────────────────────────────────────
let state = {
  scores:           [],
  current:          null,
  tracker:          null,
  accompanist:      null,
  playing:          false,
  selectedPart:     0,
  partInstruments:  {},  // partIndex → instrument name override
};

let _sheetMeasureEls = [];
let _sheetHighlightRect = null;
let _sheetHighlightIndex = -1;

// ── API helpers ──────────────────────────────────────────────────────────────
async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// ── Screens ──────────────────────────────────────────────────────────────────
function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
}

// ── Score list screen ─────────────────────────────────────────────────────────
async function loadScoreList() {
  const { scores } = await api('/api/scores');
  state.scores = scores;
  const grid = document.getElementById('score-grid');
  grid.innerHTML = scores.map(name => `
    <div class="score-card" id="card-${name}">
      <div onclick="openScore('${name}')" style="flex:1;cursor:pointer">
        <h3>${formatName(name)}</h3>
        <small>${name}</small>
      </div>
      <button class="delete-btn" onclick="deleteScore(event, '${name}')" title="Remove">✕</button>
    </div>
  `).join('');
}

function formatName(name) {
  return name.replace(/_/g,' ').replace(/\b\w/g, c => c.toUpperCase());
}

// ── Play screen ───────────────────────────────────────────────────────────────
async function fetchScore(name) {
  const CACHE_KEY = `accompy_score_v2_${name}`;
  try {
    // Cheap mtime check first
    const { mtime } = await api(`/api/scores/${name}/meta`);
    const cached = localStorage.getItem(CACHE_KEY);
    if (cached) {
      const parsed = JSON.parse(cached);
      if (parsed._mtime === mtime && Array.isArray(parsed.measure_beats)) return parsed;
    }
    // Cache miss — fetch full data
    const data = await api(`/api/scores/${name}`);
    data._mtime = mtime;
    localStorage.setItem(CACHE_KEY, JSON.stringify(data));
    return data;
  } catch {
    // Fallback: fetch without caching
    return api(`/api/scores/${name}`);
  }
}

async function openScore(name) {
  const data = await fetchScore(name);
  state.current = data;
  state.selectedPart = 0;
  state.partInstruments = {};
  _stopMic();
  setInputMode('keyboard');

  document.getElementById('play-title').textContent = formatName(name);
  document.getElementById('progress-fill').style.width = '0%';
  document.getElementById('next-note-display').textContent = '—';
  document.getElementById('beat-val').textContent  = '—';
  document.getElementById('tempo-val').textContent = '—';

  // Sheet music
  const frame = document.getElementById('sheet-frame');
  const placeholder = document.getElementById('sheet-placeholder');
  if (data.has_sheet) {
    frame.onload = () => initializeSheetHighlighting();
    frame.src = `/api/scores/${name}/sheet?v=${encodeURIComponent(data._mtime ?? Date.now())}`;
    frame.style.display = 'block';
    placeholder.style.display = 'none';
  } else {
    frame.onload = null;
    frame.style.display = 'none';
    placeholder.style.display = 'block';
    clearSheetHighlight();
  }

  // Part picker
  const parts = data.parts || [];
  const picker = document.getElementById('part-picker');
  const btns   = document.getElementById('part-buttons');
  if (parts.length > 0) {
    btns.innerHTML = parts.map((p, i) => {
      const instr = p.instrument || 'piano';
      return `<div class="part-row" id="part-row-${i}">
        <button class="part-btn${i === 0 ? ' selected' : ''}"
                onclick="selectPart(${i})" id="part-btn-${i}">
          ${p.name}
        </button>
        <select class="instr-select" onchange="changeInstrument(${i}, this.value)" id="instr-${i}">
          ${INSTRUMENTS.map(ins =>
            `<option value="${ins}"${ins === instr ? ' selected' : ''}>${INSTRUMENT_EMOJI[ins] || '🎵'} ${ins}</option>`
          ).join('')}
        </select>
      </div>`;
    }).join('');
    picker.style.display = 'block';
  } else {
    picker.style.display = 'none';
  }

  buildKeyboard(getRightHand());
  updateNextKey(getRightHand(), 0);
  showScreen('play-screen');
  document.getElementById('start-btn').disabled = false;
  document.getElementById('stop-btn').disabled  = true;
}

function selectPart(idx) {
  state.selectedPart = idx;
  document.querySelectorAll('.part-btn').forEach((b, i) =>
    b.classList.toggle('selected', i === idx));
  buildKeyboard(getRightHand());
  updateNextKey(getRightHand(), 0);
}

function getInstrumentForPart(idx) {
  return state.partInstruments[idx]
    ?? state.current?.parts?.[idx]?.instrument
    ?? 'piano';
}

async function changeInstrument(partIdx, instrument) {
  state.partInstruments[partIdx] = instrument;
  try {
    await api(`/api/scores/${state.current.name}/instrument`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ part_index: partIdx, instrument }),
    });
    localStorage.removeItem(`accompy_score_${state.current.name}`);
  } catch { /* non-critical — change is applied in-memory either way */ }
}

function getRightHand() {
  const parts = state.current?.parts;
  if (parts && parts.length > 0) return parts[state.selectedPart ?? 0].notes;
  return state.current?.right_hand || [];
}

function getLeftHand() {
  const parts = state.current?.parts;
  if (!parts || parts.length === 0) return state.current?.left_hand || [];
  const idx = state.selectedPart ?? 0;
  // Merge all parts except the selected one
  const left = [];
  parts.forEach((p, i) => { if (i !== idx) left.push(...p.notes); });
  left.sort((a, b) => a[1] - b[1]);
  // Wrap pitches as arrays for the accompanist
  return left.map(n => [Array.isArray(n[0]) ? n[0] : [n[0]], n[1]]);
}

function initializeSheetHighlighting() {
  const frame = document.getElementById('sheet-frame');
  const doc = frame?.contentDocument;
  if (!doc) return;

  _sheetMeasureEls = [...doc.querySelectorAll('g.measure')];
  _sheetHighlightRect = null;
  _sheetHighlightIndex = -1;

  const svg = doc.querySelector('svg.definition-scale');
  if (!svg || !_sheetMeasureEls.length) return;

  let style = doc.getElementById('accompy-measure-highlight-style');
  if (!style) {
    style = doc.createElement('style');
    style.id = 'accompy-measure-highlight-style';
    style.textContent = `
      .accompy-measure-highlight {
        fill: rgba(220, 40, 40, 0.12);
        stroke: rgba(220, 40, 40, 0.95);
        stroke-width: 24px;
        rx: 20px;
        ry: 20px;
        pointer-events: none;
      }
    `;
    doc.head?.appendChild(style);
  }

  updateSheetHighlight(0);
}

function clearSheetHighlight() {
  _sheetMeasureEls = [];
  _sheetHighlightRect?.remove();
  _sheetHighlightRect = null;
  _sheetHighlightIndex = -1;
}

function measureIndexForBeat(beat) {
  const starts = state.current?.measure_beats || [];
  if (!starts.length) return -1;

  let idx = 0;
  for (let i = 0; i < starts.length; i++) {
    if (starts[i] <= beat + 0.001) idx = i;
    else break;
  }
  return Math.min(idx, _sheetMeasureEls.length - 1);
}

function updateSheetHighlight(beat) {
  if (!_sheetMeasureEls.length) return;
  const idx = measureIndexForBeat(beat);
  if (idx < 0 || idx === _sheetHighlightIndex) return;

  const measureEl = _sheetMeasureEls[idx];
  if (!measureEl) return;
  const doc = measureEl.ownerDocument;

  _sheetHighlightRect?.remove();
  const bbox = measureEl.getBBox();
  const rect = doc.createElementNS('http://www.w3.org/2000/svg', 'rect');
  rect.setAttribute('class', 'accompy-measure-highlight');
  rect.setAttribute('x', String(bbox.x - 36));
  rect.setAttribute('y', String(bbox.y - 28));
  rect.setAttribute('width', String(bbox.width + 72));
  rect.setAttribute('height', String(bbox.height + 56));
  measureEl.insertBefore(rect, measureEl.firstChild);

  _sheetHighlightRect = rect;
  _sheetHighlightIndex = idx;
  measureEl.scrollIntoView({ block: 'nearest', inline: 'nearest' });
}

// ── Keyboard visualiser ───────────────────────────────────────────────────────
function expectedKeyboardPitch() {
  const rightHand = getRightHand();
  const position = state.tracker?.position ?? 0;
  return rightHand[position]?.[0] ?? rightHand[0]?.[0] ?? 60;
}

function resolveTypedMidi(code, shifted = false) {
  const layout = SIMPLE_KEY_LAYOUT[code];
  if (!layout) return undefined;
  const pitchClass = (layout.natural + (shifted && SHARPABLE_CODES.has(code) ? 1 : 0)) % 12;
  const target = expectedKeyboardPitch();

  let midi = pitchClass;
  while (midi < target - 6) midi += 12;
  while (midi > target + 6) midi -= 12;
  while (midi < 24) midi += 12;
  while (midi > 108) midi -= 12;
  return midi;
}

function cueKeyIdForMidi(midi) {
  const pitchClass = midi % 12;
  for (const code of SIMPLE_KEY_ORDER) {
    const layout = SIMPLE_KEY_LAYOUT[code];
    if (layout.natural === pitchClass) return `kbkey-${code}`;
    if (SHARPABLE_CODES.has(code) && (layout.natural + 1) % 12 === pitchClass) return `kbsharp-${code}`;
  }
  return null;
}

function buildKeyboard(rightHand) {
  const nextPitch = rightHand[0]?.[0];

  const row = document.getElementById('kb-row-main');
  row.innerHTML = SIMPLE_KEY_ORDER.map(code => {
    const layout = SIMPLE_KEY_LAYOUT[code];
    const sharpPitchClass = (layout.natural + 1) % 12;
    const naturalIsNext = nextPitch % 12 === layout.natural;
    const sharpIsNext = SHARPABLE_CODES.has(code) && nextPitch % 12 === sharpPitchClass;

    const sharpBadge = SHARPABLE_CODES.has(code)
      ? `<div class="kb-sharp${sharpIsNext ? ' next' : ''}" id="kbsharp-${code}">
           <span class="sharp-char">⇧${layout.label}</span>
           <span class="sharp-note">${NOTE_NAMES[sharpPitchClass]}</span>
         </div>`
      : `<div class="kb-sharp-empty"></div>`;

    return `<div class="kb-key-wrap">
      ${sharpBadge}
      <div class="kb-key${naturalIsNext ? ' next' : ''}" id="kbkey-${code}">
        <span class="key-char">${layout.label}</span>
        <span class="note-name">${layout.naturalName}</span>
      </div>
    </div>`;
  }).join('');
}

function highlightKey(key, on) {
  const el = document.getElementById(key);
  if (el) el.classList.toggle('active', on);
}

function updateNextKey(rightHand, position) {
  document.querySelectorAll('.kb-key.next, .kb-sharp.next')
    .forEach(el => el.classList.remove('next'));
  if (position >= rightHand.length) return;

  const midi = rightHand[position][0];
  const keyId = cueKeyIdForMidi(midi);
  if (keyId) document.getElementById(keyId)?.classList.add('next');
  document.getElementById('next-note-display').textContent = pitchName(midi);
}

// ── Start / Stop ──────────────────────────────────────────────────────────────
async function startPlaying() {
  audioCtx().resume(); // unblock audio on user gesture

  const bpm        = parseFloat(document.getElementById('bpm-input').value) || 100;
  const initialBps = bpm / 60;
  const right = getRightHand();
  const left  = getLeftHand();

  // Build per-part instrument map for the accompanist (all non-selected parts)
  const parts = state.current?.parts || [];
  const sel   = state.selectedPart ?? 0;
  const leftInstruments = parts
    .map((_, i) => i)
    .filter(i => i !== sel)
    .map(i => getInstrumentForPart(i));
  const instrumentsInUse = [getInstrumentForPart(sel), ...leftInstruments];

  const startBtn = document.getElementById('start-btn');
  startBtn.disabled = true;
  const originalLabel = startBtn.textContent;
  startBtn.textContent = 'Loading...';

  try {
    await ensureSamplePlayback(instrumentsInUse);
  } finally {
    startBtn.textContent = originalLabel;
  }

  state.tracker     = new Tracker(right, initialBps);
  state.accompanist = new Accompanist(left, right, initialBps, leftInstruments);
  state.accompanist.start();
  state.playing = true;

  document.getElementById('start-btn').disabled = true;
  document.getElementById('stop-btn').disabled  = false;

  updateNextKey(right, 0);
  updateSheetHighlight(0);
  enableMidi();
  if (_inputMode === 'mic') _startMic();
}

function stopPlaying() {
  if (state.accompanist) state.accompanist.stop();
  _stopMic();
  state.playing = false;
  document.getElementById('start-btn').disabled = false;
  document.getElementById('stop-btn').disabled  = true;
  document.getElementById('next-note-display').textContent = '—';
}

// ── Note handler (called by keyboard and MIDI) ────────────────────────────────
function handleNoteMic(midi) {
  if (!state.playing || !state.tracker) return;
  const beat = state.tracker.onNoteFuzzy(midi);
  if (beat !== null) {
    const bps = state.tracker.bps();
    state.accompanist.onRhNote(beat, bps);
    updateSheetHighlight(beat);
    document.getElementById('beat-val').textContent  = beat.toFixed(1);
    document.getElementById('tempo-val').textContent = Math.round(bps * 60) + ' BPM';
    document.getElementById('progress-fill').style.width =
      (state.tracker.progress() * 100).toFixed(1) + '%';
    updateNextKey(getRightHand(), state.tracker.position);
  }
  if (state.tracker.isFinished()) stopPlaying();
}

function handleNote(midi) {
  if (!state.playing || !state.tracker) return;
  playNote(midi, 0.6, getInstrumentForPart(state.selectedPart ?? 0));
  const keyId = cueKeyIdForMidi(midi);
  highlightKey(keyId, true);
  setTimeout(() => highlightKey(keyId, false), 120);

  const beat = state.tracker.onNote(midi);
  if (beat !== null) {
    const bps = state.tracker.bps();
    state.accompanist.onRhNote(beat, bps);
    updateSheetHighlight(beat);
    document.getElementById('beat-val').textContent  = beat.toFixed(1);
    document.getElementById('tempo-val').textContent = Math.round(bps * 60) + ' BPM';
    document.getElementById('progress-fill').style.width =
      (state.tracker.progress() * 100).toFixed(1) + '%';
    updateNextKey(getRightHand(), state.tracker.position);
  }

  if (state.tracker.isFinished()) stopPlaying();
}

// ── Input mode ───────────────────────────────────────────────────────────────
let _inputMode        = 'keyboard';
let _pitchDetector    = null;
let _selectedMicId    = null;
let _selectedSpeakerId = null;

function setInputMode(mode) {
  _inputMode = mode;
  document.getElementById('tab-keyboard').classList.toggle('active', mode === 'keyboard');
  document.getElementById('tab-mic').classList.toggle('active', mode === 'mic');
  document.getElementById('mic-controls').style.display    = mode === 'mic' ? 'block' : 'none';
  document.getElementById('keyboard-section').style.display = mode === 'keyboard' ? 'block' : 'none';

  if (mode === 'mic') {
    _startMic();
  } else {
    _stopMic();
  }
}

function onNoiseGateChange(val) {
  document.getElementById('noise-gate-val').textContent = val;
  if (_pitchDetector) _pitchDetector.setThreshold(val / 1000);
  _drawMeter(_lastRms);  // redraw so threshold line updates immediately
}

// ── Level meter ───────────────────────────────────────────────────────────────
let _lastRms = 0;
let _peakRms = 0;
let _peakHold = 0;

function _drawMeter(rms) {
  _lastRms = rms;
  const fill  = document.getElementById('level-fill');
  const peak  = document.getElementById('level-peak');
  const gate  = document.getElementById('level-gate');
  const label = document.getElementById('level-gate-label');
  if (!fill) return;

  const gateVal   = parseFloat(document.getElementById('noise-gate')?.value || 8) / 1000;
  const scale     = v => Math.min(v / 0.15, 1.0) * 100;  // % of bar width
  const fillPct   = scale(rms);
  const gatePct   = scale(gateVal);
  const aboveGate = rms >= gateVal;

  // Peak hold
  if (rms > _peakRms) { _peakRms = rms; _peakHold = 50; }
  else if (_peakHold > 0) _peakHold--;
  else _peakRms = Math.max(_peakRms * 0.95, 0);
  const peakPct = scale(_peakRms);

  fill.style.width = fillPct + '%';
  fill.classList.toggle('active', aboveGate);

  peak.style.left  = Math.min(peakPct, 99) + '%';
  gate.style.left  = gatePct + '%';

  const labelLeft = gatePct > 85 ? gatePct - 6 : gatePct + 0.5;
  label.style.left = labelLeft + '%';
}

function _micDot(state) {
  const dot  = document.getElementById('mic-dot');
  const text = document.getElementById('mic-status-text');
  dot.className = 'mic-status-dot' + (state ? ' ' + state : '');
  text.textContent = state === 'active'  ? 'Listening…'
                   : state === 'hearing' ? 'Note detected'
                   : 'Mic off';
}

async function _populateMicList() {
  try {
    // Need a temporary permission grant to get device labels
    const tmp = await navigator.mediaDevices.getUserMedia({ audio: true });
    tmp.getTracks().forEach(t => t.stop());
  } catch { return; }

  const devices   = await navigator.mediaDevices.enumerateDevices();
  const mics      = devices.filter(d => d.kind === 'audioinput');
  const speakers  = devices.filter(d => d.kind === 'audiooutput');

  const micSel = document.getElementById('mic-select');
  micSel.innerHTML = mics.map(d =>
    `<option value="${d.deviceId}"${d.deviceId === _selectedMicId ? ' selected' : ''}>${d.label || 'Microphone ' + d.deviceId.slice(0,6)}</option>`
  ).join('');
  if (!_selectedMicId && mics.length) _selectedMicId = mics[0].deviceId;

  const spkSel = document.getElementById('speaker-select');
  spkSel.innerHTML = '<option value="">— default —</option>' + speakers.map(d =>
    `<option value="${d.deviceId}"${d.deviceId === _selectedSpeakerId ? ' selected' : ''}>${d.label || 'Speaker ' + d.deviceId.slice(0,6)}</option>`
  ).join('');
}

async function onMicChange() {
  const sel = document.getElementById('mic-select');
  _selectedMicId = sel.value;
  if (_pitchDetector) {
    _stopMic();
    await _startMic();
  }
}

async function onSpeakerChange() {
  const sel = document.getElementById('speaker-select');
  _selectedSpeakerId = sel.value;
  const ctx = audioCtx();
  if (ctx.setSinkId) {
    try { await ctx.setSinkId(_selectedSpeakerId || ''); } catch (e) { console.warn('setSinkId failed:', e); }
  }
}

async function _startMic() {
  if (_pitchDetector) return;
  await _populateMicList();
  const gate = parseFloat(document.getElementById('noise-gate').value) / 1000;
  _pitchDetector = new PitchDetector(audioCtx(), {
    threshold: gate,
    deviceId: _selectedMicId || undefined,
    onNote: (midi, info) => {
      _micDot('hearing');
      const freqText = info?.freq ? ` ${info.freq.toFixed(1)} Hz` : '';
      document.getElementById('mic-note-display').textContent = `${pitchName(midi)}${freqText}`;
      handleNoteMic(midi);
      setTimeout(() => { if (_pitchDetector) _micDot('active'); }, 300);
    },
    onSilence: () => {
      document.getElementById('mic-note-display').textContent = '';
      _micDot('active');
    },
    onLevel: (rms) => _drawMeter(rms),
    onDebug: (msg) => { document.getElementById('mic-debug').textContent = msg; },
  });

  // Keep meter decaying to zero when silent
  (function decayLoop() {
    if (!_pitchDetector) { _drawMeter(0); return; }
    requestAnimationFrame(decayLoop);
  })();
  try {
    await _pitchDetector.start();
    _micDot('active');
  } catch (e) {
    alert(e.message);
    setInputMode('keyboard');
  }
}

function _stopMic() {
  if (_pitchDetector) { _pitchDetector.stop(); _pitchDetector = null; }
  _micDot(null);
  document.getElementById('mic-note-display').textContent = '';
  document.getElementById('mic-debug').textContent = '';
}

// ── Computer keyboard input ───────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.repeat) return;
  if (['INPUT','TEXTAREA'].includes(e.target.tagName)) return;
  const midi = resolveTypedMidi(e.code, e.shiftKey);
  if (midi !== undefined) { e.preventDefault(); handleNote(midi); }
});

// ── Web MIDI input ────────────────────────────────────────────────────────────
function enableMidi() {
  if (!navigator.requestMIDIAccess) return;
  navigator.requestMIDIAccess().then(access => {
    for (const input of access.inputs.values()) {
      input.onmidimessage = ({ data }) => {
        const [status, pitch, velocity] = data;
        if ((status & 0xF0) === 0x90 && velocity > 0) handleNote(pitch);
      };
    }
    document.getElementById('midi-status').textContent = 'MIDI: connected';
  }).catch(() => {});
}

// ── Delete piece ─────────────────────────────────────────────────────────────
async function deleteScore(e, name) {
  e.stopPropagation();
  if (!confirm(`Remove "${formatName(name)}"?`)) return;
  await api(`/api/scores/${name}`, { method: 'DELETE' });
  localStorage.removeItem(`accompy_score_${name}`);
  document.getElementById(`card-${name}`)?.remove();
  state.scores = state.scores.filter(s => s !== name);
}

// ── Add piece modal ───────────────────────────────────────────────────────────
let _searchTimer = null;

function openAddModal() {
  document.getElementById('add-modal').style.display = 'flex';
  document.getElementById('corpus-search').value = '';
  document.getElementById('search-results').innerHTML =
    '<p class="search-hint">Type to search the built-in music library (535 pieces).</p>';
  setTimeout(() => document.getElementById('corpus-search').focus(), 50);
}

function closeAddModal(e) {
  if (e && e.target !== document.getElementById('add-modal')) return;
  document.getElementById('add-modal').style.display = 'none';
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') document.getElementById('add-modal').style.display = 'none';
});

function onSearchInput() {
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(runSearch, 300);
}

async function runSearch() {
  const q = document.getElementById('corpus-search').value.trim();
  const spinner = document.getElementById('search-spinner');
  spinner.style.display = 'inline';

  try {
    const { results } = await api(`/api/corpus/search?q=${encodeURIComponent(q)}`);
    renderSearchResults(results);
  } catch (e) {
    document.getElementById('search-results').innerHTML =
      `<p class="search-hint" style="color:#e05c5c">Error: ${e.message}</p>`;
  } finally {
    spinner.style.display = 'none';
  }
}

function renderSearchResults(results) {
  const already = new Set(state.scores);
  if (!results.length) {
    document.getElementById('search-results').innerHTML =
      '<p class="search-hint">No results found.</p>';
    return;
  }
  document.getElementById('search-results').innerHTML = results.map(r => {
    const safeName = r.path.replace(/[^a-zA-Z0-9]/g, '_').toLowerCase();
    const added    = already.has(safeName);
    return `
      <div class="result-item${added ? ' done' : ''}" id="result-${safeName}">
        <div class="result-info">
          <div class="result-name">${r.composer} — ${r.title}</div>
          <div class="result-path">${r.path}</div>
        </div>
        <button class="btn btn-primary" onclick="addPiece('${r.path}', '${safeName}')"
          ${added ? 'disabled' : ''}>
          ${added ? '✓ Added' : '+ Add'}
        </button>
      </div>`;
  }).join('');
}

async function addPiece(corpusPath, safeName) {
  const item = document.getElementById(`result-${safeName}`);
  item.classList.add('adding');
  item.querySelector('button').textContent = 'Converting…';

  try {
    await api('/api/convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ corpus_path: corpusPath, name: safeName }),
    });
    item.classList.remove('adding');
    item.classList.add('done');
    item.querySelector('button').textContent = '✓ Added';
    item.querySelector('button').disabled = true;

    // Refresh score list in background
    await loadScoreList();
  } catch (e) {
    item.classList.remove('adding');
    item.querySelector('button').textContent = '+ Add';
    alert(`Failed to convert: ${e.message}`);
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────
loadScoreList();
