(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const repository = 'jyoutir/blasbench';
  const revision = $('blasbench').dataset.revision;
  const release = `https://raw.githubusercontent.com/${repository}/${revision}`;
  const evidence = `https://github.com/${repository}/tree/${revision}`;
  const load = $('load-blasbench');
  const status = $('blasbench-status');
  const results = $('blasbench-results');
  const tbody = $('blasbench-rows');
  const dataset = $('blasbench-dataset');
  const metric = $('blasbench-metric');
  const publishedDatasets = { 'cv-corpus-25.0-ga-IE': 'commonvoice-ga', 'google/fleurs': 'fleurs-ga' };
  let entries = [];

  async function read(path) {
    const response = await fetch(`${release}/${path}`, { credentials: 'omit', referrerPolicy: 'no-referrer' });
    if (!response.ok) throw new Error('Published artifact unavailable');
    return response;
  }

  function parse(csv) {
    // The pinned v0.1.0 artifact is plain comma-delimited scalar data.
    const [header, ...lines] = csv.trim().split(/\r?\n/);
    const columns = header.split(',');
    const required = ['run_id', 'model', 'dataset', 'split', 'normalizer', 'wer', 'cer', 'num_utterances'];
    if (!required.every((field) => columns.includes(field))) throw new Error('Unexpected artifact format');
    return lines.map((line) => {
      const values = line.split(',');
      if (values.length !== columns.length) throw new Error('Unexpected artifact row');
      const row = Object.fromEntries(columns.map((field, i) => [field, values[i]]));
      const stamp = /^\d{8}_\d{6}/.exec(row.run_id);
      if (!stamp || !/^[\w.-]+\/[\w.-]+$/.test(row.model) || !Object.hasOwn(publishedDatasets, row.dataset) ||
          row.split !== 'test' || row.normalizer !== 'irish' ||
          !['wer', 'cer', 'num_utterances'].every((key) => /^\d+(\.\d+)?$/.test(row[key]))) {
        throw new Error('Unexpected experiment row');
      }
      return {
        ...row,
        path: `experiments/${stamp[0]}_${row.model.replace('/', '_')}_${publishedDatasets[row.dataset]}`,
      };
    });
  }

  function add(parent, tag, text) {
    const element = document.createElement(tag);
    element.textContent = text;
    parent.append(element);
    return element;
  }

  function draw() {
    const rows = entries.filter((entry) => entry.dataset === dataset.value);
    rows.sort((a, b) => a[metric.value] - b[metric.value] || a.model.localeCompare(b.model));
    tbody.replaceChildren();
    for (const entry of rows) {
      const row = tbody.insertRow();
      add(row, 'th', entry.model).scope = 'row';
      add(row, 'td', `${entry.wer}%`);
      add(row, 'td', `${entry.cer}%`);
      add(row, 'td', entry.num_utterances);
      const details = row.insertCell().appendChild(document.createElement('details'));
      add(details, 'summary', 'Run details');
      const info = add(details, 'p', '');
      info.className = 'lab-note';
      info.setAttribute('role', 'status');
      add(details, 'a', 'Experiment files').href = `${evidence}/${entry.path}`;
      details.addEventListener('toggle', async () => {
        if (!details.open || info.textContent) return;
        info.textContent = 'Loading intervals…';
        try {
          const { model, overall } = await (await read(`${entry.path}/results.json`)).json();
          if (model !== entry.model || Number(entry.wer) !== overall.wer || Number(entry.cer) !== overall.cer) {
            throw new Error('Result does not match the release summary');
          }
          const intervals = ['wer', 'cer'].flatMap((name) => {
            const lo = overall[`${name}_ci95_lo`];
            const hi = overall[`${name}_ci95_hi`];
            return Number.isFinite(lo) && Number.isFinite(hi) ? [`${name.toUpperCase()} ${lo}–${hi}%`] : [];
          });
          info.textContent = intervals.length ? `95% intervals: ${intervals.join('; ')}.` : 'No intervals in this run artifact.';
        } catch {
          info.textContent = 'Could not load intervals. See the linked experiment files.';
        }
      });
    }
    status.textContent = `${rows.length} published ${rows.length === 1 ? 'run' : 'runs'} on ${dataset.selectedOptions[0].textContent}, sorted by ${metric.value.toUpperCase()}.`;
  }

  load.hidden = false;
  dataset.addEventListener('change', draw);
  metric.addEventListener('change', draw);
  load.addEventListener('click', async () => {
    load.disabled = true;
    status.textContent = 'Loading the pinned BlasBench release…';
    try {
      entries = parse(await (await read('results/summary.csv')).text());
      if (!entries.length) throw new Error('No published runs');
      draw();
      results.hidden = false;
      load.hidden = true;
      dataset.focus();
    } catch {
      status.textContent = 'Could not load the published results. The release CSV is linked above.';
      load.disabled = false;
    }
  });
})();
