/**
 * MIRAI Site Carbon Navigator - Frontend Application
 * CO2 emission calculation system for construction sites
 */

'use strict';

const API_BASE = '';

// ===== Category labels =====
const CATEGORY_LABELS = {
  fuel: '燃料',
  power: '電力',
  material: '材料',
  transport: '輸送',
};

// Only these keys are valid CSS class suffixes — used to prevent class injection
const VALID_CATEGORIES = new Set(['fuel', 'power', 'material', 'transport']);

const CATEGORY_COLORS = {
  fuel: '#e67e22',
  power: '#f1c40f',
  material: '#7f8c8d',
  transport: '#2980b9',
};

// ===== State =====
let currentProjectId = null;
let currentPage = 'projects';
let charts = {};

// ===== API Helper =====
async function fetchJSON(url, options = {}) {
  const defaults = { headers: { 'Content-Type': 'application/json' } };
  const config = Object.assign({}, defaults, options);
  if (config.body && typeof config.body === 'object') {
    config.body = JSON.stringify(config.body);
  }
  const res = await fetch(API_BASE + url, config);
  if (!res.ok) {
    let errMsg = `HTTP ${res.status}`;
    try {
      const errData = await res.json();
      errMsg = errData.detail || errData.message || errMsg;
    } catch (_) {}
    throw new Error(errMsg);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ===== Loading state =====
function showLoading() {
  document.getElementById('loadingOverlay').classList.add('show');
}

function hideLoading() {
  document.getElementById('loadingOverlay').classList.remove('show');
}

// ===== Toast notifications (DOM-only, no innerHTML) =====
function showToast(message, type = 'success') {
  const container = document.getElementById('toastContainer');
  const iconMap = { success: '✅', danger: '❌', warning: '⚠️', info: 'ℹ️' };
  const icon = iconMap[type] || 'ℹ️';

  // Build structure with DOM methods — no innerHTML
  const toastEl = document.createElement('div');
  toastEl.className = `toast align-items-center text-bg-${sanitizeType(type)} border-0`;
  toastEl.setAttribute('role', 'alert');
  toastEl.setAttribute('aria-live', 'assertive');

  const dFlex = document.createElement('div');
  dFlex.className = 'd-flex';

  const body = document.createElement('div');
  body.className = 'toast-body';
  body.textContent = `${icon} ${message}`; // textContent — safe

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'btn-close btn-close-white me-2 m-auto';
  btn.setAttribute('data-bs-dismiss', 'toast');
  btn.setAttribute('aria-label', '閉じる');

  dFlex.appendChild(body);
  dFlex.appendChild(btn);
  toastEl.appendChild(dFlex);
  container.appendChild(toastEl);

  const toast = new bootstrap.Toast(toastEl, { delay: 4000 });
  toast.show();
  toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
}

// Prevent class injection in toast type
function sanitizeType(type) {
  const allowed = new Set(['success', 'danger', 'warning', 'info', 'secondary']);
  return allowed.has(type) ? type : 'secondary';
}

// ===== DOM helpers =====

/** Create a text node wrapped in a td */
function td(text, className) {
  const cell = document.createElement('td');
  if (className) cell.className = className;
  cell.textContent = text ?? '';
  return cell;
}

/** Create a category badge <span> — uses allowlisted CSS class */
function makeCategoryBadge(cat) {
  const span = document.createElement('span');
  span.className = 'category-badge' + (VALID_CATEGORIES.has(cat) ? ` badge-${cat}` : '');
  span.textContent = CATEGORY_LABELS[cat] || cat;
  return span;
}

/** Create a Bootstrap badge <span> */
function makeBadge(text, bgClass) {
  const span = document.createElement('span');
  span.className = `badge ${sanitizeBgClass(bgClass)}`;
  span.textContent = text;
  return span;
}

function sanitizeBgClass(cls) {
  const allowed = new Set(['bg-success', 'bg-secondary', 'bg-danger', 'bg-warning', 'bg-info', 'bg-primary']);
  return allowed.has(cls) ? cls : 'bg-secondary';
}

/** Create a loading row that spans ncols columns */
function makeLoadingRow(ncols) {
  const tr = document.createElement('tr');
  const cell = document.createElement('td');
  cell.colSpan = ncols;
  cell.className = 'text-center py-3';

  const spinner = document.createElement('span');
  spinner.className = 'spinner-border spinner-border-sm me-2';
  spinner.setAttribute('aria-hidden', 'true');

  cell.appendChild(spinner);
  cell.appendChild(document.createTextNode('読み込み中...'));
  tr.appendChild(cell);
  return tr;
}

/** Create an error row */
function makeErrorRow(ncols, message) {
  const tr = document.createElement('tr');
  const cell = document.createElement('td');
  cell.colSpan = ncols;
  cell.className = 'text-center text-danger py-3';
  cell.textContent = `⚠️ ${message}`;
  tr.appendChild(cell);
  return tr;
}

/** Create an empty-state row */
function makeEmptyRow(ncols, icon, message) {
  const tr = document.createElement('tr');
  const cell = document.createElement('td');
  cell.colSpan = ncols;

  const wrapper = document.createElement('div');
  wrapper.className = 'empty-state';

  const iconDiv = document.createElement('div');
  iconDiv.className = 'empty-icon';
  iconDiv.textContent = icon;

  const msgDiv = document.createElement('div');
  msgDiv.textContent = message;

  wrapper.appendChild(iconDiv);
  wrapper.appendChild(msgDiv);
  cell.appendChild(wrapper);
  tr.appendChild(cell);
  return tr;
}

/** Replace all children of a tbody with a single row */
function setTbodyRow(tbody, row) {
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
  tbody.appendChild(row);
}

function formatNumber(n, decimals = 2) {
  if (n === null || n === undefined || isNaN(Number(n))) return '-';
  return Number(n).toLocaleString('ja-JP', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function destroyChart(key) {
  if (charts[key]) {
    charts[key].destroy();
    delete charts[key];
  }
}

// ===== Navigation =====
function navigateTo(page) {
  currentPage = page;
  document.querySelectorAll('.page-section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-link[data-page]').forEach(l => l.classList.remove('active'));

  const section = document.getElementById('section-' + page);
  if (section) section.classList.add('active');

  const link = document.querySelector(`.nav-link[data-page="${page}"]`);
  if (link) link.classList.add('active');

  switch (page) {
    case 'projects':    loadProjects(); break;
    case 'activities':  populateProjectSelects(); break;
    case 'calculation': populateProjectSelects(); break;
    case 'reports':     populateProjectSelects(); break;
  }
}

// ===== Projects =====
async function loadProjects() {
  const tbody = document.getElementById('projectsTableBody');
  setTbodyRow(tbody, makeLoadingRow(6));

  try {
    const projects = await fetchJSON('/api/projects');
    renderProjectsTable(projects);
  } catch (err) {
    setTbodyRow(tbody, makeErrorRow(6, err.message));
  }
}

function renderProjectsTable(projects) {
  const tbody = document.getElementById('projectsTableBody');
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);

  if (!projects || projects.length === 0) {
    tbody.appendChild(makeEmptyRow(6, '🏗️', '工事が登録されていません。「新規登録」から追加してください。'));
    return;
  }

  for (const p of projects) {
    const isSelected = currentProjectId === p.project_id;
    const tr = document.createElement('tr');
    tr.className = 'table-row-clickable' + (isSelected ? ' selected' : '');
    tr.dataset.projectId = p.project_id;

    const nameTd = document.createElement('td');
    const strong = document.createElement('strong');
    strong.textContent = p.name || p.project_id;
    nameTd.appendChild(strong);

    tr.appendChild(nameTd);
    tr.appendChild(td(p.branch || '-'));
    tr.appendChild(td(p.construction_type || '-'));
    tr.appendChild(td(p.start_date || '-'));
    tr.appendChild(td(p.end_date || '-'));

    const badgeTd = document.createElement('td');
    badgeTd.appendChild(makeBadge(isSelected ? '選択中' : '選択', isSelected ? 'bg-success' : 'bg-secondary'));
    tr.appendChild(badgeTd);

    // Use addEventListener — no onclick attribute avoids attribute-context injection
    tr.addEventListener('click', () => selectProject(p.project_id, p.name || p.project_id, tr));
    tbody.appendChild(tr);
  }
}

function selectProject(projectId, projectName, rowEl) {
  currentProjectId = projectId;
  document.querySelectorAll('#projectsTableBody tr').forEach(r => {
    r.classList.remove('selected');
    const badge = r.querySelector('.badge');
    if (badge) { badge.className = 'badge bg-secondary'; badge.textContent = '選択'; }
  });
  rowEl.classList.add('selected');
  const badge = rowEl.querySelector('.badge');
  if (badge) { badge.className = 'badge bg-success'; badge.textContent = '選択中'; }

  showToast(`工事「${projectName}」を選択しました`, 'success');
}

async function createProject(data) {
  return fetchJSON('/api/projects', { method: 'POST', body: data });
}

function openNewProjectModal() {
  document.getElementById('projectForm').reset();
  const modal = new bootstrap.Modal(document.getElementById('projectModal'));
  modal.show();
}

async function submitProjectForm() {
  const form = document.getElementById('projectForm');
  if (!form.checkValidity()) { form.reportValidity(); return; }

  const data = {
    project_id: document.getElementById('fProjectId').value.trim(),
    name: document.getElementById('fProjectName').value.trim(),
    branch: document.getElementById('fBranch').value.trim(),
    construction_type: document.getElementById('fConstructionType').value.trim(),
    start_date: document.getElementById('fStartDate').value || null,
    end_date: document.getElementById('fEndDate').value || null,
    notes: document.getElementById('fNotes').value.trim(),
  };

  showLoading();
  try {
    await createProject(data);
    bootstrap.Modal.getInstance(document.getElementById('projectModal')).hide();
    showToast('工事を登録しました', 'success');
    loadProjects();
  } catch (err) {
    showToast(`登録失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

// ===== Project Select Populate (DOM-only) =====
async function populateProjectSelects() {
  const selects = document.querySelectorAll('.project-select');
  if (!selects.length) return;

  try {
    const projects = await fetchJSON('/api/projects');
    selects.forEach(sel => {
      const current = sel.value;
      while (sel.firstChild) sel.removeChild(sel.firstChild);

      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = '-- 工事を選択 --';
      sel.appendChild(placeholder);

      for (const p of (projects || [])) {
        const opt = document.createElement('option');
        opt.value = p.project_id;           // assigned as property — no attribute injection
        opt.textContent = p.name || p.project_id;
        if (current === p.project_id) opt.selected = true;
        sel.appendChild(opt);
      }

      if (currentProjectId) sel.value = currentProjectId;
    });
  } catch (err) {
    console.warn('Project select populate failed:', err.message);
  }
}

// ===== Activities =====
async function loadActivities(projectId, month) {
  if (!projectId || !month) return;

  const tbody = document.getElementById('activitiesTableBody');
  setTbodyRow(tbody, makeLoadingRow(7));

  try {
    const params = new URLSearchParams({ project_id: projectId, target_month: month });
    const activities = await fetchJSON(`/api/activities?${params}`);
    renderActivitiesTable(activities);
  } catch (err) {
    setTbodyRow(tbody, makeErrorRow(7, err.message));
  }
}

function renderActivitiesTable(activities) {
  const tbody = document.getElementById('activitiesTableBody');
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);

  if (!activities || activities.length === 0) {
    tbody.appendChild(makeEmptyRow(7, '📋', '活動量データがありません。下のフォームから登録してください。'));
    return;
  }

  for (const a of activities) {
    const tr = document.createElement('tr');
    if (a.approved) tr.classList.add('approved-row');

    // Category badge cell
    const catTd = document.createElement('td');
    catTd.appendChild(makeCategoryBadge(a.category));
    tr.appendChild(catTd);

    tr.appendChild(td(a.item_name));
    tr.appendChild(td(formatNumber(a.quantity, 3), 'text-end'));
    tr.appendChild(td(a.unit));
    tr.appendChild(td(a.source_file || '-'));

    // Approve checkbox cell
    const chkTd = document.createElement('td');
    chkTd.className = 'text-center';
    const chk = document.createElement('input');
    chk.type = 'checkbox';
    chk.className = 'form-check-input approve-checkbox';
    chk.dataset.id = a.activity_id || a.id;
    chk.checked = !!a.approved;
    chk.addEventListener('change', () => toggleApprove(chk));
    chkTd.appendChild(chk);
    tr.appendChild(chkTd);

    // Status badge cell
    const statusTd = document.createElement('td');
    statusTd.className = 'text-center';
    statusTd.appendChild(makeBadge(a.approved ? '承認済' : '未承認', a.approved ? 'bg-success' : 'bg-secondary'));
    tr.appendChild(statusTd);

    tbody.appendChild(tr);
  }
}

async function createActivity(data) {
  return fetchJSON('/api/activities', { method: 'POST', body: data });
}

async function approveActivity(activityId) {
  return fetchJSON(`/api/activities/${activityId}/approve`, { method: 'PUT' });
}

async function toggleApprove(checkbox) {
  const activityId = checkbox.dataset.id;
  const row = checkbox.closest('tr');

  try {
    await approveActivity(activityId);
    // Update status badge — DOM only
    const statusTd = row.querySelector('td:last-child');
    if (statusTd) {
      while (statusTd.firstChild) statusTd.removeChild(statusTd.firstChild);
      statusTd.appendChild(makeBadge(
        checkbox.checked ? '承認済' : '未承認',
        checkbox.checked ? 'bg-success' : 'bg-secondary'
      ));
    }
    row.classList.toggle('approved-row', checkbox.checked);
    showToast(checkbox.checked ? '承認しました' : '承認を取消しました', 'success');
  } catch (err) {
    checkbox.checked = !checkbox.checked; // revert
    showToast(`承認操作に失敗しました: ${err.message}`, 'danger');
  }
}

async function bulkApprove() {
  const unchecked = document.querySelectorAll('.approve-checkbox:not(:checked)');
  if (!unchecked.length) { showToast('未承認のデータはありません', 'info'); return; }

  showLoading();
  let success = 0;
  let failed = 0;

  for (const cb of unchecked) {
    try {
      await approveActivity(cb.dataset.id);
      cb.checked = true;
      const row = cb.closest('tr');
      if (row) {
        row.classList.add('approved-row');
        const statusTd = row.querySelector('td:last-child');
        if (statusTd) {
          while (statusTd.firstChild) statusTd.removeChild(statusTd.firstChild);
          statusTd.appendChild(makeBadge('承認済', 'bg-success'));
        }
      }
      success++;
    } catch (_) {
      failed++;
    }
  }

  hideLoading();
  showToast(
    `一括承認完了: 成功 ${success}件${failed ? ` / 失敗 ${failed}件` : ''}`,
    failed ? 'warning' : 'success'
  );
}

async function submitActivityForm() {
  const form = document.getElementById('activityForm');
  if (!form.checkValidity()) { form.reportValidity(); return; }

  const projectId = document.getElementById('actProjectSelect').value;
  const month = document.getElementById('actMonthPicker').value;
  if (!projectId) { showToast('工事を選択してください', 'warning'); return; }
  if (!month) { showToast('対象月を選択してください', 'warning'); return; }

  const data = {
    project_id: projectId,
    target_month: month,
    category: document.getElementById('fCategory').value,
    item_name: document.getElementById('fItemName').value.trim(),
    quantity: parseFloat(document.getElementById('fQuantity').value),
    unit: document.getElementById('fUnit').value.trim(),
    source_file: document.getElementById('fSourceFile').value.trim() || null,
  };

  showLoading();
  try {
    await createActivity(data);
    form.reset();
    document.getElementById('actProjectSelect').value = projectId;
    document.getElementById('actMonthPicker').value = month;
    showToast('活動量を登録しました', 'success');
    loadActivities(projectId, month);
  } catch (err) {
    showToast(`登録失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

function onActivityFilterChange() {
  const projectId = document.getElementById('actProjectSelect').value;
  const month = document.getElementById('actMonthPicker').value;
  if (projectId && month) loadActivities(projectId, month);
}

// ===== Emissions Calculation =====
async function runCalculation(projectId, month) {
  return fetchJSON('/api/emissions/calculate', {
    method: 'POST',
    body: { project_id: projectId, target_month: month },
  });
}

async function loadEmissionSummary(projectId, month) {
  const params = new URLSearchParams({ project_id: projectId, target_month: month });
  return fetchJSON(`/api/emissions/summary?${params}`);
}

async function loadReductionSuggestions(projectId, month) {
  return fetchJSON(`/api/emissions/reduction/${encodeURIComponent(projectId)}/${encodeURIComponent(month)}`);
}

async function executeCalculation() {
  const projectId = document.getElementById('calcProjectSelect').value;
  const month = document.getElementById('calcMonthPicker').value;
  if (!projectId) { showToast('工事を選択してください', 'warning'); return; }
  if (!month) { showToast('対象月を選択してください', 'warning'); return; }

  showLoading();
  try {
    const result = await runCalculation(projectId, month);
    showToast('算定を実行しました', 'success');

    let summary = null;
    try {
      summary = await loadEmissionSummary(projectId, month);
    } catch (_) {
      summary = result;
    }

    renderCalculationResults(result, summary);
    renderEmissionChart(summary);

    try {
      const suggestions = await loadReductionSuggestions(projectId, month);
      renderReductionSuggestions(suggestions);
    } catch (_) {
      const el = document.getElementById('reductionList');
      while (el.firstChild) el.removeChild(el.firstChild);
      const p = document.createElement('p');
      p.className = 'text-muted small';
      p.textContent = '削減ナビ情報を取得できませんでした。';
      el.appendChild(p);
    }
  } catch (err) {
    showToast(`算定失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

function renderCalculationResults(result, summary) {
  document.getElementById('calcResultsSection').style.display = 'block';

  const tbody = document.getElementById('calcTableBody');
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);

  const items = Array.isArray(result) ? result : (result.items || result.details || []);

  if (!items.length) {
    setTbodyRow(tbody, (() => {
      const tr = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 7;
      cell.className = 'text-center text-muted py-3';
      cell.textContent = '算定結果データがありません';
      tr.appendChild(cell);
      return tr;
    })());
  } else {
    for (const item of items) {
      const co2kg = item.co2_kg ?? item.emissions_kg ?? item.co2_emission ?? 0;
      const co2t  = item.co2_t ?? item.emissions_t ?? (co2kg / 1000);

      const tr = document.createElement('tr');

      const catTd = document.createElement('td');
      catTd.appendChild(makeCategoryBadge(item.category));
      tr.appendChild(catTd);

      tr.appendChild(td(item.item_name || item.name || '-'));
      tr.appendChild(td(formatNumber(item.quantity, 3), 'text-end'));
      tr.appendChild(td(item.unit || '-'));
      tr.appendChild(td(formatNumber(item.emission_factor ?? item.factor, 4), 'text-end'));

      const kgTd = td(formatNumber(co2kg), 'text-end co2-value');
      const tTd  = td(formatNumber(co2t, 4), 'text-end co2-value');
      tr.appendChild(kgTd);
      tr.appendChild(tTd);

      tbody.appendChild(tr);
    }
  }

  const totals = extractTotals(summary || result);
  document.getElementById('statTotal').textContent     = formatNumber(totals.total_t, 3);
  document.getElementById('statFuel').textContent      = formatNumber(totals.fuel_t, 3);
  document.getElementById('statPower').textContent     = formatNumber(totals.power_t, 3);
  document.getElementById('statMaterial').textContent  = formatNumber(totals.material_t, 3);
  document.getElementById('statTransport').textContent = formatNumber(totals.transport_t, 3);
}

function extractTotals(data) {
  const r = { total_t: 0, fuel_t: 0, power_t: 0, material_t: 0, transport_t: 0 };
  if (!data) return r;

  r.total_t     = data.total_co2_t     ?? data.total_t     ?? data.total     ?? 0;
  r.fuel_t      = data.fuel_co2_t      ?? data.fuel_t      ?? data.fuel      ?? 0;
  r.power_t     = data.power_co2_t     ?? data.power_t     ?? data.power     ?? 0;
  r.material_t  = data.material_co2_t  ?? data.material_t  ?? data.material  ?? 0;
  r.transport_t = data.transport_co2_t ?? data.transport_t ?? data.transport ?? 0;

  if (data.by_category) {
    const bc = data.by_category;
    r.fuel_t      = bc.fuel?.co2_t      ?? bc.fuel      ?? r.fuel_t;
    r.power_t     = bc.power?.co2_t     ?? bc.power     ?? r.power_t;
    r.material_t  = bc.material?.co2_t  ?? bc.material  ?? r.material_t;
    r.transport_t = bc.transport?.co2_t ?? bc.transport ?? r.transport_t;
  }

  if (!r.total_t) r.total_t = r.fuel_t + r.power_t + r.material_t + r.transport_t;
  return r;
}

function renderEmissionChart(data) {
  destroyChart('emission');
  const ctx = document.getElementById('emissionChart').getContext('2d');
  const totals = extractTotals(data);

  charts['emission'] = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['燃料', '電力', '材料', '輸送'],
      datasets: [{
        data: [totals.fuel_t, totals.power_t, totals.material_t, totals.transport_t],
        backgroundColor: [
          CATEGORY_COLORS.fuel,
          CATEGORY_COLORS.power,
          CATEGORY_COLORS.material,
          CATEGORY_COLORS.transport,
        ],
        borderWidth: 2,
        borderColor: '#fff',
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'right' },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.label}: ${formatNumber(ctx.raw, 3)} t-CO2`,
          },
        },
      },
    },
  });
}

function renderReductionSuggestions(data) {
  const container = document.getElementById('reductionList');
  while (container.firstChild) container.removeChild(container.firstChild);

  const suggestions = Array.isArray(data) ? data : (data.suggestions || data.items || []);

  if (!suggestions.length) {
    const p = document.createElement('p');
    p.className = 'text-muted small';
    p.textContent = '削減提案データがありません。';
    container.appendChild(p);
    return;
  }

  for (const s of suggestions) {
    const div = document.createElement('div');
    div.className = 'reduction-item';

    if (s.category) {
      const strong = document.createElement('strong');
      // Use allowlisted label, fall back to empty string if unknown
      strong.textContent = CATEGORY_LABELS[s.category] || '';
      div.appendChild(strong);
      div.appendChild(document.createTextNode(' — '));
    }

    const text = s.suggestion || s.message || s.text || '';
    div.appendChild(document.createTextNode(text));

    container.appendChild(div);
  }
}

// ===== Reports =====
function downloadReport(projectId, month) {
  if (!projectId) { showToast('工事を選択してください', 'warning'); return; }
  if (!month) { showToast('対象月を選択してください', 'warning'); return; }
  window.location.href = `${API_BASE}/api/reports/monthly/${encodeURIComponent(projectId)}/${encodeURIComponent(month)}`;
}

async function loadMonthlyTrend() {
  const projectId = document.getElementById('rptProjectSelect').value;
  if (!projectId) { showToast('工事を選択してください', 'warning'); return; }

  showLoading();
  try {
    const params = new URLSearchParams({ project_id: projectId });
    const trend = await fetchJSON(`/api/emissions/trend?${params}`);
    renderTrendChart(trend);
  } catch (err) {
    showToast(`トレンドデータ取得失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

function renderTrendChart(data) {
  destroyChart('trend');
  const ctx = document.getElementById('trendChart').getContext('2d');

  const months = Array.isArray(data) ? data : (data.months || data.data || []);
  const labels = months.map(m => m.month || m.target_month || '');
  const values = months.map(m => m.total_t ?? m.co2_t ?? m.total ?? 0);

  charts['trend'] = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'CO2排出量 (t-CO2)',
        data: values,
        borderColor: '#2d7d46',
        backgroundColor: 'rgba(45,125,70,0.1)',
        fill: true,
        tension: 0.3,
        pointBackgroundColor: '#2d7d46',
        pointRadius: 5,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ` ${formatNumber(ctx.raw, 3)} t-CO2`,
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          title: { display: true, text: 't-CO2' },
        },
        x: {
          title: { display: true, text: '対象月' },
        },
      },
    },
  });
}

function onReportFilterChange() {
  const projectId = document.getElementById('rptProjectSelect').value;
  if (projectId) loadMonthlyTrend();
}

function downloadCurrentReport() {
  downloadReport(
    document.getElementById('rptProjectSelect').value,
    document.getElementById('rptMonthPicker').value
  );
}

// ===== Init =====
document.addEventListener('DOMContentLoaded', () => {
  const now = new Date();
  const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  ['actMonthPicker', 'calcMonthPicker', 'rptMonthPicker'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = currentMonth;
  });

  document.querySelectorAll('.nav-link[data-page]').forEach(link => {
    link.addEventListener('click', e => {
      e.preventDefault();
      navigateTo(link.dataset.page);
    });
  });

  navigateTo('projects');
});
