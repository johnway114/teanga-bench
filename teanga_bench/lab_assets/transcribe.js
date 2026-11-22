(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const BLAS = 'https://blasapp.com';
  const LAB_ORIGIN = 'https://research.blasapp.com';
  const SAMPLE_RATE = 16_000;
  const RECORD_LIMIT = 30;
  const FILE_SECONDS = 120;
  const FILE_BYTES = 100 * 1024 * 1024;
  const CHUNK_SECONDS = 20;
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  const OfflineAudioContext = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  const root = $('transcription');
  const siteKey = root.dataset.siteKey;
  const service = $('asr-state');
  const consent = $('consent');
  const challenge = $('verification');
  const recordButton = $('record');
  const recordedPlayer = $('recording');
  const dictation = $('dictation-text');
  const recordStatus = $('record-status');
  const recordTime = $('record-time');
  const recordLevel = $('record-level');
  const fileInput = $('media-file');
  const fileStatus = $('file-status');
  const drop = $('drop-zone');
  const preview = $('media-preview');
  const playingCue = $('playing-cue');
  const list = $('cues');
  const cueStatus = $('cue-status');
  const downloads = [...root.querySelectorAll('[data-export]')];
  const cues = [];
  let available = Boolean(siteKey && OfflineAudioContext && location.origin === LAB_ORIGIN);
  let busy = false;
  let recording = null;
  let recordedBlob = null;
  let recordingSent = false;
  let recordingURL = '';
  let fileJob = null;
  let fileURL = '';
  let extractedURL = '';
  let player = null;
  let turnstileLoader = null;
  let microphonePending = false;
  let closing = false;
  let requestController = null;

  function updateControls() {
    const recordingActive = Boolean(recording || microphonePending);
    const maySend = available && consent.checked && !busy && !recordingActive;
    $('send-recording').disabled = !maySend || !recordedBlob || recordingSent;
    $('clear-recording').disabled = !recordedBlob || busy || recordingActive;
    $('send-file').disabled = !maySend || !fileJob || !fileJob.eligible || fileJob.done;
    $('extract-audio').disabled = busy || !OfflineAudioContext || !fileJob?.eligible || Boolean(extractedURL);
    $('clear-file').disabled = busy || !fileJob;
    recordButton.disabled = !window.MediaRecorder || !navigator.mediaDevices?.getUserMedia || busy || microphonePending || Boolean(recording && recording.recorder.state === 'inactive');
    fileInput.disabled = busy;
    for (const button of downloads) button.disabled = !cues.some((cue) => cue.text.trim());
    $('copy-dictation').disabled = !dictation.value.trim();
    $('download-dictation').disabled = !dictation.value.trim();
  }

  function element(tag, text = '') {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
  }

  function setAvailability(message) {
    available = false;
    service.textContent = message;
    $('upload-consent').hidden = true;
    updateControls();
  }

  function loadTurnstile() {
    if (window.turnstile) return Promise.resolve(window.turnstile);
    if (!turnstileLoader) {
      turnstileLoader = new Promise((resolve, reject) => {
        const script = element('script');
        const fail = () => {
          clearTimeout(timer);
          script.remove();
          reject(new Error('Verification could not load. Local editing and export still work.'));
        };
        const timer = setTimeout(fail, 15_000);
        script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
        script.async = true;
        script.onerror = fail;
        script.onload = () => {
          if (!window.turnstile) return fail();
          window.turnstile.ready(() => {
            clearTimeout(timer);
            resolve(window.turnstile);
          });
        };
        document.head.append(script);
      }).catch((error) => {
        turnstileLoader = null;
        throw error;
      });
    }
    return turnstileLoader;
  }

  async function verify(signal) {
    const turnstile = await loadTurnstile();
    if (signal.aborted) throw new Error('Transcription was cancelled.');
    return new Promise((resolve, reject) => {
      let widget;
      let settled = false;
      const target = challenge.appendChild(element('div'));
      const finish = (error, token) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        signal.removeEventListener('abort', cancelled);
        if (widget !== undefined) turnstile.remove(widget);
        target.remove();
        if (error) reject(error);
        else resolve(token);
      };
      const failed = () => {
        finish(new Error('Verification expired or failed. You can try again when ready.'));
        return true;
      };
      const cancelled = () => finish(new Error('Transcription was cancelled.'));
      const timer = setTimeout(failed, 120_000);
      signal.addEventListener('abort', cancelled, { once: true });
      try {
        widget = turnstile.render(target, {
          sitekey: siteKey,
          action: 'lab_transcribe',
          size: 'compact',
          appearance: 'interaction-only',
          execution: 'execute',
          retry: 'never',
          'refresh-expired': 'manual',
          'refresh-timeout': 'manual',
          'response-field': false,
          callback: (token) => finish(null, token),
          'error-callback': failed,
          'expired-callback': failed,
          'timeout-callback': failed,
          'before-interactive-callback': () => challenge.scrollIntoView({ block: 'nearest' }),
        });
        turnstile.execute(widget);
      } catch {
        failed();
      }
    });
  }

  // Decode at the target sample rate, then downmix using the browser's Web Audio channel rules.
  async function decode(blob, maxSeconds, limitMessage) {
    let buffer;
    try {
      const decoder = new OfflineAudioContext(1, 1, SAMPLE_RATE);
      buffer = await decoder.decodeAudioData(await blob.arrayBuffer());
    } catch {
      throw new Error('This browser could not extract audio from the file. Try WAV or MP3, or add subtitle cues manually.');
    }
    if (buffer.duration > maxSeconds) throw new Error(limitMessage);
    if (buffer.numberOfChannels === 1) return buffer.getChannelData(0);
    const mixer = new OfflineAudioContext(1, buffer.length, SAMPLE_RATE);
    const source = mixer.createBufferSource();
    source.buffer = buffer;
    source.connect(mixer.destination);
    source.start();
    return (await mixer.startRendering()).getChannelData(0);
  }

  function wav(samples) {
    const bytes = new Uint8Array(44 + samples.length * 2);
    const view = new DataView(bytes.buffer);
    const header = (offset, value) => {
      for (let i = 0; i < value.length; i++) bytes[offset + i] = value.charCodeAt(i);
    };
    header(0, 'RIFF');
    view.setUint32(4, bytes.length - 8, true);
    header(8, 'WAVEfmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, SAMPLE_RATE, true);
    view.setUint32(28, SAMPLE_RATE * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    header(36, 'data');
    view.setUint32(40, samples.length * 2, true);
    for (let i = 0; i < samples.length; i++) {
      const sample = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(44 + i * 2, Math.round(sample * (sample < 0 ? 32768 : 32767)), true);
    }
    return bytes;
  }

  function base64(bytes) {
    const parts = [];
    for (let i = 0; i < bytes.length; i += 8192) parts.push(String.fromCharCode(...bytes.subarray(i, i + 8192)));
    return btoa(parts.join(''));
  }

  // Energy-based segmentation. Silence is not timestamped as speech; long active
  // regions are split at the quietest frame near the 20-second limit.
  function segments(samples) {
    const frame = SAMPLE_RATE / 50;
    const frames = Math.ceil(samples.length / frame);
    const rms = new Float32Array(frames);
    for (let i = 0; i < frames; i++) {
      const end = Math.min((i + 1) * frame, samples.length);
      let sum = 0;
      for (let at = i * frame; at < end; at++) sum += samples[at] ** 2;
      rms[i] = Math.sqrt(sum / (end - i * frame));
    }
    const levels = rms.slice().sort();
    const noise = levels[Math.floor(levels.length * 0.15)] || 0;
    const threshold = Math.max(0.003, Math.min(0.02, noise * 2.5));
    const limits = [];
    let first = -1;
    let last = -1;
    let voiced = 0;
    const cut = () => {
      if (voiced >= 6) {
        let begin = Math.max(0, first - 5);
        const end = Math.min(frames, last + 6);
        while (end - begin > CHUNK_SECONDS * 50) {
          let boundary = begin + CHUNK_SECONDS * 50;
          for (let candidate = boundary - 75, max = boundary; candidate < max; candidate++) {
            if (rms[candidate] < rms[boundary]) boundary = candidate;
          }
          limits.push([begin * frame, boundary * frame]);
          begin = boundary;
        }
        limits.push([begin * frame, Math.min(end * frame, samples.length)]);
      }
      first = -1;
      last = -1;
      voiced = 0;
    };
    for (let i = 0; i < frames; i++) {
      if (rms[i] >= threshold) {
        if (first === -1) first = i;
        last = i;
        voiced++;
      } else if (first !== -1 && i - last >= 75) {
        cut();
      }
    }
    cut();
    return limits;
  }

  async function transcribe(samples, signal) {
    if (!available || !consent.checked || signal.aborted) throw new Error('Allow audio processing before sending audio.');
    const token = await verify(signal);
    if (!consent.checked || signal.aborted) throw new Error('Transcription was cancelled before sending audio.');
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal.addEventListener('abort', abort, { once: true });
    const timer = setTimeout(abort, 45_000);
    try {
      const result = await fetch(`${BLAS}/api/lab/transcribe`, {
        method: 'POST', credentials: 'omit', redirect: 'error', cache: 'no-store', referrerPolicy: 'no-referrer',
        headers: { 'Content-Type': 'application/json', 'X-Turnstile-Token': token },
        body: JSON.stringify({ audio: base64(wav(samples)), language: 'irish' }),
        signal: controller.signal,
      });
      if (result.status === 503 || result.status === 404) {
        setAvailability('Automatic transcription is unavailable. You can still preview media, edit cues and export locally.');
        throw new Error('The isolated transcription service is unavailable.');
      }
      if (result.status === 429) throw new Error('The transcription service is busy or at its quota. Try again later.');
      if (result.status === 403) throw new Error('Verification was not accepted. Try again to obtain a new challenge.');
      if (!result.ok) throw new Error('The transcription request failed. Your local edits are still available.');
      const output = await result.json();
      if (typeof output.transcription !== 'string') throw new Error('No valid transcript was returned.');
      return { text: output.transcription.trim(), confidence: output.confidence };
    } catch (error) {
      if (controller.signal.aborted) {
        throw new Error(signal.aborted ? 'Transcription was cancelled.' : 'The request timed out; your local edits are still available.');
      }
      if (error instanceof TypeError) throw new Error('Could not reach the transcription service. Your media and edits are still local.');
      throw error;
    } finally {
      clearTimeout(timer);
      signal.removeEventListener('abort', abort);
    }
  }

  function releaseRecording(session) {
    cancelAnimationFrame(session.animation);
    clearTimeout(session.limit);
    for (const track of session.stream.getTracks()) track.stop();
    if (session.context) session.context.close().catch(() => {});
    recordLevel.value = 0;
    if (recording === session) recording = null;
  }

  function discardRecording() {
    if (recordingURL) URL.revokeObjectURL(recordingURL);
    recordingURL = '';
    recordedBlob = null;
    recordingSent = false;
    recordedPlayer.removeAttribute('src');
    recordedPlayer.load();
    recordedPlayer.hidden = true;
    recordTime.textContent = '0:00';
  }

  function stopRecording() {
    if (recording?.recorder.state === 'recording') {
      recording.recorder.stop();
      clearTimeout(recording.limit);
      updateControls();
    }
  }

  async function startRecording() {
    if (recording) return stopRecording();
    microphonePending = true;
    updateControls();
    recordStatus.textContent = 'Waiting for microphone permission…';
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (closing) {
        for (const track of stream.getTracks()) track.stop();
        return;
      }
      const recorder = new MediaRecorder(stream);
      const chunks = [];
      const session = { recorder, stream, context: null, limit: null, animation: null, failed: false };
      recording = session;
      recorder.addEventListener('dataavailable', (event) => {
        if (event.data.size) chunks.push(event.data);
      });
      recorder.addEventListener('error', () => {
        session.failed = true;
        releaseRecording(session);
        recordStatus.textContent = 'Recording failed. Check your microphone and try again.';
        recordButton.textContent = 'Record';
        updateControls();
      });
      recorder.addEventListener('stop', () => {
        if (session.failed || closing) return;
        releaseRecording(session);
        recordedBlob = new Blob(chunks, { type: recorder.mimeType || chunks[0]?.type });
        recordButton.textContent = 'Record again';
        if (recordedBlob.size) {
          recordingURL = URL.createObjectURL(recordedBlob);
          recordedPlayer.src = recordingURL;
          recordedPlayer.hidden = false;
          recordStatus.textContent = 'Recording ready. Listen back before sending.';
        } else {
          discardRecording();
          recordStatus.textContent = 'No audio was captured.';
        }
        updateControls();
      });
      discardRecording();
      let analyser;
      if (AudioContext) {
        try {
          session.context = new AudioContext();
          analyser = session.context.createAnalyser();
          session.context.createMediaStreamSource(stream).connect(analyser);
          session.context.resume().catch(() => {});
        } catch {
          analyser = null;
        }
      }
      recorder.start();
      const start = performance.now();
      const frame = analyser && new Float32Array(analyser.fftSize);
      const tick = () => {
        if (recorder.state !== 'recording') return;
        const seconds = Math.min(RECORD_LIMIT, Math.floor((performance.now() - start) / 1000));
        recordTime.textContent = `0:${String(seconds).padStart(2, '0')}`;
        if (analyser) {
          analyser.getFloatTimeDomainData(frame);
          let sum = 0;
          for (const sample of frame) sum += sample * sample;
          recordLevel.value = Math.min(1, 4 * Math.sqrt(sum / frame.length));
        }
        session.animation = requestAnimationFrame(tick);
      };
      session.limit = setTimeout(stopRecording, RECORD_LIMIT * 1000);
      tick();
      recordButton.textContent = 'Stop recording';
      recordStatus.textContent = 'Recording locally. Nothing has been sent.';
    } catch (error) {
      if (recording) releaseRecording(recording);
      else if (stream) for (const track of stream.getTracks()) track.stop();
      recordStatus.textContent = error.name === 'NotAllowedError' || error.name === 'SecurityError'
        ? 'Microphone access was denied. Allow it in your browser settings or choose a local file.'
        : 'Could not start the microphone. Check your input device or choose a local file.';
    } finally {
      microphonePending = false;
      updateControls();
    }
  }

  function previewCaption() {
    const time = player?.currentTime;
    const active = Number.isFinite(time) && cues.find((cue) => cue.start <= time && cue.end > time && cue.text.trim());
    playingCue.hidden = !active;
    playingCue.textContent = active ? active.text : '';
  }

  function closeMedia() {
    if (player) {
      player.pause();
      player.removeAttribute('src');
      player.load();
      player = null;
    }
    if (fileURL) URL.revokeObjectURL(fileURL);
    if (extractedURL) URL.revokeObjectURL(extractedURL);
    fileURL = '';
    extractedURL = '';
    fileJob = null;
    $('save-audio').removeAttribute('href');
    $('save-audio').hidden = true;
    $('file-name').textContent = '';
    preview.replaceChildren();
    preview.hidden = true;
    previewCaption();
    for (const button of list.querySelectorAll('[data-seek]')) button.disabled = true;
  }

  function loadFile(file) {
    if (!file || busy) return;
    const ext = file.name.split('.').pop().toLowerCase();
    if (file.size > FILE_BYTES) {
      fileStatus.textContent = 'This file exceeds 100 MiB. Choose a smaller file.';
      return;
    }
    if (!file.size || (!file.type.match(/^(audio|video)\//) && !['wav', 'mp3', 'm4a', 'mp4', 'mov'].includes(ext))) {
      fileStatus.textContent = 'Choose a nonempty audio or video file.';
      return;
    }
    closeMedia();
    fileURL = URL.createObjectURL(file);
    fileJob = { file, eligible: true, done: false, cursor: 0, added: 0, pcm: null, segments: [] };
    $('send-file').textContent = 'Generate subtitle cues';
    $('file-name').textContent = file.name;
    fileStatus.textContent = 'File opened locally. Existing cues are kept.';
    const media = element(file.type.startsWith('video/') || ['mp4', 'mov'].includes(ext) ? 'video' : 'audio');
    player = media;
    media.controls = true;
    media.playsInline = true;
    media.preload = 'metadata';
    media.setAttribute('aria-label', 'Local media preview');
    media.addEventListener('loadedmetadata', () => {
      if (player !== media) return;
      if (media.duration > FILE_SECONDS && Number.isFinite(media.duration)) {
        fileJob.eligible = false;
        fileStatus.textContent = 'This file exceeds the two-minute audio processing limit. Preview and manual cues still work.';
      }
      updateControls();
    });
    media.addEventListener('error', () => {
      if (player === media) fileStatus.textContent = 'This browser cannot preview the file. Try another format or edit cues manually.';
    });
    for (const event of ['timeupdate', 'seeked', 'loadedmetadata']) media.addEventListener(event, previewCaption);
    media.src = fileURL;
    preview.replaceChildren(media);
    preview.hidden = false;
    previewCaption();
    for (const button of list.querySelectorAll('[data-seek]')) button.disabled = false;
    updateControls();
  }

  function glosses(details, cue) {
    const words = element('div');
    const result = element('p', '');
    result.className = 'lab-note';
    result.setAttribute('role', 'status');
    let lookup;
    const refresh = () => {
      lookup?.abort();
      result.textContent = '';
      words.replaceChildren();
      if (!details.open) return;
      const unique = new Map();
      for (const word of cue.text.match(/\p{L}+(?:[-’']\p{L}+)*/gu) || []) {
        unique.set(word.toLocaleLowerCase('ga'), word);
      }
      if (!unique.size) result.textContent = 'Enter cue text to look up its words.';
      for (const word of unique.values()) {
        const button = words.appendChild(element('button', word));
        button.type = 'button';
        button.lang = 'ga';
        button.addEventListener('click', async () => {
          lookup?.abort();
          const controller = new AbortController();
          lookup = controller;
          result.textContent = `Looking up ${word}…`;
          try {
            const query = new URLSearchParams({ language: 'irish', q: word });
            const response = await fetch(`${BLAS}/api/tools/v1/dictionary?${query}`, { credentials: 'omit', referrerPolicy: 'no-referrer', signal: controller.signal });
            if (!response.ok) throw new Error('Dictionary unavailable');
            const { results } = await response.json();
            const exact = results?.find((item) => [item.native, item.mutation?.nativeName, item.verbForm?.form]
              .some((form) => form?.normalize('NFC').toLocaleLowerCase('ga') === word.normalize('NFC').toLocaleLowerCase('ga')));
            if (controller.signal.aborted) return;
            if (!exact) {
              result.textContent = 'No matching dictionary entry.';
              return;
            }
            const source = new URL(exact.url);
            if (source.origin !== BLAS) throw new Error('Invalid dictionary source');
            const notes = [exact.english, exact.gender, exact.mutation?.mutationType].filter(Boolean);
            result.textContent = notes.length ? `${notes.join(' · ')}. ` : '';
            const link = result.appendChild(element('a', exact.native));
            link.lang = 'ga';
            link.href = source.href;
          } catch {
            if (!controller.signal.aborted) result.textContent = 'Could not retrieve the dictionary entry.';
          }
        });
      }
    };
    details.append(element('summary', 'Look up words in this cue'), words, result,
      Object.assign(element('p', 'Only the word you click is sent to the Blas dictionary.'), { className: 'lab-note' }));
    details.addEventListener('toggle', refresh);
    return refresh;
  }

  function addCue({ start, end, text = '', confidence = null }, focus = false) {
    const cue = { start, end, text };
    cues.push(cue);
    const row = list.appendChild(element('li'));
    const times = row.appendChild(element('div'));
    times.className = 'lab-cue-times';
    for (const [key, labelText] of [['start', 'Start (s)'], ['end', 'End (s)']]) {
      const label = times.appendChild(element('label', labelText));
      const input = label.appendChild(element('input'));
      input.type = 'number';
      input.min = '0';
      input.step = '0.001';
      input.value = cue[key];
      input.addEventListener('input', () => {
        cue[key] = input.valueAsNumber;
        previewCaption();
      });
    }
    const label = row.appendChild(element('label', 'Cue text'));
    const textarea = label.appendChild(element('textarea'));
    textarea.rows = 2;
    textarea.lang = 'ga';
    textarea.value = text;
    const actions = row.appendChild(element('div'));
    actions.className = 'lab-cue-actions';
    const seek = actions.appendChild(element('button', 'Go to cue'));
    seek.type = 'button';
    seek.dataset.seek = '';
    seek.disabled = !player;
    seek.addEventListener('click', () => {
      if (!player || !(cue.start >= 0) || player.readyState === 0) return;
      player.currentTime = cue.start;
      previewCaption();
    });
    const remove = actions.appendChild(element('button', 'Remove cue'));
    remove.type = 'button';
    const details = row.appendChild(element('details'));
    details.className = 'lab-gloss';
    const refreshGlosses = glosses(details, cue);
    remove.addEventListener('click', () => {
      cues.splice(cues.indexOf(cue), 1);
      refreshGlosses();
      row.remove();
      $('add-cue').focus();
      previewCaption();
      updateControls();
    });
    if (Number.isFinite(confidence)) {
      const note = row.appendChild(element('p', `Recognition confidence: ${Math.round(confidence * 100)}%`));
      note.className = 'lab-note';
    }
    textarea.addEventListener('input', () => {
      cue.text = textarea.value;
      refreshGlosses();
      previewCaption();
      updateControls();
    });
    if (focus) textarea.focus();
    previewCaption();
    updateControls();
  }

  function timestamp(seconds, separator) {
    const millis = Math.round(seconds * 1000);
    const fields = [Math.floor(millis / 3_600_000), Math.floor(millis / 60_000) % 60, Math.floor(millis / 1000) % 60];
    return fields.map((value) => String(value).padStart(2, '0')).join(':') + separator + String(millis % 1000).padStart(3, '0');
  }

  function download(filename, text, type = 'text/plain;charset=utf-8') {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const link = element('a');
    link.download = filename;
    link.href = url;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function exportCues(format) {
    const selected = cues.filter((cue) => cue.text.trim());
    if (!selected.length) return;
    if (format !== 'txt' && selected.some(({ start, end }) => !Number.isFinite(start) || !Number.isFinite(end) || start < 0 || Math.round(end * 1000) <= Math.round(start * 1000))) {
      cueStatus.textContent = 'Each nonempty cue needs a valid start and a later end before subtitle export.';
      return;
    }
    selected.sort((a, b) => (a.start || 0) - (b.start || 0));
    let text;
    if (format === 'txt') {
      text = selected.map((cue) => cue.text.trim()).join('\n\n') + '\n';
    } else {
      const srt = format === 'srt';
      const separator = srt ? ',' : '.';
      text = (srt ? '' : 'WEBVTT\n\n') + selected.map((cue, index) => {
        const body = cue.text.trim().split('\n').filter((line) => line.trim()).join('\n');
        const literal = body.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
        return `${srt ? `${index + 1}\n` : ''}${timestamp(cue.start, separator)} --> ${timestamp(cue.end, separator)}\n${literal}`;
      }).join('\n\n') + '\n\n';
    }
    const stem = fileJob?.file.name.replace(/\.[^.]+$/, '').replace(/[^\p{L}\p{N}._ -]/gu, '_');
    download(`${stem || 'irish-subtitles'}.${format}`, text, format === 'vtt' ? 'text/vtt;charset=utf-8' : undefined);
    cueStatus.textContent = `${format.toUpperCase()} download requested.`;
  }

  async function withRequest(status, work) {
    if (busy || !available || !consent.checked) return;
    busy = true;
    requestController = new AbortController();
    // Keep verification next to the action that triggered it rather than shifting the page.
    status.before(challenge);
    updateControls();
    try {
      await work(requestController.signal);
    } catch (error) {
      status.textContent = error.message || 'Transcription could not complete.';
    } finally {
      busy = false;
      requestController = null;
      updateControls();
    }
  }

  async function sendRecording() {
    if (!recordedBlob) return;
    await withRequest(recordStatus, async (signal) => {
      recordStatus.textContent = 'Preparing recording locally…';
      // Encoders can pad the tail by a few samples. Never send more than thirty seconds.
      const pcm = await decode(recordedBlob, RECORD_LIMIT + 1, 'This recording ran over thirty seconds. Please record a shorter clip.');
      const clip = pcm.subarray(0, RECORD_LIMIT * SAMPLE_RATE);
      if (!segments(clip).length) throw new Error('No speech-like audio was detected. Record another clip.');
      recordStatus.textContent = 'Verifying and transcribing recording…';
      const output = await transcribe(clip, signal);
      recordingSent = true;
      if (!output.text) {
        recordStatus.textContent = 'No speech was recognized in this recording.';
        return;
      }
      dictation.value = [dictation.value.trim(), output.text].filter(Boolean).join('\n\n');
      recordStatus.textContent = 'Transcription complete. Review and edit the text before use.';
      $('dictation-status').textContent = Number.isFinite(output.confidence)
        ? `Recognition confidence: ${Math.round(output.confidence * 100)}%.` : '';
    });
  }

  function decodeFile(job) {
    return decode(job.file, FILE_SECONDS, 'This file exceeds the two-minute audio processing limit. You can still add cues manually.');
  }

  async function extractAudio() {
    if (busy || !fileJob?.eligible) return;
    busy = true;
    updateControls();
    const job = fileJob;
    fileStatus.textContent = 'Extracting the audio in your browser…';
    try {
      const pcm = job.pcm ?? await decodeFile(job);
      if (closing) return;
      if (!job.done) job.pcm = pcm;
      extractedURL = URL.createObjectURL(new Blob([wav(pcm)], { type: 'audio/wav' }));
      const link = $('save-audio');
      link.href = extractedURL;
      link.hidden = false;
      fileStatus.textContent = 'Extracted 16 kHz mono WAV. Nothing was sent.';
    } catch (error) {
      fileStatus.textContent = error.message || 'Audio extraction failed.';
    } finally {
      busy = false;
      updateControls();
    }
  }

  async function sendFile() {
    if (!fileJob?.eligible || fileJob.done) return;
    await withRequest(fileStatus, async (signal) => {
      const job = fileJob;
      if (!job.segments.length) {
        fileStatus.textContent = 'Preparing the audio in your browser…';
        job.pcm ??= await decodeFile(job);
        job.segments = segments(job.pcm);
        if (!job.segments.length) {
          job.done = true;
          job.pcm = null;
          fileStatus.textContent = 'No speech-like audio was detected. You can still add cues manually.';
          return;
        }
      }
      for (; job.cursor < job.segments.length; job.cursor++) {
        const [start, end] = job.segments[job.cursor];
        fileStatus.textContent = `Verifying and transcribing audio segment ${job.cursor + 1} of ${job.segments.length}…`;
        const output = await transcribe(job.pcm.subarray(start, end), signal);
        if (output.text) {
          job.added++;
          addCue({ start: Math.round(start / SAMPLE_RATE * 1000) / 1000, end: Math.round(end / SAMPLE_RATE * 1000) / 1000, ...output });
        }
        if (job.cursor + 1 < job.segments.length) $('send-file').textContent = 'Continue transcription';
      }
      job.done = true;
      job.pcm = null;
      $('send-file').textContent = 'Generate subtitle cues';
      fileStatus.textContent = job.added
        ? `${job.added} ${job.added === 1 ? 'cue' : 'cues'} created. Edit the text and check the approximate timings before downloading.`
        : 'No speech was recognized. You can still add cues manually.';
    });
  }

  if (available) $('upload-consent').hidden = false;
  else setAvailability('Automatic transcription is unavailable here. Preview media, write text and export cues locally.');
  if (!window.MediaRecorder || !navigator.mediaDevices?.getUserMedia) {
    recordStatus.textContent = 'Microphone recording is unavailable in this browser or on this connection.';
  }
  for (const section of root.querySelectorAll('[data-js]')) section.hidden = false;
  consent.addEventListener('change', () => {
    if (!consent.checked) requestController?.abort();
    updateControls();
  });
  dictation.addEventListener('input', updateControls);
  recordButton.addEventListener('click', startRecording);
  $('clear-recording').addEventListener('click', () => {
    discardRecording();
    recordButton.textContent = 'Record';
    recordStatus.textContent = 'Local recording discarded.';
    updateControls();
  });
  $('send-recording').addEventListener('click', sendRecording);
  $('send-file').addEventListener('click', sendFile);
  $('extract-audio').addEventListener('click', extractAudio);
  $('clear-file').addEventListener('click', () => {
    closeMedia();
    fileStatus.textContent = 'Local media closed. Subtitle cues are kept.';
    updateControls();
  });
  $('copy-dictation').addEventListener('click', async () => {
    const status = $('dictation-status');
    try {
      await navigator.clipboard.writeText(dictation.value);
      status.textContent = 'Transcript copied.';
    } catch {
      dictation.focus();
      dictation.select();
      status.textContent = 'Clipboard access is blocked. Copy the selected text manually.';
    }
  });
  $('download-dictation').addEventListener('click', () => download('irish-transcript.txt', `${dictation.value.trim()}\n`));
  fileInput.addEventListener('change', () => {
    loadFile(fileInput.files[0]);
    fileInput.value = '';
  });
  drop.addEventListener('dragover', (event) => {
    event.preventDefault();
    if (!busy) drop.classList.add('is-dragging');
  });
  drop.addEventListener('dragleave', () => drop.classList.remove('is-dragging'));
  drop.addEventListener('drop', (event) => {
    event.preventDefault();
    drop.classList.remove('is-dragging');
    loadFile(event.dataTransfer.files[0]);
  });
  $('add-cue').addEventListener('click', () => {
    const last = cues.at(-1)?.end;
    const duration = player?.duration;
    const at = player && Number.isFinite(duration) && player.currentTime < duration ? player.currentTime : 0;
    const start = Math.round((player && !player.paused ? at : Math.max(at, Number.isFinite(last) ? last : 0)) * 1000) / 1000;
    addCue({ start, end: Math.round((start + 3) * 1000) / 1000 }, true);
  });
  for (const button of downloads) button.addEventListener('click', () => exportCues(button.dataset.export));
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stopRecording();
  });
  window.addEventListener('pagehide', (event) => {
    closing = !event.persisted;
    requestController?.abort();
    if (recording) {
      if (closing) releaseRecording(recording);
      else stopRecording();
    }
    if (closing) {
      if (fileURL) URL.revokeObjectURL(fileURL);
      if (extractedURL) URL.revokeObjectURL(extractedURL);
      if (recordingURL) URL.revokeObjectURL(recordingURL);
    }
  });
  updateControls();
})();
