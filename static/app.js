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
const FULL_KEYBOARD_START = 21;
const FULL_KEYBOARD_END = 108;
const VISUAL_SLOTS = [
  { id: 'KeyA-natural', code: 'KeyA', sharp: false, noteName: 'C', keyLabel: 'a', kind: 'white', pitchClass: 0 },
  { id: 'KeyA-sharp',   code: 'KeyA', sharp: true,  noteName: 'C#', keyLabel: '⇧a', kind: 'black', pitchClass: 1 },
  { id: 'KeyS-natural', code: 'KeyS', sharp: false, noteName: 'D', keyLabel: 's', kind: 'white', pitchClass: 2 },
  { id: 'KeyS-sharp',   code: 'KeyS', sharp: true,  noteName: 'D#', keyLabel: '⇧s', kind: 'black', pitchClass: 3 },
  { id: 'KeyD-natural', code: 'KeyD', sharp: false, noteName: 'E', keyLabel: 'd', kind: 'white', pitchClass: 4 },
  { id: 'KeyJ-natural', code: 'KeyJ', sharp: false, noteName: 'F', keyLabel: 'j', kind: 'white', pitchClass: 5 },
  { id: 'KeyJ-sharp',   code: 'KeyJ', sharp: true,  noteName: 'F#', keyLabel: '⇧j', kind: 'black', pitchClass: 6 },
  { id: 'KeyK-natural', code: 'KeyK', sharp: false, noteName: 'G', keyLabel: 'k', kind: 'white', pitchClass: 7 },
  { id: 'KeyK-sharp',   code: 'KeyK', sharp: true,  noteName: 'G#', keyLabel: '⇧k', kind: 'black', pitchClass: 8 },
  { id: 'KeyL-natural', code: 'KeyL', sharp: false, noteName: 'A', keyLabel: 'l', kind: 'white', pitchClass: 9 },
  { id: 'KeyL-sharp',   code: 'KeyL', sharp: true,  noteName: 'A#', keyLabel: '⇧l', kind: 'black', pitchClass: 10 },
  { id: 'Semicolon-natural', code: 'Semicolon', sharp: false, noteName: 'B', keyLabel: ';', kind: 'white', pitchClass: 11 },
];
function pitchName(midi) { return NOTE_NAMES[midi % 12] + (Math.floor(midi/12)-1); }
function isBlackKeyMidi(midi) { return [1, 3, 6, 8, 10].includes(midi % 12); }

const INSTRUMENTS = ['piano','violin','viola','cello','strings','flute','clarinet','oboe','voice'];
const INSTRUMENT_EMOJI = {
  piano:'🎹', violin:'🎻', viola:'🎻', cello:'🎻', strings:'🎻',
  flute:'🪈', clarinet:'🎷', oboe:'🎷', voice:'🎤',
};
const TEMPO_PAUSE_IGNORE_SEC = 3;
let _accompanimentLatencyCompSec = 0.28;
const CHORD_MATCH_WINDOW_SEC = 0.5;

// ── Playback engines ────────────────────────────────────────────────────────
let _audioCtx = null;
let _midiConnected = false;
let _lastMidiNoteTime = 0;
let _lastMidiPitch = null;
let _pedalResonanceBus = null;
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
  voice:    { harmonics:[[1,.62],[2,.2],[3,.1],[4,.05],[5,.03]], attack:.05, decay:.55, type:'triangle', vibrato:true },
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

function eventDuration(event, fallbackBeats = 0.75) {
  const raw = Number(event?.[2]);
  return Number.isFinite(raw) && raw > 0 ? raw : fallbackBeats;
}

function eventPedalRelease(event) {
  const raw = Number(event?.[3]);
  return Number.isFinite(raw) && raw > 0 ? raw : null;
}

function isPedaledEvent(event) {
  return eventPedalRelease(event) !== null;
}

function eventPedalHoldSeconds(event, bps = currentBps()) {
  const releaseBeat = eventPedalRelease(event);
  const beat = Number(event?.[1]);
  if (releaseBeat === null || !Number.isFinite(beat)) return null;
  return Math.max(0.12, (releaseBeat - beat) / Math.max(0.5, bps));
}

function eventDurationSeconds(event, instrument = 'piano', fallbackBeats = 0.75) {
  const beats = eventDuration(event, fallbackBeats);
  const seconds = beats / Math.max(0.5, currentBps());
  const familyBoost = ['violin', 'viola', 'cello', 'strings'].includes(instrument) ? 1.08 : 1.0;
  const pianoBoost = instrument === 'piano' ? 1.22 : 1.0;
  return Math.max(0.14, Math.min(10, seconds * familyBoost * pianoBoost));
}

function ensurePedalResonanceBus() {
  if (_pedalResonanceBus) return _pedalResonanceBus;
  const ctx = audioCtx();
  const convolver = ctx.createConvolver();
  const impulseSeconds = 2.4;
  const length = Math.floor(ctx.sampleRate * impulseSeconds);
  const impulse = ctx.createBuffer(2, length, ctx.sampleRate);
  for (let channel = 0; channel < impulse.numberOfChannels; channel++) {
    const data = impulse.getChannelData(channel);
    for (let i = 0; i < length; i++) {
      const t = i / length;
      const decay = Math.pow(1 - t, 2.2);
      data[i] = (Math.random() * 2 - 1) * decay * 0.22;
    }
  }
  convolver.buffer = impulse;

  const pre = ctx.createGain();
  pre.gain.value = 0.55;
  const lowpass = ctx.createBiquadFilter();
  lowpass.type = 'lowpass';
  lowpass.frequency.value = 2800;
  const highpass = ctx.createBiquadFilter();
  highpass.type = 'highpass';
  highpass.frequency.value = 110;
  const wet = ctx.createGain();
  wet.gain.value = 0.05;

  pre.connect(convolver);
  convolver.connect(lowpass);
  lowpass.connect(highpass);
  highpass.connect(wet);
  wet.connect(ctx.destination);

  _pedalResonanceBus = { pre, wet };
  return _pedalResonanceBus;
}

function playPedalResonance(pitches, velocity = 0.5, opts = {}) {
  if (!pitches?.length) return;
  const ctx = audioCtx();
  const now = ctx.currentTime;
  const { pre, wet } = ensurePedalResonanceBus();
  const duration = Math.max(0.7, Math.min(12, (opts.duration ?? 1.5) * 1.9 + 0.45));
  const pedalHold = Math.max(duration, opts.pedalHold ?? duration);
  const resonanceGain = Math.min(0.16, 0.08 + velocity * 0.06) / Math.sqrt(pitches.length);
  const harmonicShape = [
    [1, 1.0],
    [2, 0.65],
    [3, 0.38],
    [4, 0.22],
    [5, 0.12],
  ];

  wet.gain.cancelScheduledValues(now);
  wet.gain.setValueAtTime(Math.max(0.05, wet.gain.value), now);
  wet.gain.linearRampToValueAtTime(Math.max(0.18, 0.12 + velocity * 0.12), now + 0.08);
  wet.gain.setValueAtTime(Math.max(0.18, 0.12 + velocity * 0.12), now + pedalHold);
  wet.gain.exponentialRampToValueAtTime(0.05, now + pedalHold + 0.45);

  pitches.forEach((midi) => {
    const fundamental = 440 * Math.pow(2, (midi - 69) / 12);
    harmonicShape.forEach(([mult, amp], idx) => {
      const osc = ctx.createOscillator();
      const body = ctx.createBiquadFilter();
      body.type = 'bandpass';
      body.frequency.value = Math.min(5200, fundamental * mult);
      body.Q.value = idx === 0 ? 8 : 10 + idx * 2;
      const gain = ctx.createGain();
      const start = now + idx * 0.004;
      const peak = resonanceGain * amp;

      osc.type = idx === 0 ? 'triangle' : 'sine';
      osc.frequency.value = fundamental * mult;

      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(Math.max(0.0002, peak), start + 0.05);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);

      osc.connect(body);
      body.connect(gain);
      gain.connect(pre);
      osc.start(start);
      osc.stop(start + duration + 0.03);
    });
  });
}

