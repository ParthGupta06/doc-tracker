'use strict';

const $ = (id) => document.getElementById(id);
const origin = window.location.origin;

function openTool(name, focus = false) {
  for (const tab of document.querySelectorAll('[data-tab]')) {
    const selected = tab.dataset.tab === name;
    tab.classList.toggle('selected', selected);
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
    $(`panel-${tab.dataset.tab}`).hidden = !selected;
    if (selected && focus) tab.focus();
  }
}
for (const tab of document.querySelectorAll('[data-tab]')) {
  tab.addEventListener('click', () => openTool(tab.dataset.tab));
  tab.addEventListener('keydown', (event) => {
    const names = ['analyze', 'tests', 'evidence'];
    let index = names.indexOf(tab.dataset.tab);
    if (event.key === 'ArrowRight') index = (index + 1) % names.length;
    else if (event.key === 'ArrowLeft') index = (index + names.length - 1) % names.length;
    else if (event.key === 'Home') index = 0;
    else if (event.key === 'End') index = names.length - 1;
    else return;
    event.preventDefault();
    openTool(names[index], true);
  });
}
for (const link of document.querySelectorAll('[data-open]')) {
  link.addEventListener('click', () => openTool(link.dataset.open));
}

function message(id, text, error = false) {
  const box = $(id);
  box.hidden = false;
  box.classList.toggle('error', error);
  box.textContent = text;
}

