(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const round = $('blind-round');
  const start = $('start-listening');
  const panel = $('blind-workspace');
  const tracks = $('blind-tracks');
  const reveal = $('reveal-voices');
  const results = $('blind-result');
  const status = $('blind-status');
  const templates = [...round.querySelectorAll('.lab-blind-clip')];
  const names = ['Voice A', 'Voice B'];
  const fields = [...panel.querySelectorAll('fieldset')];
  const heard = new Set();
  let failed = false;
  let revealed = false;
  if (templates.length !== 2) return;

  function node(tag, text, parent) {
    const element = document.createElement(tag);
    element.textContent = text;
    parent.append(element);
    return element;
  }

  start.hidden = false;
  start.addEventListener('click', () => {
    if (crypto.getRandomValues(new Uint8Array(1))[0] & 1) templates.reverse();
    status.textContent = 'Play both voices before choosing a preference.';
    const players = templates.map((template, index) => {
      const track = node('div', '', tracks);
      track.className = 'lab-well';
      node('strong', names[index], track);
      const audio = template.content.firstElementChild.cloneNode(true);
      audio.setAttribute('aria-label', names[index]);
      track.append(audio);
      audio.addEventListener('error', () => {
        failed = true;
        for (const field of fields) field.disabled = true;
        reveal.disabled = true;
        status.textContent = `${names[index]} could not load. A blind comparison needs both clips.`;
      });
      audio.addEventListener('playing', () => {
        heard.add(audio);
        if (heard.size === 2 && !failed && !revealed) {
          for (const field of fields) field.disabled = false;
          reveal.disabled = false;
          status.textContent = 'Choose your preferences or reveal the voices.';
        }
      });
      audio.addEventListener('play', () => players.forEach((other) => {
        if (other !== audio) other.pause();
      }));
      return audio;
    });
    panel.hidden = false;
    start.hidden = true;
    players[0].focus();
  }, { once: true });

  const preference = (name) => {
    const selected = round.querySelector(`input[name="${name}"]:checked`)?.value;
    return selected === 'a' ? names[0] : selected === 'b' ? names[1] :
      selected === 'tie' ? 'no preference' : 'no choice made';
  };

  reveal.addEventListener('click', () => {
    revealed = true;
    for (const [i, template] of templates.entries()) {
      const row = node('li', `${names[i]}: ${template.dataset.name} · `, results);
      node('a', 'Playback rights and attribution', row).href = template.dataset.rights;
    }
    status.textContent = `Your local choices: naturalness — ${preference('natural')}; dialect authenticity — ${preference('dialect')}. Nothing was submitted.`;
    for (const field of fields) field.disabled = true;
    results.hidden = false;
    reveal.disabled = true;
    results.querySelector('a').focus();
  }, { once: true });
})();