async function ensureSamplePlayback(instruments = []) {
  const requested = [...new Set(instruments
    .map(ins => SAMPLE_ALIAS[ins] || ins)
    .filter(ins => SAMPLE_LIBRARY[ins]))];
  if (!requested.length || typeof Tone === 'undefined') return false;

  const toneContext = Tone.getContext?.();
  if (toneContext) {
    if ('lookAhead' in toneContext) toneContext.lookAhead = 0.01;
    if ('updateInterval' in toneContext) toneContext.updateInterval = 0.01;
  }

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

function isSampleBackedInstrument(instrument) {
  const sampledInstrument = SAMPLE_ALIAS[instrument] || instrument;
  return !!SAMPLE_LIBRARY[sampledInstrument];
}

function hasLoadedSampler(instrument) {
  const sampledInstrument = SAMPLE_ALIAS[instrument] || instrument;
  return !!_sampleSamplers[sampledInstrument];
}

function currentScoreInstruments() {
  const parts = state.current?.parts || [];
  if (!parts.length) return [getInstrumentForPart(state.selectedPart ?? 0)];
  return parts.map((_, idx) => getInstrumentForPart(idx));
}

async function preloadCurrentScoreInstruments() {
  if (!state.current) return false;
  try {
    return await ensureSamplePlayback(currentScoreInstruments());
  } catch (error) {
    console.warn('Sample preload failed:', error);
    return false;
  }
}

function playSynthNote(midi, velocity = 0.6, instrument = 'piano', opts = {}) {
  const ctx    = audioCtx();
  const freq   = 440 * Math.pow(2, (midi - 69) / 12);
  const preset = INSTRUMENT_PRESETS[instrument] || INSTRUMENT_PRESETS.piano;
  const now    = ctx.currentTime;
  const baseDur = instrument === 'piano' ? 0.55 : 0.5;
  const dur    = Math.max(0.12, opts.duration ?? noteDurationSeconds(instrument, baseDur));

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

function playNote(midi, velocity = 0.6, instrument = 'piano', opts = {}) {
  const sampledInstrument = SAMPLE_ALIAS[instrument] || instrument;
  const sampler = _sampleSamplers[sampledInstrument];
  if (sampler && !opts.preferSynth) {
    const baseDuration = SAMPLE_LIBRARY[sampledInstrument]?.noteDuration ?? 0.45;
    const duration = Math.max(0.12, opts.duration ?? noteDurationSeconds(instrument, baseDuration));
    sampler.triggerAttackRelease(midiToToneNote(midi), duration, undefined, Math.min(1, velocity));
    if (instrument === 'piano' && opts.pedaled) {
      playPedalResonance([midi], velocity, opts);
    }
    return;
  }
  if (isSampleBackedInstrument(instrument)) return;
  playSynthNote(midi, velocity, instrument, opts);
}

function playChord(pitches, velocity = 0.5, instrument = 'piano', opts = {}) {
  pitches.forEach(p => playNote(p, velocity / pitches.length + 0.3, instrument, opts));
  if (instrument === 'piano' && opts.pedaled) {
    playPedalResonance(pitches, velocity, opts);
  }
}

function eventPitches(event) {
  if (!event) return [];
  return Array.isArray(event[0]) ? event[0] : [event[0]];
}

function leadPitchFromEvent(event) {
  const pitches = eventPitches(event);
  return pitches.length ? pitches[pitches.length - 1] : 60;
}

function eventLabel(event) {
  const pitches = eventPitches(event);
  if (!pitches.length) return '—';
  return pitches.map((pitch) => pitchName(pitch)).join(' / ');
}

function syncExpectedMicNote() {
  if (!_pitchDetector || !state.playing) return;
  if (typeof _pitchDetector.setExpectedMidi !== 'function') return;
  const rightHand = getRightHand();
  const position = state.tracker?.position ?? 0;
  const expected = leadPitchFromEvent(rightHand[position] ?? rightHand[0]);
  _pitchDetector.setExpectedMidi(expected);
}

// ── Tracker ──────────────────────────────────────────────────────────────────
class Tracker {
  constructor(rightHand, initialBps) {
    this.score      = rightHand;       // [[pitch, beat], ...]
    this.position   = 0;
    this.timestamps = [];              // [{time, beat}, ...]
    this._defaultBps = initialBps;
    this._smoothedBps = initialBps;
    this._lastAdvanceTime = 0;
    this._pendingChord = new Set();
    this._pendingPosition = -1;
    this._pendingStartedAt = 0;
    this._recentNotes = [];
  }

  onNote(pitch) {
    const expected = this.score[this.position];
    if (!expected) return null;
    const now = performance.now() / 1000;
    this._recentNotes.push({ pitch, time: now });
    this._recentNotes = this._recentNotes.filter((entry) => now - entry.time <= CHORD_MATCH_WINDOW_SEC);

    const pitches = eventPitches(expected);
    if (pitches.length === 1) {
      return pitches[0] === pitch ? this._advance(this.position) : null;
    }

    if (!pitches.includes(pitch)) return null;
    if (this._pendingPosition !== this.position || now - this._pendingStartedAt > CHORD_MATCH_WINDOW_SEC) {
      this._pendingChord = new Set(
        this._recentNotes
          .filter((entry) => pitches.includes(entry.pitch))
          .map((entry) => entry.pitch)
      );
      this._pendingPosition = this.position;
      this._pendingStartedAt = now;
    }
    this._pendingChord.add(pitch);
    return pitches.every((expectedPitch) => this._pendingChord.has(expectedPitch))
      ? this._advance(this.position)
      : null;
  }

  // Mic mode: accept only the current note, with a small pitch tolerance.
  onNoteFuzzy(midi) {
    const expected = this.score[this.position];
    if (!expected) return null;
    return Math.abs(leadPitchFromEvent(expected) - midi) <= 1 ? this._advance(this.position) : null;
  }

  _advance(i) {
    const now = performance.now() / 1000;
    if (now - this._lastAdvanceTime < 0.06) return null;
    this._lastAdvanceTime = now;
    this._pendingChord.clear();
    this._pendingPosition = -1;
    this._pendingStartedAt = 0;
    this.position = i + 1;
    const beat = this.score[i][1];
    this.timestamps.push({ time: now, beat });
    if (this.timestamps.length > 5) this.timestamps.shift();
    return beat;
  }

  bps() {
    const ts = this.timestamps;
    if (ts.length < 2) return this._smoothedBps;
    const rates = [];
    for (let i = 1; i < ts.length; i++) {
      const dt = ts[i].time - ts[i-1].time;
      const db = ts[i].beat - ts[i-1].beat;
      if (dt >= 0.08 && dt <= TEMPO_PAUSE_IGNORE_SEC && db > 0) rates.push(db / dt);
    }
    if (!rates.length) return this._smoothedBps;

    rates.sort((a, b) => a - b);
    let candidate = rates[Math.floor(rates.length / 2)];

    const minBps = 35 / 60;
    const maxBps = 300 / 60;
    if (candidate > maxBps) return this._smoothedBps;
    candidate = Math.max(minBps, Math.min(maxBps, candidate));

    const maxRise = Math.min(maxBps, this._smoothedBps * 1.22 + 0.05);
    const maxDrop = Math.max(minBps, this._smoothedBps * 0.78 - 0.03);
    candidate = Math.max(maxDrop, Math.min(maxRise, candidate));

    this._smoothedBps = this._smoothedBps * 0.72 + candidate * 0.28;
    return this._smoothedBps;
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
    this.events    = [...leftHand].sort((a,b) => a[1]-b[1]); // [[pitches,beat,duration],...]
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
    const hasPrelude = this.events.some((event) => event[1] < this._nextSync - 0.01);
    if (hasPrelude) {
      this._syncBeat = 0;
      this._syncTime = performance.now() / 1000 - _accompanimentLatencyCompSec;
    }
    this._running = true;
    this._tick();
  }

  stop() {
    this._running = false;
    if (this._raf) cancelAnimationFrame(this._raf);
  }

  pause() {
    this._running = false;
    if (this._raf) cancelAnimationFrame(this._raf);
    this._raf = null;
  }

  resume(beat, bps) {
    this._bps = bps;
    this._syncBeat = beat;
    this._syncTime = performance.now() / 1000 - _accompanimentLatencyCompSec;
    this._nextSync = this.rhBeats.find((b) => b > beat + 0.01) ?? Infinity;
    this._running = true;
    this._tick();
  }

  onRhNote(beat, bps) {
    this._bps      = bps;
    this._syncBeat = beat;
    // Bias the accompaniment clock slightly ahead to compensate for browser
    // output latency that is still audible even with wired MIDI input.
    this._syncTime = performance.now() / 1000 - _accompanimentLatencyCompSec;
    this._nextSync = this.rhBeats.find(b => b > beat + 0.01) ?? Infinity;
    // Skip LH events now in the past
    while (this._lhIdx < this.events.length && this.events[this._lhIdx][1] < beat - 0.08)
      this._lhIdx++;
  }

  _currentBeat() {
    if (this._syncTime === null) return 0;
    return this._syncBeat + (performance.now()/1000 - this._syncTime) * this._bps;
  }

  _tick() {
    if (!this._running) return;

    if (this._syncTime !== null && this._lhIdx < this.events.length) {
      const [pitches, beat, durationBeats] = this.events[this._lhIdx];

      // Pause before next RH sync point
      if (beat < this._nextSync - 0.01) {
        const current = this._currentBeat();
        if (current >= beat - 0.005) {
          const instr = this._instruments[0] || 'piano';
          const duration = Math.max(0.12, (durationBeats ?? 0.75) / Math.max(0.5, this._bps));
          const pedalRelease = eventPedalRelease(this.events[this._lhIdx]);
          playChord(pitches, 0.5, instr, {
            duration,
            pedaled: pedalRelease !== null,
            pedalHold: pedalRelease !== null ? Math.max(duration, (pedalRelease - beat) / Math.max(0.5, this._bps)) : null,
          });
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
  serverScores:     [],
  current:          null,
  tracker:          null,
  accompanist:      null,
  playing:          false,
  selectedPart:     0,
  partInstruments:  {},  // partIndex → instrument name override
  scoreGridColumns: 3,
  keyboardLayoutMode: 'full',
  paused:           false,
  pausedBeat:       0,
  pausedBps:        1,
  sheetView: { zoom: 1.0, rotation: 0, autoFit: true },
  sheetSource: null, // { name, hasSheet, musicXml }
};

let _noteHighwayRaf = null;
let _noteHighwayStartTime = null;
let _noteHighwayStartBeat = 0;
let _noteHighwayBps = 1;

let _sheetMeasureEls = [];
let _sheetHighlightRect = null;
let _sheetHighlightIndex = -1;
const SCORE_LIBRARY_KEY = 'accompy_score_library_v1';
const SCORE_LIBRARY_INIT_KEY = 'accompy_score_library_initialized_v1';
const PLAY_SIDEBAR_COLLAPSED_KEY = 'accompy_play_sidebar_collapsed_v1';
let _appConfig = { supabase_enabled: false, auth_enabled: false };
let _authUser = null;
const OPENING_GUIDE_LEAD_BEATS = 0.75;

// ── API helpers ──────────────────────────────────────────────────────────────
async function api(path, opts) {
  const headers = { ...((opts && opts.headers) || {}) };
  const request = { cache: 'no-store', ...(opts || {}), headers };
  const r = await fetch(path, request);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// ── Screens ──────────────────────────────────────────────────────────────────
function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  if (id === 'play-screen' && typeof fitSheetToWidth === 'function') {
    requestAnimationFrame(() => fitSheetToWidth());
  }
}

function applyPlaySidebarCollapsed(collapsed) {
  const shell = document.querySelector('#play-screen .play-shell');
  const toggle = document.getElementById('play-sidebar-toggle');
  if (!shell || !toggle) return;
  const normalized = !!collapsed;
  shell.dataset.sidebar = normalized ? 'collapsed' : 'open';
  toggle.textContent = normalized ? '→' : '←';
  toggle.setAttribute('aria-label', normalized ? 'Expand piece sidebar' : 'Collapse piece sidebar');
  localStorage.setItem(PLAY_SIDEBAR_COLLAPSED_KEY, normalized ? '1' : '0');
}

function togglePlaySidebar() {
  const shell = document.querySelector('#play-screen .play-shell');
  if (!shell) return;
  applyPlaySidebarCollapsed(shell.dataset.sidebar !== 'collapsed');
}

window.togglePlaySidebar = togglePlaySidebar;

function setAuthStatus(message, tone = 'muted') {
  const el = document.getElementById('auth-status');
  if (!el) return;
  el.textContent = message || '';
  el.style.color = tone === 'error'
    ? '#e05c5c'
    : tone === 'success'
      ? 'var(--success)'
      : 'var(--muted)';
}

function updateAuthUI() {
  const panel = document.getElementById('auth-panel');
  const loggedOut = document.getElementById('auth-logged-out');
  const loggedIn = document.getElementById('auth-logged-in');
  const addPieceBtn = document.getElementById('add-piece-btn');
  if (!panel || !loggedOut || !loggedIn || !addPieceBtn) return;
  if (!_appConfig.auth_enabled) {
    panel.style.display = 'none';
    addPieceBtn.disabled = false;
    return;
  }

  panel.style.display = 'block';
  const isLoggedIn = !!_authUser;
  loggedOut.style.display = isLoggedIn ? 'none' : 'block';
  loggedIn.style.display = isLoggedIn ? 'block' : 'none';
  addPieceBtn.disabled = !isLoggedIn;
  if (isLoggedIn) {
    document.getElementById('auth-user-email').textContent = _authUser.email || _authUser.username || 'Signed in';
    setAuthStatus('');
  } else {
    document.getElementById('score-grid').innerHTML = '<div class="score-preview-empty">Sign in to load your score library.</div>';
  }
  renderPlayPieceList();
}

async function initAppConfig() {
  try {
    _appConfig = await api('/api/config');
    if (_appConfig.auth_enabled) {
      const session = await api('/api/session');
      _authUser = session.user || null;
    }
  } catch (error) {
    _appConfig = { supabase_enabled: false, auth_enabled: false };
    setAuthStatus(`Auth config failed to load: ${error.message || error}`);
  }
  updateAuthUI();
}

async function signIn() {
  const username = document.getElementById('auth-email').value.trim();
  const password = document.getElementById('auth-password').value;
  if (!_appConfig.auth_enabled) return;
  setAuthStatus('Signing in...');
  try {
    const result = await api('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    _authUser = result.user || null;
    updateAuthUI();
    await loadScoreList();
    setAuthStatus('Signed in.', 'success');
  } catch (error) {
    setAuthStatus(error.message || 'Sign in failed.', 'error');
    return;
  }
}

async function signUp() {
  if (!_appConfig.auth_enabled) return;
  const username = document.getElementById('auth-email').value.trim();
  const password = document.getElementById('auth-password').value;
  setAuthStatus('Creating account...');
  try {
    const result = await api('/api/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    _authUser = result.user || null;
    updateAuthUI();
    await loadScoreList();
    setAuthStatus('Account created.', 'success');
  } catch (error) {
    setAuthStatus(error.message || 'Sign up failed.', 'error');
    return;
  }
}

async function signOut() {
  await api('/api/logout', { method: 'POST' });
  _authUser = null;
  state.current = null;
  state.scores = [];
  state.serverScores = [];
  updateAuthUI();
  renderPlayPieceList();
}

window.signIn = signIn;
window.signUp = signUp;
window.signOut = signOut;

function loadPersonalScoreLibrary() {
  if (_appConfig.auth_enabled) return [...(state.serverScores || [])];
  try {
    const parsed = JSON.parse(localStorage.getItem(SCORE_LIBRARY_KEY) || '[]');
    return Array.isArray(parsed) ? parsed.filter((name) => typeof name === 'string' && name) : [];
  } catch {
    return [];
  }
}

function savePersonalScoreLibrary(names) {
  if (_appConfig.auth_enabled) {
    const deduped = [...new Set((names || []).filter(Boolean))].sort();
    state.scores = deduped;
    return deduped;
  }
  const deduped = [...new Set((names || []).filter(Boolean))].sort();
  localStorage.setItem(SCORE_LIBRARY_KEY, JSON.stringify(deduped));
  localStorage.setItem(SCORE_LIBRARY_INIT_KEY, '1');
  state.scores = deduped;
  return deduped;
}

function addScoreToLibrary(name) {
  return savePersonalScoreLibrary([...loadPersonalScoreLibrary(), name]);
}

function removeScoreFromLibrary(name) {
  localStorage.removeItem(`accompy_score_${name}`);
  localStorage.removeItem(`accompy_score_v2_${name}`);
  return savePersonalScoreLibrary(loadPersonalScoreLibrary().filter((item) => item !== name));
}

function normalizedScoreGridColumns(value) {
  const n = Number.parseInt(value, 10);
  if (!Number.isFinite(n)) return 3;
  return Math.max(2, Math.min(6, n));
}

function applyScoreGridColumns(value) {
  const columns = normalizedScoreGridColumns(value);
  state.scoreGridColumns = columns;
  document.getElementById('score-grid')?.style.setProperty('--score-grid-columns', String(columns));
  const select = document.getElementById('score-grid-columns');
  if (select && select.value !== String(columns)) select.value = String(columns);
  requestAnimationFrame(() => resizeScorePreviews());
}

function setScoreGridColumns(value) {
  const columns = normalizedScoreGridColumns(value);
  applyScoreGridColumns(columns);
  localStorage.setItem('accompy_score_grid_columns', String(columns));
}

function applyKeyboardLayoutMode(mode) {
  const normalized = mode === 'mini' ? 'mini' : 'full';
  state.keyboardLayoutMode = normalized;
  const section = document.getElementById('keyboard-section');
  const miniPanel = document.getElementById('mini-keyboard-panel');
  const mini = document.getElementById('mini-keyboard-layout');
  const full = document.getElementById('full-keyboard-panel');
  if (section) section.dataset.layoutMode = normalized;
  if (miniPanel) {
    miniPanel.classList.toggle('hidden', normalized !== 'mini');
    miniPanel.style.display = normalized === 'mini' ? '' : 'none';
    miniPanel.hidden = normalized !== 'mini';
  }
  if (mini) {
    mini.classList.toggle('hidden', normalized !== 'mini');
    mini.style.display = normalized === 'mini' ? '' : 'none';
    mini.hidden = normalized !== 'mini';
  }
  if (full) {
    full.classList.toggle('hidden', normalized !== 'full');
    full.style.display = normalized === 'full' ? '' : 'none';
    full.hidden = normalized !== 'full';
  }
  document.getElementById('keyboard-view-mini')?.classList.toggle('active', normalized === 'mini');
  document.getElementById('keyboard-view-full')?.classList.toggle('active', normalized === 'full');
}

function setKeyboardLayoutMode(mode) {
  applyKeyboardLayoutMode(mode);
  localStorage.setItem('accompy_keyboard_layout_mode', state.keyboardLayoutMode);
}

window.setKeyboardLayoutMode = setKeyboardLayoutMode;

function initKeyboardLayoutToggle() {
  document.getElementById('keyboard-view-full')?.addEventListener('click', () => setKeyboardLayoutMode('full'));
  document.getElementById('keyboard-view-mini')?.addEventListener('click', () => setKeyboardLayoutMode('mini'));
}

function setLatencyCompensation(value) {
  const ms = Math.max(0, Math.min(500, Number.parseInt(value, 10) || 0));
  _accompanimentLatencyCompSec = ms / 1000;
  const slider = document.getElementById('latency-slider');
  const label = document.getElementById('latency-value');
  if (slider && slider.value !== String(ms)) slider.value = String(ms);
  if (label) label.textContent = `${ms} ms`;
  localStorage.setItem('accompy_latency_comp_ms', String(ms));
}

function initLatencyControls() {
  const slider = document.getElementById('latency-slider');
  if (!slider || slider.dataset.bound === '1') return;
  const sync = () => setLatencyCompensation(slider.value);
  slider.addEventListener('input', sync);
  slider.addEventListener('change', sync);
  slider.dataset.bound = '1';
}

function applyTheme(theme) {
  const normalized = theme === 'light' ? 'light' : 'dark';
  document.body.classList.toggle('light', normalized === 'light');
  const toggle = document.getElementById('theme-toggle');
  if (toggle) toggle.textContent = normalized === 'light' ? 'Dark' : 'Light';
  localStorage.setItem('accompy_theme', normalized);
  document.querySelectorAll('#sheet-frame, .score-preview-frame').forEach((frame) => sanitizeSheetFrame(frame));
}

function toggleTheme() {
  applyTheme(document.body.classList.contains('light') ? 'dark' : 'light');
}

function resizeScorePreviews() {
  document.querySelectorAll('.score-preview-frame').forEach((frame) => {
    const preview = frame.parentElement;
    if (!preview) return;
    const width = preview.clientWidth;
    if (!width) return;
    preview.style.setProperty('--preview-scale', String(width / 960));
  });
}

function sanitizeSheetFrame(frame) {
  const doc = frame?.contentDocument;
  if (!doc) return;
  const darkMode = !document.body.classList.contains('light');

  doc.querySelectorAll('h1').forEach((el) => el.remove());

  let style = doc.getElementById('accompy-sheet-cleanup-style');
  if (!style) {
    style = doc.createElement('style');
    style.id = 'accompy-sheet-cleanup-style';
    doc.head?.appendChild(style);
  }

  style.textContent = `
    h1 { display: none !important; }
    body {
      padding-top: 0 !important;
      margin-top: 0 !important;
      background: ${darkMode ? '#0f0f13' : '#f4f1ea'} !important;
      color: ${darkMode ? '#f2efe8' : '#111318'} !important;
    }
    .page {
      background: ${darkMode ? '#181824' : '#ffffff'} !important;
      box-shadow: ${darkMode ? '0 6px 18px rgba(0,0,0,.55)' : '0 2px 6px rgba(0,0,0,.18)'} !important;
    }
    svg {
      color: ${darkMode ? '#f2efe8' : '#111318'} !important;
    }
    svg :is(path, ellipse, polygon, polyline, line, text, tspan, use):not(.accompy-measure-highlight) {
      ${darkMode ? 'fill: #f2efe8 !important; stroke: #f2efe8 !important;' : ''}
    }
    svg use {
      ${darkMode ? 'color: #f2efe8 !important; fill: #f2efe8 !important; stroke: #f2efe8 !important;' : ''}
    }
    svg rect:not(.accompy-measure-highlight) {
      ${darkMode ? 'fill: #f2efe8 !important; stroke: #f2efe8 !important;' : ''}
    }
    svg [fill="none"] {
      fill: none !important;
    }
    svg [stroke="none"] {
      stroke: none !important;
    }
    svg rect[fill="white"],
    svg rect[fill="#ffffff"],
    svg rect[fill="#FFF"],
    svg rect[fill="#fff"] {
      fill: ${darkMode ? '#181824' : '#ffffff'} !important;
      stroke: ${darkMode ? '#181824' : '#ffffff'} !important;
    }
  `;
  doc.documentElement.style.colorScheme = darkMode ? 'dark' : 'light';
  if (darkMode) {
    doc.body?.classList.add('accompy-dark-sheet');
  } else {
    doc.body?.classList.remove('accompy-dark-sheet');
  }
  applySheetFrameZoom(frame, state.sheetView?.zoom || 1);
}

function applySheetFrameZoom(frame, zoom = 1) {
  const doc = frame?.contentDocument;
  if (!doc?.documentElement) return;
  const normalized = Math.max(0.4, Math.min(2.5, zoom || 1));
  doc.documentElement.style.zoom = String(normalized);
  if (doc.body) {
    doc.body.style.transformOrigin = 'top left';
  }
}

// ── Score list screen ─────────────────────────────────────────────────────────
async function loadScoreList() {
  if (_appConfig.auth_enabled && !_authUser) {
    updateAuthUI();
    return;
  }
  applyScoreGridColumns(state.scoreGridColumns);
  const { scores = [], items = [] } = await api('/api/scores');
  state.serverScores = scores;
  const grid = document.getElementById('score-grid');
  const itemByName = new Map((items.length ? items : scores.map(name => ({ name, has_sheet: false }))).map((item) => [item.name, item]));
  let scoreItems;
  if (_appConfig.auth_enabled) {
    state.scores = [...scores];
    scoreItems = (items.length ? items : scores.map(name => ({ name, has_sheet: false })));
  } else {
    const existing = new Set(scores);
    let library = loadPersonalScoreLibrary();
    if (!localStorage.getItem(SCORE_LIBRARY_INIT_KEY)) library = scores;
    library = savePersonalScoreLibrary(library.filter((name) => existing.has(name)));
    scoreItems = library
      .map((name) => itemByName.get(name))
      .filter(Boolean);
  }
  grid.innerHTML = scoreItems.map(({ name, has_sheet }) => `
    <div class="score-card" id="card-${name}" onclick="openScore('${name}')">
      <button class="delete-btn" onclick="deleteScore(event, '${name}')" title="Remove from my list">✕</button>
      <div class="score-preview${has_sheet ? '' : ' empty'}">
        ${has_sheet
          ? `<iframe
              class="score-preview-frame"
              src="/api/scores/${encodeURIComponent(name)}/sheet"
              loading="lazy"
              tabindex="-1"
              aria-hidden="true"></iframe>`
          : `<div class="score-preview-empty">No sheet preview</div>`
        }
      </div>
      <div class="score-card-meta">
        <h3>${formatName(name)}</h3>
        <small>${name}</small>
      </div>
    </div>
  `).join('');
  document.querySelectorAll('.score-preview-frame').forEach((frame) => {
    frame.addEventListener('load', () => sanitizeSheetFrame(frame), { once: true });
    sanitizeSheetFrame(frame);
  });
  requestAnimationFrame(() => resizeScorePreviews());
  renderPlayPieceList();
}

function renderPlayPieceList() {
  const root = document.getElementById('play-piece-list');
  if (!root) return;
  const currentName = state.current?.name || null;
  const names = Array.isArray(state.scores) ? state.scores : [];

  if (!names.length) {
    root.innerHTML = '<div class="score-preview-empty">No pieces in your library yet.</div>';
    return;
  }

  root.innerHTML = names.map((name) => {
    const active = name === currentName;
    return `
      <button
        class="play-piece-item${active ? ' active' : ''}"
        ${active ? 'disabled' : ''}
        onclick="openScore('${name}')">
        <span class="play-piece-title">${formatName(name)}</span>
        <span class="play-piece-slug">${name}</span>
      </button>
    `;
  }).join('');
}

function initPlaySidebar() {
  applyPlaySidebarCollapsed(localStorage.getItem(PLAY_SIDEBAR_COLLAPSED_KEY) === '1');
}

function formatName(name) {
  return name.replace(/_/g,' ').replace(/\b\w/g, c => c.toUpperCase());
}

let _musicXmlDisplay = null;

async function renderMusicXmlFallback(xmlText) {
  const host = document.getElementById('sheet-musicxml-fallback');
  if (!host || !window.opensheetmusicdisplay?.OpenSheetMusicDisplay) return false;
  host.innerHTML = '';
  host.style.display = 'block';
  try {
    _musicXmlDisplay = new window.opensheetmusicdisplay.OpenSheetMusicDisplay(host, {
      autoResize: true,
      drawTitle: false,
      drawPartNames: true,
      backend: 'svg',
    });
    await _musicXmlDisplay.load(xmlText);
    _musicXmlDisplay.render();
    fitSheetToWidth();
    return true;
  } catch (error) {
    console.warn('MusicXML fallback render failed:', error);
    host.innerHTML = '';
    host.style.display = 'none';
    return false;
  }
}

// ── Sheet viewer toolbar ─────────────────────────────────────────────────────
function applySheetView() {
  const wrap = document.getElementById('sheet-content-wrap');
  const frame = document.getElementById('sheet-frame');
  const fallback = document.getElementById('sheet-musicxml-fallback');
  const label = document.getElementById('sheet-zoom-label');
  if (!wrap) return;
  const { zoom, rotation } = state.sheetView;

  const frameVisible = frame && frame.style.display !== 'none';
  const fallbackVisible = fallback && fallback.style.display !== 'none';

  // OSMD uses native zoom so the SVG re-renders at the requested size
  // instead of being bitmap-scaled. This also avoids resize-feedback loops.
  if (fallbackVisible && _musicXmlDisplay) {
    try {
      _musicXmlDisplay.Zoom = zoom;
      _musicXmlDisplay.render();
    } catch (e) { console.warn('OSMD zoom failed', e); }
  }
  if (frameVisible) {
    applySheetFrameZoom(frame, zoom);
  }

  wrap.style.transformOrigin = 'top left';
  const parts = [];
  if (rotation) parts.push(`rotate(${rotation}deg)`);
  wrap.style.transform = parts.join(' ');

  if (label) label.textContent = `${Math.round(zoom * 100)}%`;
}

function sheetZoom(delta) {
  const next = Math.max(0.4, Math.min(2.5, (state.sheetView.zoom || 1) + delta));
  state.sheetView.zoom = Math.round(next * 100) / 100;
  state.sheetView.autoFit = false;
  applySheetView();
}

function sheetRotate() {
  state.sheetView.rotation = (state.sheetView.rotation + 90) % 360;
  applySheetView();
}

function sheetResetView() {
  state.sheetView = { zoom: 1.0, rotation: 0, autoFit: true };
  applySheetView();
  fitSheetToWidth();
}

function resetSheetView() {
  state.sheetView = { zoom: 1.0, rotation: 0, autoFit: true };
  applySheetView();
}

function fitSheetToWidth(retry = 0) {
  if (!state.sheetView?.autoFit) return;
  const viewer = document.getElementById('sheet-viewer');
  const frame = document.getElementById('sheet-frame');
  const fallback = document.getElementById('sheet-musicxml-fallback');
  if (!viewer) return;

  const frameVisible = frame && frame.style.display !== 'none';
  const fallbackVisible = fallback && fallback.style.display !== 'none';
  const viewerWidth = viewer.clientWidth;

  const retryLater = () => {
    if (retry < 8) setTimeout(() => fitSheetToWidth(retry + 1), 80);
  };

  if (frameVisible) {
    const doc = frame.contentDocument;
    if (!doc?.documentElement) { retryLater(); return; }
    const prev = doc.documentElement.style.zoom;
    doc.documentElement.style.zoom = '1';
    // Measure the actual page element — scrollWidth is clamped to viewport
    // when the iframe is wider than the fixed 210mm page.
    const page = doc.querySelector('.page');
    let natural = page?.getBoundingClientRect().width || 0;
    if (!natural) {
      const svg = doc.querySelector('.page svg, svg');
      natural = svg?.getBoundingClientRect().width || 0;
    }
    if (!natural) natural = doc.body?.scrollWidth || doc.documentElement.scrollWidth || 0;
    doc.documentElement.style.zoom = prev;
    if (!natural || !viewerWidth) { retryLater(); return; }
    const z = Math.max(0.4, Math.min(2.5, viewerWidth / natural));
    state.sheetView.zoom = Math.round(z * 100) / 100;
    applySheetView();
  } else if (fallbackVisible && _musicXmlDisplay) {
    if (!viewerWidth) { retryLater(); return; }
    // OSMD's autoResize already paginates to the host width — keep zoom at 1.
    state.sheetView.zoom = 1.0;
    applySheetView();
  }
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function sheetDownload() {
  const src = state.sheetSource;
  if (!src || !src.name) {
    alert('Open a score first.');
    return;
  }
  if (src.hasSheet) {
    try {
      const resp = await fetch(`/api/scores/${encodeURIComponent(src.name)}/sheet`);
      const html = await resp.text();
      triggerDownload(new Blob([html], { type: 'text/html' }), `${src.name}.sheet.html`);
    } catch (err) {
      alert(`Download failed: ${err}`);
    }
    return;
  }
  if (src.musicXml) {
    triggerDownload(
      new Blob([src.musicXml], { type: 'application/vnd.recordare.musicxml+xml' }),
      `${src.name}.musicxml`
    );
    return;
  }
  alert('No sheet source available to download.');
}

// ── Play screen ───────────────────────────────────────────────────────────────
async function fetchScore(name) {
  const scope = _appConfig.auth_enabled
    ? (_authUser?.id || _authUser?.username || 'auth')
    : 'local';
  const CACHE_KEY = `accompy_score_v2_${scope}_${name}`;
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
  if (state.playing && state.current?.name !== name) stopPlaying();
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
  const musicXmlFallback = document.getElementById('sheet-musicxml-fallback');
  musicXmlFallback.style.display = 'none';
  musicXmlFallback.innerHTML = '';
  state.sheetSource = { name, hasSheet: !!data.has_sheet, musicXml: data.musicxml_source || null };
  resetSheetView();
  if (data.has_sheet) {
    frame.onload = () => {
      sanitizeSheetFrame(frame);
      initializeSheetHighlighting();
      fitSheetToWidth();
    };
    frame.src = `/api/scores/${name}/sheet?v=${encodeURIComponent(data._mtime ?? Date.now())}`;
    frame.style.display = 'block';
    placeholder.style.display = 'none';
  } else {
    frame.onload = null;
    frame.style.display = 'none';
    const renderedFallback = data.musicxml_source
      ? await renderMusicXmlFallback(data.musicxml_source)
      : false;
    placeholder.style.display = renderedFallback ? 'none' : 'block';
    placeholder.textContent = renderedFallback
      ? ''
      : 'Sheet preview unavailable for this score.';
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
  renderNoteHighway();
  syncExpectedMicNote();
  preloadCurrentScoreInstruments();
  renderPlayPieceList();
  showScreen('play-screen');
  state.paused = false;
  state.pausedBeat = 0;
  state.pausedBps = 1;
  document.getElementById('start-btn').disabled = false;
  document.getElementById('start-btn').textContent = '▶ Start';
  document.getElementById('start-btn').classList.add('btn-primary');
  document.getElementById('stop-btn').disabled  = true;
}

async function selectPart(idx) {
  state.selectedPart = idx;
  document.querySelectorAll('.part-btn').forEach((b, i) =>
    b.classList.toggle('selected', i === idx));
  buildKeyboard(getRightHand());
  updateNextKey(getRightHand(), 0);
  renderNoteHighway();
  syncExpectedMicNote();
  preloadCurrentScoreInstruments();
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
  preloadCurrentScoreInstruments();
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
  return left.map((event) => {
    const merged = [eventPitches(event), event[1], eventDuration(event)];
    const pedalRelease = eventPedalRelease(event);
    if (pedalRelease !== null) merged.push(pedalRelease);
    return merged;
  });
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
        fill: rgba(98, 255, 140, 0.96);
        stroke: rgba(190, 255, 205, 0.95);
        stroke-width: 4px;
        rx: 10px;
        ry: 10px;
        filter: drop-shadow(0 0 10px rgba(98, 255, 140, 0.65));
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
  if (idx < 0) return;

  const measureEl = _sheetMeasureEls[idx];
  if (!measureEl) return;
  const doc = measureEl.ownerDocument;
  const overlayRoot = doc.querySelector('svg.definition-scale g.page-margin') || measureEl.parentNode;
  if (!overlayRoot) return;

  const bbox = measureEl.getBBox();
  const starts = state.current?.measure_beats || [];
  const measureStart = starts[idx] ?? 0;
  const nextStart = starts[idx + 1];
  const previousSpan = idx > 0 ? ((starts[idx] ?? 0) - (starts[idx - 1] ?? 0)) : 4;
  const measureSpan = Math.max(0.25, (nextStart ?? (measureStart + previousSpan || 4)) - measureStart);
  const progress = Math.max(0, Math.min(1, (beat - measureStart) / measureSpan));
  const barWidth = 14;
  const minX = bbox.x - 7;
  const maxX = bbox.x + bbox.width - 7;
  const x = minX + (maxX - minX) * progress;
  const y = bbox.y - 18;
  const height = bbox.height + 36;

  if (!_sheetHighlightRect || idx !== _sheetHighlightIndex) {
    _sheetHighlightRect?.remove();
    const rect = doc.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('class', 'accompy-measure-highlight');
    rect.setAttribute('width', String(barWidth));
    rect.setAttribute('height', String(height));
    overlayRoot.appendChild(rect);
    _sheetHighlightRect = rect;
    _sheetHighlightIndex = idx;
    measureEl.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }

  _sheetHighlightRect.setAttribute('x', String(x));
  _sheetHighlightRect.setAttribute('y', String(y));
  _sheetHighlightRect.setAttribute('width', String(barWidth));
  _sheetHighlightRect.setAttribute('height', String(height));
}

// ── Keyboard visualiser ───────────────────────────────────────────────────────
function expectedKeyboardPitch() {
  const rightHand = getRightHand();
  const position = state.tracker?.position ?? 0;
  return leadPitchFromEvent(rightHand[position] ?? rightHand[0]) ?? 60;
}

function resolveTypedMidi(code, shifted = false) {
  const layout = SIMPLE_KEY_LAYOUT[code];
  if (!layout) return undefined;
  const pitchClass = (layout.natural + (shifted && SHARPABLE_CODES.has(code) ? 1 : 0)) % 12;
  const rightHand = getRightHand();
  const position = state.tracker?.position ?? 0;
  const expectedEvent = rightHand[position] ?? rightHand[0];
  const expectedPitches = eventPitches(expectedEvent);

  const exactMatch = expectedPitches.find((pitch) => pitch % 12 === pitchClass);
  if (exactMatch !== undefined) return exactMatch;

  const target = expectedKeyboardPitch();

  let midi = pitchClass;
  while (midi < target - 6) midi += 12;
  while (midi > target + 6) midi -= 12;
  while (midi < 24) midi += 12;
  while (midi > 108) midi -= 12;
  return midi;
}

function cueKeyIdForMidi(midi) {
  const slot = VISUAL_SLOTS.find((entry) => entry.pitchClass === (midi % 12));
  return slot ? `kbslot-${slot.id}` : null;
}

function laneCodeForMidi(midi) {
  return VISUAL_SLOTS.find((entry) => entry.pitchClass === (midi % 12)) || null;
}

function currentGuideBeat(rightHand) {
  if (!rightHand.length) return 0;
  const trackerPos = state.tracker?.position ?? 0;
  const expectedBeat = rightHand[trackerPos]?.[1]
    ?? rightHand[rightHand.length - 1]?.[1]
    ?? 0;
  if (state.paused) return Math.min(state.pausedBeat ?? 0, expectedBeat);

  const last = state.tracker?.timestamps?.[state.tracker.timestamps.length - 1];
  const anchorBeat = last?.beat ?? _noteHighwayStartBeat ?? 0;
  const anchorTime = last?.time ?? _noteHighwayStartTime;
  const bps = state.tracker?.bps?.() ?? _noteHighwayBps ?? 1;
  if (!last && trackerPos === 0) return Math.max(0, expectedBeat - OPENING_GUIDE_LEAD_BEATS);
  if (!anchorTime) return Math.min(anchorBeat, expectedBeat);

  const estimated = anchorBeat + Math.max(0, performance.now() / 1000 - anchorTime) * bps;
  return Math.min(estimated, expectedBeat);
}

function ensureNoteHighway() {
  const root = document.getElementById('note-highway');
  if (!root || root.dataset.ready === '1') return;
  root.innerHTML = VISUAL_SLOTS.map((slot) => {
    return `<div class="note-lane ${slot.kind}" data-lane="${slot.id}">
      <div class="note-lane-label">${slot.noteName}</div>
      <div class="note-hit-line"></div>
    </div>`;
  }).join('');
  root.dataset.ready = '1';
}

const HIGHWAY_LOOK_BEHIND_BEATS = 0.5;
const HIGHWAY_LOOK_AHEAD_BEATS = 4;
const HIGHWAY_TOP_PADDING = 12;
const HIGHWAY_MIN_BAR_HEIGHT = 3;
const HIGHWAY_BAR_GAP_BEATS = 0.06;

function resolveSustainBeats(event, nextBeat) {
  const beat = event?.[1];
  const gap = (Number.isFinite(nextBeat) && Number.isFinite(beat)) ? (nextBeat - beat) : Infinity;
  const fallback = Number.isFinite(gap) ? gap : 0.75;
  const raw = eventDuration(event, fallback);
  const cap = Number.isFinite(gap) ? Math.max(0.02, gap - HIGHWAY_BAR_GAP_BEATS) : raw;
  return Math.max(0.02, Math.min(raw, cap));
}

// bar's bottom = hit line at onset (delta=0); bar's height = sustain * pxPerBeat.
function computeBarGeometry(delta, sustainBeats, laneHeight, hitLineTop, pixelsPerBeat) {
  const bottomRaw = hitLineTop - delta * pixelsPerBeat;
  const topRaw = bottomRaw - sustainBeats * pixelsPerBeat;
  const top = Math.max(HIGHWAY_TOP_PADDING, topRaw);
  const bottom = Math.min(laneHeight, bottomRaw);
  if (bottom - top < HIGHWAY_MIN_BAR_HEIGHT) return null;
  return { top, height: bottom - top };
}

function renderNoteHighway() {
  ensureNoteHighway();
  const root = document.getElementById('note-highway');

  const rightHand = getRightHand();
  const trackerPos = state.tracker?.position ?? 0;
  const hasMatchedAnyNote = (state.tracker?.timestamps?.length ?? 0) > 0;
  const openingOnlyCurrent = trackerPos === 0 && !hasMatchedAnyNote;
  const currentBeat = rightHand.length ? currentGuideBeat(rightHand) : 0;
  updateSheetHighlight(currentBeat);

  renderFullKeyboardHighway(rightHand, trackerPos, currentBeat, openingOnlyCurrent);

  if (!root) return;
  root.querySelectorAll('.note-bar').forEach((el) => el.remove());
  if (!rightHand.length) return;

  const firstLane = root.querySelector('.note-lane');
  const hitLineEl = firstLane?.querySelector('.note-hit-line');
  if (!firstLane || !hitLineEl) return;
  const laneRect = firstLane.getBoundingClientRect();
  const hitRect = hitLineEl.getBoundingClientRect();
  if (!laneRect.height) return;
  const laneHeight = laneRect.height;
  const hitLineTop = hitRect.top - laneRect.top;
  const pixelsPerBeat = (hitLineTop - HIGHWAY_TOP_PADDING) / HIGHWAY_LOOK_AHEAD_BEATS;

  const startIndex = Math.max(0, trackerPos - 1);

  for (let i = startIndex; i < rightHand.length; i++) {
    const event = rightHand[i];
    if (openingOnlyCurrent && i !== trackerPos) continue;
    const beat = event?.[1];
    const delta = beat - currentBeat;
    if (delta < -HIGHWAY_LOOK_BEHIND_BEATS) continue;
    if (delta > HIGHWAY_LOOK_AHEAD_BEATS) break;

    const sustainBeats = resolveSustainBeats(event, rightHand[i + 1]?.[1]);
    const geom = computeBarGeometry(delta, sustainBeats, laneHeight, hitLineTop, pixelsPerBeat);
    if (!geom) continue;

    eventPitches(event).forEach((midi) => {
      const lane = laneCodeForMidi(midi);
      if (!lane) return;
      const laneEl = root.querySelector(`[data-lane="${lane.id}"]`);
      if (!laneEl) return;
      const bar = document.createElement('div');
      bar.className = `note-bar${lane.sharp ? ' sharp' : ''}${i === trackerPos ? ' current' : ''}`;
      bar.style.top = `${geom.top}px`;
      bar.style.height = `${geom.height}px`;
      laneEl.appendChild(bar);
    });
  }
}

function renderFullKeyboardHighway(rightHand, trackerPos, currentBeat, openingOnlyCurrent = false) {
  const root = document.getElementById('full-note-highway');
  const hitLineEl = root?.querySelector('.full-note-hit-line');
  if (!root || !hitLineEl) return;

  root.querySelectorAll('.full-note-bar').forEach((el) => el.remove());
  if (!rightHand.length) return;

  const rootRect = root.getBoundingClientRect();
  const hitRect = hitLineEl.getBoundingClientRect();
  if (!rootRect.width || !rootRect.height) return;
  const laneHeight = rootRect.height;
  const hitLineTop = hitRect.top - rootRect.top;
  const pixelsPerBeat = (hitLineTop - HIGHWAY_TOP_PADDING) / HIGHWAY_LOOK_AHEAD_BEATS;

  const startIndex = Math.max(0, trackerPos - 1);

  for (let i = startIndex; i < rightHand.length; i++) {
    const event = rightHand[i];
    if (openingOnlyCurrent && i !== trackerPos) continue;
    const beat = event?.[1];
    const delta = beat - currentBeat;
    if (delta < -HIGHWAY_LOOK_BEHIND_BEATS) continue;
    if (delta > HIGHWAY_LOOK_AHEAD_BEATS) break;

    const sustainBeats = resolveSustainBeats(event, rightHand[i + 1]?.[1]);
    const geom = computeBarGeometry(delta, sustainBeats, laneHeight, hitLineTop, pixelsPerBeat);
    if (!geom) continue;

    eventPitches(event).forEach((midi) => {
      const keyEl = document.getElementById(`refkey-${midi}`);
      if (!keyEl) return;
      const keyRect = keyEl.getBoundingClientRect();
      const bar = document.createElement('div');
      bar.className = `full-note-bar${isBlackKeyMidi(midi) ? ' sharp' : ''}${i === trackerPos ? ' current' : ''}`;
      bar.style.left = `${Math.max(0, keyRect.left - rootRect.left + 2)}px`;
      bar.style.width = `${Math.max(8, keyRect.width - 4)}px`;
      bar.style.top = `${geom.top}px`;
      bar.style.height = `${geom.height}px`;
      root.appendChild(bar);
    });
  }
}

function stopNoteHighwayLoop() {
  if (_noteHighwayRaf) cancelAnimationFrame(_noteHighwayRaf);
  _noteHighwayRaf = null;
}

function startNoteHighwayLoop() {
  stopNoteHighwayLoop();
  const tick = () => {
    renderNoteHighway();
    if (state.playing && !state.paused) _noteHighwayRaf = requestAnimationFrame(tick);
  };
  tick();
}

function buildKeyboard(rightHand) {
  const nextPitches = eventPitches(rightHand[0]);

  const row = document.getElementById('kb-row-main');
  row.innerHTML = SIMPLE_KEY_ORDER.map((code) => {
    const naturalSlot = VISUAL_SLOTS.find((slot) => slot.code === code && !slot.sharp);
    const sharpSlot = VISUAL_SLOTS.find((slot) => slot.code === code && slot.sharp);
    const naturalIsNext = naturalSlot && nextPitches.some((pitch) => pitch % 12 === naturalSlot.pitchClass);
    const sharpIsNext = sharpSlot && nextPitches.some((pitch) => pitch % 12 === sharpSlot.pitchClass);

    return `<div class="kb-key-wrap">
      <div class="kb-key kb-key-white${naturalIsNext ? ' next' : ''}" id="kbslot-${naturalSlot.id}">
        <span class="key-char">${naturalSlot.keyLabel}</span>
        <span class="note-name">${naturalSlot.noteName}</span>
      </div>
      ${sharpSlot ? `
        <div class="kb-key kb-key-black${sharpIsNext ? ' next' : ''}" id="kbslot-${sharpSlot.id}">
          <span class="key-char">${sharpSlot.keyLabel}</span>
          <span class="note-name">${sharpSlot.noteName}</span>
        </div>
      ` : ''}
    </div>`;
  }).join('');

  buildReferenceKeyboard();
  applyKeyboardLayoutMode(state.keyboardLayoutMode);
}

function buildReferenceKeyboard() {
  const whiteRoot = document.getElementById('full-kb-whites');
  const blackRoot = document.getElementById('full-kb-blacks');
  if (!whiteRoot || !blackRoot) return;

  let whiteIndex = 0;
  const whiteKeys = [];
  const blackKeys = [];

  for (let midi = FULL_KEYBOARD_START; midi <= FULL_KEYBOARD_END; midi++) {
    const label = pitchName(midi);
    if (isBlackKeyMidi(midi)) {
      blackKeys.push(
        `<div class="ref-key ref-key-black" id="refkey-${midi}" data-midi="${midi}" style="left: calc(${whiteIndex} * var(--ref-white-width) - var(--ref-black-offset));">
          <span class="ref-key-note">${label}</span>
        </div>`
      );
    } else {
      whiteKeys.push(
        `<div class="ref-key ref-key-white" id="refkey-${midi}" data-midi="${midi}">
          <span class="ref-key-note">${label}</span>
        </div>`
      );
      whiteIndex += 1;
    }
  }

  whiteRoot.innerHTML = whiteKeys.join('');
  blackRoot.innerHTML = blackKeys.join('');
}

function scrollReferenceKeyboardToMidi(midi) {
  if (state.keyboardLayoutMode !== 'full') return;
  const shell = document.getElementById('reference-keyboard-shell');
  const key = document.getElementById(`refkey-${midi}`);
  if (!shell || !key) return;
  key.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
}

function highlightKey(key, on) {
  const el = document.getElementById(key);
  if (el) el.classList.toggle('active', on);
}

function updateNextKey(rightHand, position) {
  document.querySelectorAll('.kb-key.next, .kb-sharp.next, .ref-key.next')
    .forEach(el => el.classList.remove('next'));
  if (position >= rightHand.length) {
    renderNoteHighway();
    return;
  }

  const event = rightHand[position];
  eventPitches(event).forEach((midi) => {
    const keyId = cueKeyIdForMidi(midi);
    if (keyId) document.getElementById(keyId)?.classList.add('next');
    document.getElementById(`refkey-${midi}`)?.classList.add('next');
  });
  document.getElementById('next-note-display').textContent = eventLabel(event);
  scrollReferenceKeyboardToMidi(leadPitchFromEvent(event));
  renderNoteHighway();
  syncExpectedMicNote();
}

// ── Start / Stop ──────────────────────────────────────────────────────────────
function handleStartPause() {
  if (!state.playing) {
    return startPlaying();
  }
  return togglePausePlaying();
}

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
  const stopBtn = document.getElementById('stop-btn');
  startBtn.disabled = true;
  const originalLabel = '▶ Start';
  startBtn.textContent = 'Loading...';

  try {
    await ensureSamplePlayback(instrumentsInUse);
  } finally {
    startBtn.textContent = originalLabel;
  }

  const missingSampleInstrument = instrumentsInUse.find((instrument) =>
    isSampleBackedInstrument(instrument) && !hasLoadedSampler(instrument)
  );
  if (missingSampleInstrument) {
    startBtn.disabled = false;
    stopBtn.disabled = true;
    startBtn.textContent = '▶ Start';
    startBtn.classList.add('btn-primary');
    stopBtn.textContent = '■ End';
    alert(`Could not load the sampled ${missingSampleInstrument} instrument yet. Reload and try again.`);
    return;
  }

  state.tracker     = new Tracker(right, initialBps);
  state.accompanist = new Accompanist(left, right, initialBps, leftInstruments);
  state.accompanist.start();
  state.playing = true;
  state.paused = false;
  state.pausedBeat = 0;
  state.pausedBps = initialBps;
  _noteHighwayStartTime = null;
  _noteHighwayStartBeat = 0;
  _noteHighwayBps = initialBps;

  startBtn.disabled = false;
  stopBtn.disabled  = false;
  startBtn.textContent = '❚❚ Pause';
  startBtn.classList.add('btn-primary');
  stopBtn.textContent = '■ End';

  updateNextKey(right, 0);
  updateSheetHighlight(0);
  startNoteHighwayLoop();
  enableMidi();
  if (_inputMode === 'mic') _startMic();
  syncExpectedMicNote();
}

function togglePausePlaying() {
  if (!state.playing || !state.tracker) return;

  const startBtn = document.getElementById('start-btn');
  if (!startBtn) return;

  if (!state.paused) {
    state.pausedBeat = currentGuideBeat(getRightHand());
    state.pausedBps = state.tracker?.bps?.() ?? _noteHighwayBps ?? 1;
    state.paused = true;
    state.accompanist?.pause();
    _stopMic();
    stopNoteHighwayLoop();
    updateSheetHighlight(state.pausedBeat);
    renderNoteHighway();
    startBtn.textContent = '▶ Resume';
    return;
  }

  state.paused = false;
  _noteHighwayStartBeat = state.pausedBeat ?? 0;
  _noteHighwayStartTime = performance.now() / 1000;
  _noteHighwayBps = state.pausedBps ?? (state.tracker?.bps?.() ?? 1);
  state.accompanist?.resume(_noteHighwayStartBeat, _noteHighwayBps);
  startBtn.textContent = '❚❚ Pause';
  startNoteHighwayLoop();
  if (_inputMode === 'mic') _startMic();
  syncExpectedMicNote();
}

function stopPlaying(reason = 'stopped') {
  if (state.accompanist) state.accompanist.stop();
  _stopMic();
  stopNoteHighwayLoop();
  const finished = reason === 'finished' && !!state.tracker?.isFinished?.();
  state.playing = false;
  state.paused = false;
  state.pausedBeat = 0;
  _noteHighwayStartTime = null;
  const startBtn = document.getElementById('start-btn');
  const stopBtn = document.getElementById('stop-btn');
  startBtn.disabled = false;
  stopBtn.disabled  = true;
  startBtn.textContent = '▶ Start';
  startBtn.classList.add('btn-primary');
  stopBtn.textContent = '■ End';
  if (finished) {
    document.getElementById('next-note-display').textContent = 'Finished';
    document.getElementById('progress-fill').style.width = '100%';
  } else {
    document.getElementById('next-note-display').textContent = '—';
  }
  if (typeof _pitchDetector?.setExpectedMidi === 'function') _pitchDetector.setExpectedMidi(null);
  renderNoteHighway();
}

// ── Note handler (called by keyboard and MIDI) ────────────────────────────────
function handleNoteMic(midi) {
  if (!state.playing || state.paused || !state.tracker) return;
  const beat = state.tracker.onNoteFuzzy(midi);
  if (beat !== null) {
    const bps = state.tracker.bps();
    _noteHighwayStartBeat = beat;
    _noteHighwayStartTime = performance.now() / 1000;
    _noteHighwayBps = bps;
    state.accompanist.onRhNote(beat, bps);
    updateSheetHighlight(beat);
    document.getElementById('beat-val').textContent  = beat.toFixed(1);
    document.getElementById('tempo-val').textContent = Math.round(bps * 60) + ' BPM';
    document.getElementById('progress-fill').style.width =
      (state.tracker.progress() * 100).toFixed(1) + '%';
    updateNextKey(getRightHand(), state.tracker.position);
    syncExpectedMicNote();
  }
  if (state.tracker.isFinished()) stopPlaying('finished');
}

function handleNote(midi) {
  if (!state.playing || state.paused || !state.tracker) return;
  const expectedEvent = getRightHand()[state.tracker.position] ?? getRightHand()[0];
  playNote(midi, 0.6, getInstrumentForPart(state.selectedPart ?? 0), {
    duration: expectedEvent ? eventDurationSeconds(expectedEvent, getInstrumentForPart(state.selectedPart ?? 0)) : undefined,
    pedaled: expectedEvent ? isPedaledEvent(expectedEvent) : false,
    pedalHold: expectedEvent ? eventPedalHoldSeconds(expectedEvent) : null,
  });
  const keyId = cueKeyIdForMidi(midi);
  highlightKey(keyId, true);
  highlightKey(`refkey-${midi}`, true);
  setTimeout(() => highlightKey(keyId, false), 120);
  setTimeout(() => highlightKey(`refkey-${midi}`, false), 120);

  const beat = state.tracker.onNote(midi);
  if (beat !== null) {
    const bps = state.tracker.bps();
    _noteHighwayStartBeat = beat;
    _noteHighwayStartTime = performance.now() / 1000;
    _noteHighwayBps = bps;
    state.accompanist.onRhNote(beat, bps);
    updateSheetHighlight(beat);
    document.getElementById('beat-val').textContent  = beat.toFixed(1);
    document.getElementById('tempo-val').textContent = Math.round(bps * 60) + ' BPM';
    document.getElementById('progress-fill').style.width =
      (state.tracker.progress() * 100).toFixed(1) + '%';
    updateNextKey(getRightHand(), state.tracker.position);
  }

  if (state.tracker.isFinished()) stopPlaying('finished');
}

function handleMidiNote(midi) {
  if (!state.playing || state.paused || !state.tracker) return;
  const now = performance.now();
  if (_lastMidiPitch === midi && now - _lastMidiNoteTime < 70) return;
  _lastMidiPitch = midi;
  _lastMidiNoteTime = now;
  const keyId = cueKeyIdForMidi(midi);
  highlightKey(keyId, true);
  highlightKey(`refkey-${midi}`, true);
  setTimeout(() => highlightKey(keyId, false), 120);
  setTimeout(() => highlightKey(`refkey-${midi}`, false), 120);

  const beat = state.tracker.onNote(midi);
  if (beat !== null) {
    const bps = state.tracker.bps();
    _noteHighwayStartBeat = beat;
    _noteHighwayStartTime = performance.now() / 1000;
    _noteHighwayBps = bps;
    state.accompanist.onRhNote(beat, bps);
    updateSheetHighlight(beat);
    document.getElementById('beat-val').textContent  = beat.toFixed(1);
    document.getElementById('tempo-val').textContent = Math.round(bps * 60) + ' BPM';
    document.getElementById('progress-fill').style.width =
      (state.tracker.progress() * 100).toFixed(1) + '%';
    updateNextKey(getRightHand(), state.tracker.position);
  }

  if (state.tracker.isFinished()) stopPlaying('finished');
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
    syncExpectedMicNote();
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
    _midiConnected = access.inputs.size > 0;
    for (const input of access.inputs.values()) {
      input.onmidimessage = ({ data }) => {
        const [status, pitch, velocity] = data;
        if ((status & 0xF0) === 0x90 && velocity > 0) handleMidiNote(pitch);
      };
    }
    document.getElementById('midi-status').textContent = 'MIDI: connected';
  }).catch(() => {});
}

// ── Delete piece ─────────────────────────────────────────────────────────────
async function deleteScore(e, name) {
  e.stopPropagation();
  if (_appConfig.auth_enabled) {
    if (!confirm(`Delete "${formatName(name)}" from this account?`)) return;
    await api(`/api/scores/${name}`, { method: 'DELETE' });
    localStorage.removeItem(`accompy_score_v2_${_authUser?.id || _authUser?.username || 'auth'}_${name}`);
    await loadScoreList();
    return;
  }
  if (!confirm(`Remove "${formatName(name)}" from this browser's list?`)) return;
  removeScoreFromLibrary(name);
  await loadScoreList();
}

// ── Add piece modal ───────────────────────────────────────────────────────────
let _searchTimer = null;

function openAddModal() {
  if (_appConfig.auth_enabled && !_authUser) {
    setAuthStatus('Sign in first to add pieces.', 'error');
    return;
  }
  document.getElementById('add-modal').style.display = 'flex';
  document.getElementById('corpus-search').value = '';
  document.getElementById('import-name').value = '';
  document.getElementById('import-files').value = '';
  setImportStatus('No files selected.');
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

const savedScoreGridColumns = localStorage.getItem('accompy_score_grid_columns');
if (savedScoreGridColumns) {
  state.scoreGridColumns = normalizedScoreGridColumns(savedScoreGridColumns);
}
state.keyboardLayoutMode = localStorage.getItem('accompy_keyboard_layout_mode') === 'mini' ? 'mini' : 'full';
applyScoreGridColumns(state.scoreGridColumns);
applyKeyboardLayoutMode(state.keyboardLayoutMode);
applyTheme(localStorage.getItem('accompy_theme') || 'dark');
window.addEventListener('resize', resizeScorePreviews);

let _sheetFitTimer = null;
function scheduleSheetFit() {
  if (!state.sheetView?.autoFit) return;
  clearTimeout(_sheetFitTimer);
  _sheetFitTimer = setTimeout(fitSheetToWidth, 80);
}
window.addEventListener('resize', scheduleSheetFit);
const _sheetViewerEl = document.getElementById('sheet-viewer');
if (_sheetViewerEl && typeof ResizeObserver !== 'undefined') {
  new ResizeObserver(scheduleSheetFit).observe(_sheetViewerEl);
}

// ── Click-to-play on keyboard keys ───────────────────────────────────────────
function midiFromKeyboardEl(el) {
  const refKey = el.closest?.('.ref-key');
  if (refKey) {
    const midi = parseInt(refKey.dataset.midi, 10);
    return Number.isFinite(midi) ? { midi, highlightId: refKey.id } : null;
  }
  const kbKey = el.closest?.('.kb-key');
  if (kbKey?.id?.startsWith('kbslot-')) {
    const slotId = kbKey.id.slice('kbslot-'.length);
    const slot = VISUAL_SLOTS.find((s) => s.id === slotId);
    if (slot) return { midi: 60 + slot.pitchClass, highlightId: kbKey.id };
  }
  return null;
}

const _keyboardSectionEl = document.getElementById('keyboard-section');
if (_keyboardSectionEl) {
  _keyboardSectionEl.addEventListener('click', (e) => {
    const hit = midiFromKeyboardEl(e.target);
    if (!hit) return;
    if (typeof Tone !== 'undefined' && Tone.start) Tone.start().catch(() => {});
    if (state.playing && !state.paused && state.tracker) {
      // Same flow as a physical keypress — plays the note and advances the tracker.
      handleNote(hit.midi);
      return;
    }
    // Preview mode — piece isn't running; just play the note + flash the key.
    const instrument = getInstrumentForPart(state.selectedPart ?? 0);
    const sampledInstrument = SAMPLE_ALIAS[instrument] || instrument;
    if (_sampleSamplers[sampledInstrument]) {
      playNote(hit.midi, 0.6, instrument, { duration: 0.45 });
    } else {
      playSynthNote(hit.midi, 0.6, 'piano', { duration: 0.45 });
    }
    highlightKey(hit.highlightId, true);
    setTimeout(() => highlightKey(hit.highlightId, false), 180);
  });
}

function onSearchInput() {
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(runSearch, 300);
}

function setImportStatus(message, tone = 'muted') {
  const status = document.getElementById('import-status');
  if (!status) return;
  status.textContent = message;
  status.style.color = tone === 'error'
    ? '#e05c5c'
    : tone === 'success'
      ? 'var(--success)'
      : 'var(--muted)';
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
    addScoreToLibrary(safeName);

    // Refresh score list in background
    await loadScoreList();
  } catch (e) {
    item.classList.remove('adding');
    item.querySelector('button').textContent = '+ Add';
    alert(`Failed to convert: ${e.message}`);
  }
}

async function importScoreFiles() {
  const fileInput = document.getElementById('import-files');
  const nameInput = document.getElementById('import-name');
  const button = document.getElementById('import-btn');
  const files = [...(fileInput?.files || [])];

  if (!files.length) {
    setImportStatus('Choose a MusicXML file, one PDF, or one/more page images first.', 'error');
    return;
  }

  const form = new FormData();
  files.forEach((file) => form.append('files', file));
  form.append('name', (nameInput?.value || '').trim());

  button.disabled = true;
  const isDirectMusicXml = files.length === 1 && /\.(xml|mxl|musicxml)$/i.test(files[0].name || '');
  setImportStatus(isDirectMusicXml ? 'Importing MusicXML and building the score…' : 'Running Audiveris and converting the score…');

  try {
    const response = await fetch('/api/import', { method: 'POST', body: form });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || 'Import failed');
    }
    addScoreToLibrary(payload.name);
    setImportStatus(`Imported ${formatName(payload.name)}.`, 'success');
    await loadScoreList();
    setTimeout(() => closeAddModal(), 350);
  } catch (error) {
    setImportStatus(error.message || 'Import failed.', 'error');
  } finally {
    button.disabled = false;
  }
}

function initImportControls() {
  const importFiles = document.getElementById('import-files');
  const importBtn = document.getElementById('import-btn');

  importFiles?.addEventListener('change', (event) => {
    const files = [...(event.target.files || [])];
    if (!files.length) {
      setImportStatus('No files selected.');
      return;
    }
    const label = files.length === 1
      ? files[0].name
      : `${files.length} files selected`;
    setImportStatus(label);
  });

  importBtn?.addEventListener('click', (event) => {
    event.preventDefault();
    importScoreFiles();
  });
}

window.importScoreFiles = importScoreFiles;

// ── Init ──────────────────────────────────────────────────────────────────────
initLatencyControls();
initImportControls();
initKeyboardLayoutToggle();
initPlaySidebar();
onNoiseGateChange(document.getElementById('noise-gate')?.value || '1');
setLatencyCompensation(localStorage.getItem('accompy_latency_comp_ms') || '0');
initAppConfig().then(() => {
  if (!_appConfig.auth_enabled || _authUser) loadScoreList();
});