async function request(path, body, timeout = 120000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(path, {
      signal: controller.signal,
      cache: 'no-store',
      headers: body ? { 'Content-Type': 'application/json' } : {},
      method: body ? 'POST' : 'GET',
      body: body ? JSON.stringify(body) : undefined,
    });
    const text = await response.text();
    let data;
    try { data = JSON.parse(text); }
    catch { throw new Error(`HTTP ${response.status}: the service returned a non-JSON response. It may be waking up; retry in a minute.`); }
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${data.message || data.error?.message || data.detail || 'Request failed'}`);
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The request timed out. The operation may still be running. For tests, use the session ID below to retrieve the report.');
    throw error;
  } finally { clearTimeout(timer); }
}

async function checkHealth() {
  try {
    const info = await request('/system/health', null, 90000);
    if (info.status !== 'ok') throw new Error('Health endpoint did not report ok');
    $('system-status').textContent = 'Operational';
    $('health-dot').className = 'status-dot';
    $('system-note').textContent = 'Live health check · system API reachable';
    $('version').textContent = `v${info.tool_version}`;
    $('mapping').textContent = `Configuration · ${info.config_version}`;
    $('storage-notice').replaceChildren();
    const title = document.createElement('strong');
    title.textContent = 'Save your evidence. ';
    $('storage-notice').append(title, info.storage === 'local'
      ? 'Active storage is local and temporary. Analyses and sessions can disappear on sleep, restart, or redeploy. Download reports you need to keep.'
      : `Active evidence backend: ${info.storage}. Test sessions still reset when the service restarts.`);
  } catch (error) {
    $('system-status').textContent = 'Not reachable';
    $('health-dot').className = 'status-dot offline';
    $('system-note').textContent = 'May be waking up. Refresh in about a minute.';
    $('storage-notice').textContent = 'Storage status unavailable. Download any returned evidence; hosted local storage is temporary.';
  }
  try {
    const tester = await request('/tester/health', null, 90000);
    $('test-count').textContent = tester.tests ?? '—';
  } catch { $('test-count').textContent = 'Unavailable'; }
}

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function download(data, filename) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2) + '\n'], { type: 'application/json' }));
  const link = element('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

function resultHeader(container, title, subtitle, data, filename) {
  container.replaceChildren();
  container.hidden = false;
  const header = element('div', undefined, 'result-header');
  const description = element('div');
  description.append(element('h3', title), element('p', subtitle, 'result-id mono'));
  const save = element('button', 'Download JSON ↓', 'button secondary');
  save.type = 'button';
  save.addEventListener('click', () => download(data, filename));
  header.append(description, save);
  container.append(header);
}

function table(container, headers, rows) {
  const wrap = element('div', undefined, 'table-wrap');
  const node = element('table');
  const head = element('thead');
  const labels = element('tr');
  for (const text of headers) {
    const cell = element('th', text);
    cell.scope = 'col';
    labels.append(cell);
  }
  head.append(labels);
  const body = element('tbody');
  for (const row of rows) {
    const tr = element('tr');
    for (const value of row) {
      const td = element('td');
      if (value instanceof Node) td.append(value);
      else td.textContent = value ?? '—';
      tr.append(td);
    }
    body.append(tr);
  }
  node.append(head, body);
  wrap.append(node);
  container.append(wrap);
}

function rawDetails(container, data) {
  const details = element('details');
  details.append(element('summary', 'View full JSON response'), element('pre', JSON.stringify(data, null, 2)));
  container.append(details);
}

function renderAnalysis(id, data) {
  const container = $(id);
  resultHeader(container, data.status === 'SUCCESS' ? 'Analysis saved' : 'Analysis saved with an error',
    `${data.analysis_id} · ${data.repository}`, data, `${data.analysis_id}.json`);
  const summary = element('div', undefined, 'result-summary');
  for (const [key, label] of [['changes', 'changed files'], ['issues', 'findings'], ['unmapped', 'unmapped'], ['skipped', 'unsupported files']]) {
    summary.append(element('span', `${(data[key] || []).length} ${label}`, 'result-stat'));
  }
  container.append(summary);
  if (data.error) container.append(element('p', `${data.error.code}: ${data.error.message}`, 'message error'));
  if (data.issues?.length) {
    table(container, ['FINDING', 'SOURCE → DOCUMENTATION', 'EXPLANATION'], data.issues.map((issue) => {
      const type = element('div', issue.issue_type.replaceAll('_', ' '));
      type.append(element('small', issue.verification_status));
      const paths = element('div', issue.code_file, 'mono');
      paths.append(element('small', `→ ${issue.documentation_file}`));
      return [type, paths, issue.explanation];
    }));
  } else if (data.status === 'SUCCESS') {
    container.append(element('p', 'No findings under the active mappings and supported checks. This does not prove documentation is complete or correct.', 'empty-state'));
  }
  if (data.changes?.length) table(container, ['CHANGED FILE', 'CHANGE', 'CATEGORY'], data.changes.map((change) => [change.path, change.change_type, change.category]));
  rawDetails(container, data);
  $('analysis-id').value = data.analysis_id;
}

function renderReport(data) {
  if (!Array.isArray(data.results) || !data.coverage || !data.session_id) throw new Error('The tester returned an incomplete report. Retrieve the report again using the session ID.');
  const container = $('test-result');
  resultHeader(container, 'Test run report', `${data.session_id} · ${data.target_url}`, data, `test-report-${data.session_id}.json`);
  const counts = { pass: 0, fail: 0, error: 0, skip: 0 };
  for (const result of data.results) if (result.outcome in counts) counts[result.outcome]++;
  const summary = element('div', undefined, 'result-summary');
  for (const [outcome, count] of Object.entries(counts)) summary.append(element('span', `${count} ${outcome}`, `result-stat ${outcome}`));
  container.append(summary);
  table(container, ['COVERAGE', 'COVERED / TOTAL', 'BASIS'], ['code', 'component', 'system'].map((key) => {
    const item = data.coverage[key];
    return [key === 'system' ? 'System-model / AC' : key, item?.covered == null ? 'Unavailable' : `${item.covered} / ${item.total}`, item?.basis || 'Not reported'];
  }));
  table(container, ['TEST', 'OUTCOME', 'DETAIL'], data.results.map((item) => [item.test_id, element('span', item.outcome.toUpperCase(), `outcome ${item.outcome}`), `${item.source ? `[${item.source}] ` : ''}${item.message}`]));
  rawDetails(container, data);
}

$('load-example').addEventListener('click', () => {
  $('repository').value = 'ParthGupta06/doc-tracker-fixtures';
  $('commit').value = 'add930c827b4f242d173fe6d26ebc068c8dd65fb';
  $('base-commit').value = '';
  $('commit').focus();
});

$('analyze-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  $('analysis-result').hidden = true;
  message('analyze-message', 'Reading the repository and comparing versions. Large repositories can take longer…');
  try {
    const body = { repository: $('repository').value.trim(), commit_id: $('commit').value.trim() };
    if ($('base-commit').value.trim()) body.base_commit = $('base-commit').value.trim();
    const data = await request('/system/analyze', body, 180000);
    renderAnalysis('analysis-result', data);
    message('analyze-message', data.status === 'SUCCESS' ? 'Analysis complete. Download the JSON to keep a copy of your evidence.' : 'The analysis recorded an error. See its saved details below.', data.status !== 'SUCCESS');
  } catch (error) { message('analyze-message', error.message, true); }
  finally { button.disabled = false; }
});

$('evidence-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  $('evidence-result').hidden = true;
  message('evidence-message', 'Retrieving the saved analysis…');
  try {
    const data = await request(`/system/analysis/${encodeURIComponent($('analysis-id').value.trim())}`);
    renderAnalysis('evidence-result', data);
    message('evidence-message', 'Saved evidence retrieved.');
  } catch (error) { message('evidence-message', `${error.message} If the service restarted, local evidence may no longer exist.`, true); }
  finally { button.disabled = false; }
});

$('test-ours').addEventListener('click', () => { $('target-url').value = `${origin}/system`; });

let running = false;
$('test-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (running) return;
  const target = $('target-url').value.trim().replace(/\/+$/, '');
  const parsed = new URL(target);
  if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password || parsed.search || parsed.hash || /\/(docs|openapi\.json|test)$/.test(parsed.pathname)) {
    message('test-message', 'Use an http(s) system base URL without credentials, query parameters, or a /docs, /openapi.json, or /test suffix.', true);
    return;
  }
  running = true;
  const button = event.submitter;
  button.disabled = true;
  $('retrieve-report').disabled = true;
  $('test-result').hidden = true;
  message('test-message', 'Setting up the target system. A sleeping target may take about a minute to wake…');
  let timer;
  let session;
  try {
    const setup = await request('/tester/test/setup', { target_url: target }, 125000);
    session = setup.session_id;
    if (!session) throw new Error('Setup returned no session ID. Please retry.');
    $('session-id').value = session;
    const started = Date.now();
    const progress = () => message('test-message', `Suite running · ${Math.floor((Date.now() - started) / 1000)}s elapsed. Session ${session}. Keep this page open; this may take up to 10 minutes.`);
    progress();
    timer = setInterval(progress, 15000);
    let data;
    try { data = await request('/tester/test/run', { session_id: session }, 620000); }
    catch (runError) {
      clearInterval(timer);
      try { data = await request(`/tester/test/report?session_id=${encodeURIComponent(session)}`); }
      catch { throw runError; }
    }
    clearInterval(timer);
    renderReport(data);
    message('test-message', 'Report received. Review every outcome and download the JSON for your submission.');
  } catch (error) { message('test-message', `${error.message}${session ? ` Session: ${session}. Use Retrieve report below to check for saved results.` : ''}`, true); }
  finally {
    clearInterval(timer);
    running = false;
    button.disabled = false;
    $('retrieve-report').disabled = false;
  }
});

$('retrieve-report').addEventListener('click', async () => {
  const session = $('session-id').value.trim();
  if (!session) { message('test-message', 'Enter a tester session ID first.', true); return; }
  $('retrieve-report').disabled = true;
  $('test-result').hidden = true;
  message('test-message', 'Looking up the report…');
  try {
    renderReport(await request(`/tester/test/report?session_id=${encodeURIComponent(session)}`));
    message('test-message', 'Report retrieved. Download the JSON to preserve it.');
  } catch (error) { message('test-message', error.message, true); }
  finally { $('retrieve-report').disabled = false; }
});

for (const type of ['system', 'tester']) $(`${type}-url`).textContent = `${origin}/${type}`;
for (const button of document.querySelectorAll('[data-copy]')) {
  button.addEventListener('click', async () => {
    const text = `${origin}/${button.dataset.copy}`;
    try {
      await navigator.clipboard.writeText(text);
      $('copy-message').textContent = `${button.dataset.copy === 'system' ? 'System' : 'Tester'} base URL copied.`;
    } catch { $('copy-message').textContent = `Copy this base URL: ${text}`; }
  });
}
checkHealth();
