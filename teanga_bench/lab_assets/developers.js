(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const form = $('developer-lookup');
  const query = $('lookup-query');
  const submit = $('lookup-submit');
  const save = $('lookup-download');
  const status = $('lookup-status');
  const list = $('lookup-results');
  const origin = new URL(form.action).origin;
  let output;

  function node(tag, text, parent) {
    const element = document.createElement(tag);
    element.textContent = text;
    parent.append(element);
    return element;
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (submit.disabled) return;
    const term = query.value.trim();
    if (!term) {
      status.textContent = 'Enter a word or an English meaning.';
      query.focus();
      return;
    }
    const params = new URLSearchParams({ q: term, language: $('lookup-language').value });
    submit.disabled = true;
    save.disabled = true;
    output = null;
    list.hidden = true;
    list.replaceChildren();
    status.textContent = 'Looking up your term…';
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(`${origin}/api/tools/v1/dictionary?${params}`, {
        credentials: 'omit', referrerPolicy: 'no-referrer', cache: 'no-store', signal: controller.signal,
      });
      if (!response.ok) {
        if (response.status === 429) throw new Error('The API is at its request limit. Try again later.');
        throw new Error(`Dictionary API returned HTTP ${response.status}.`);
      }
      const result = await response.json();
      if (!Array.isArray(result.results)) throw new Error('The API did not return a dictionary result.');
      for (const entry of result.results) {
        if (!entry || typeof entry.native !== 'string' || typeof entry.english !== 'string') continue;
        const item = node('li', '', list);
        let href;
        try { href = new URL(entry.url); } catch { /* Render malformed links as plain text. */ }
        const headword = node(href?.origin === origin ? 'a' : 'strong', entry.native, item);
        if (headword.tagName === 'A') headword.href = href.href;
        node('p', entry.english, item);
        const details = [entry.partOfSpeech, entry.gender, entry.mutation?.mutationType].filter(Boolean);
        if (details.length) node('p', details.join(' · '), item).className = 'lab-note';
      }
      const count = list.childElementCount;
      status.textContent = count ? `${count} ${count === 1 ? 'entry' : 'entries'} returned by the Blas dictionary.` : 'No matching entry.';
      list.hidden = count === 0;
      output = result;
      save.disabled = false;
    } catch (error) {
      list.replaceChildren();
      status.textContent = controller.signal.aborted ? 'The dictionary API timed out. ' :
        error instanceof TypeError ? 'Could not reach the dictionary API from this browser. ' : `${error.message} `;
      node('a', 'Search the Blas dictionary directly', status).href = `${form.action}?${params}`;
    } finally {
      clearTimeout(timeout);
      submit.disabled = false;
    }
  });

  save.hidden = false;
  save.addEventListener('click', () => {
    if (!output) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(output, null, 2) + '\n'], { type: 'application/json' }));
    const link = node('a', '', document.body);
    link.href = url;
    link.download = 'blas-dictionary-result.json';
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });

  const copy = $('copy-mcp');
  copy.hidden = false;
  copy.addEventListener('click', async () => {
    const config = $('mcp-config');
    const note = $('mcp-copy-status');
    try {
      await navigator.clipboard.writeText(config.textContent + '\n');
      note.textContent = 'MCP configuration copied.';
    } catch {
      const range = document.createRange();
      range.selectNodeContents(config);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      note.textContent = 'Clipboard access was blocked. Copy the selected configuration manually.';
    }
  });
})();
