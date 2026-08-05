/**
 * MIRAI Site Carbon Navigator - Frontend Application
 * CO2 emission calculation system for construction sites
 */
'use strict';

const API_BASE = '';

const CATEGORY_LABELS = {
  fuel: '燃料',
  power: '電力',
  material: '材料',
  transport: '輸送',
  machine: '建機',
  ship: '船舶',
  waste: '廃棄物',
  water: '水',
  other: 'その他',
};

const VALID_CATEGORIES = new Set(Object.keys(CATEGORY_LABELS));

const CATEGORY_COLORS = {
  fuel: '#e67e22',
  power: '#f1c40f',
  material: '#7f8c8d',
  transport: '#2980b9',
  machine: '#8e44ad',
  ship: '#16a085',
  waste: '#c0392b',
  other: '#95a5a6',
};

const ROLE_LEVELS = { viewer: 0, site: 1, reviewer: 2, admin: 3 };
const ROLE_LABELS = { viewer: '閲覧', site: '現場入力', reviewer: 'レビュアー', admin: '管理者' };

let currentProjectId = null;
let currentPage = 'dashboard';
let charts = {};
let lastSuggestions = [];
let lastSuggestionProject = null;
let lastSuggestionMonth = null;

// ===== Auth state =====
function getAuth() {
  try {
    return JSON.parse(localStorage.getItem('mirai_auth') || 'null');
  } catch (_) {
    return null;
  }
}

function setAuth(auth) {
  if (auth) localStorage.setItem('mirai_auth', JSON.stringify(auth));
  else localStorage.removeItem('mirai_auth');
}

function hasRole(minRole) {
  const auth = getAuth();
  if (!auth) return false;
  return (ROLE_LEVELS[auth.user.role] ?? 0) >= (ROLE_LEVELS[minRole] ?? 0);
}

// ===== API Helper =====
async function fetchJSON(url, options = {}) {
  const defaults = { headers: { 'Content-Type': 'application/json' } };
  const auth = getAuth();
  if (auth && auth.token) defaults.headers['Authorization'] = `Bearer ${auth.token}`;
  const config = Object.assign({}, defaults, options);
  if (config.body && typeof config.body === 'object') {
    config.body = JSON.stringify(config.body);
  }
  const res = await fetch(API_BASE + url, config);
  if (res.status === 401) {
    forceLogout();
    throw new Error('認証が必要です。ログインしてください。');
  }
  if (!res.ok) {
    let errMsg = `HTTP ${res.status}`;
    try {
      const errData = await res.json();
      errMsg = errData.detail || errData.message || errMsg;
      if (Array.isArray(errData.detail)) {
        errMsg = errData.detail.map(d => d.msg || JSON.stringify(d)).join('; ');
      }
    } catch (_) {}
    throw new Error(errMsg);
  }
  if (res.status === 204) return null;
  return res.json();
}

async function downloadFile(url, filename) {
  const auth = getAuth();
  const res = await fetch(API_BASE + url, {
    headers: auth && auth.token ? { Authorization: `Bearer ${auth.token}` } : {},
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { msg = (await res.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}

// ===== Loading state =====
function showLoading() {
  document.getElementById('loadingOverlay').classList.add('show');
}

function hideLoading() {
  document.getElementById('loadingOverlay').classList.remove('show');
}

// ===== Toast notifications (DOM-only) =====
function showToast(message, type = 'success') {
  const container = document.getElementById('toastContainer');
  const iconMap = { success: '✅', danger: '❌', warning: '⚠️', info: 'ℹ️' };
  const icon = iconMap[type] || 'ℹ️';

  const toastEl = document.createElement('div');
  toastEl.className = `toast align-items-center text-bg-${sanitizeType(type)} border-0`;
  toastEl.setAttribute('role', 'alert');
  toastEl.setAttribute('aria-live', 'assertive');

  const dFlex = document.createElement('div');
  dFlex.className = 'd-flex';

  const body = document.createElement('div');
  body.className = 'toast-body';
  body.textContent = `${icon} ${message}`;

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

function sanitizeType(type) {
  const allowed = new Set(['success', 'danger', 'warning', 'info', 'secondary']);
  return allowed.has(type) ? type : 'secondary';
}

// ===== DOM helpers =====
function td(text, className) {
  const cell = document.createElement('td');
  if (className) cell.className = className;
  cell.textContent = text ?? '';
  return cell;
}

function makeCategoryBadge(cat) {
  const span = document.createElement('span');
  span.className = 'category-badge' + (VALID_CATEGORIES.has(cat) ? ` badge-${cat}` : '');
  span.textContent = CATEGORY_LABELS[cat] || cat;
  return span;
}

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

function makeErrorRow(ncols, message) {
  const tr = document.createElement('tr');
  const cell = document.createElement('td');
  cell.colSpan = ncols;
  cell.className = 'text-center text-danger py-3';
  cell.textContent = `⚠️ ${message}`;
  tr.appendChild(cell);
  return tr;
}

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

function setTbodyRow(tbody, row) {
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
  tbody.appendChild(row);
}

function makeActionButton(label, icon, onClick, btnClass = 'btn-outline-secondary', title = '') {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = `btn btn-sm ${btnClass} me-1`;
  btn.title = title;
  btn.addEventListener('click', onClick);
  const i = document.createElement('i');
  i.className = `bi ${icon} me-1`;
  i.setAttribute('aria-hidden', 'true');
  btn.appendChild(i);
  btn.appendChild(document.createTextNode(label));
  return btn;
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

// ===== Auth UI =====
function updateAuthUI() {
  const auth = getAuth();
  const userLabel = document.getElementById('userLabel');
  const logoutBtn = document.getElementById('logoutBtn');
  if (auth && auth.user) {
    userLabel.textContent = `${auth.user.display_name || auth.user.username} (${ROLE_LABELS[auth.user.role] || auth.user.role})`;
    logoutBtn.classList.remove('d-none');
  } else {
    userLabel.textContent = '';
    logoutBtn.classList.add('d-none');
  }

  // Role-gated controls
  document.querySelectorAll('[data-role-min]').forEach(el => {
    const min = el.dataset.roleMin;
    if (hasRole(min)) el.classList.remove('d-none');
    else el.classList.add('d-none');
  });

  const auditNav = document.getElementById('auditNavItem');
  if (auditNav) {
    if (hasRole('reviewer')) auditNav.classList.remove('d-none');
    else auditNav.classList.add('d-none');
  }

  const usersNav = document.getElementById('usersNavItem');
  if (usersNav) {
    if (hasRole('admin')) usersNav.classList.remove('d-none');
    else usersNav.classList.add('d-none');
  }
}

function forceLogout() {
  setAuth(null);
  updateAuthUI();
  showLoginModal();
}

function logout() {
  setAuth(null);
  updateAuthUI();
  showToast('ログアウトしました', 'info');
  showLoginModal();
}

function showLoginModal() {
  const modalEl = document.getElementById('loginModal');
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  modal.show();
  document.getElementById('loginError').classList.add('d-none');
  document.getElementById('loginForm').reset();
}

// ===== Notifications =====
async function refreshUnreadBadge() {
  const auth = getAuth();
  if (!auth) return;
  try {
    const data = await fetchJSON('/api/notifications/unread-count');
    const badge = document.getElementById('notifBadge');
    if (badge) {
      badge.textContent = data.count;
      badge.classList.toggle('d-none', !data.count);
    }
  } catch (_) {}
}

async function loadNotifications() {
  const list = document.getElementById('notificationList');
  if (!list) return;
  try {
    const notifications = await fetchJSON('/api/notifications?unread_only=true');
    while (list.firstChild) list.removeChild(list.firstChild);
    if (!notifications || !notifications.length) {
      const p = document.createElement('p');
      p.className = 'text-muted small text-center my-3';
      p.textContent = '未読の通知はありません';
      list.appendChild(p);
      return;
    }
    for (const n of notifications) {
      const item = document.createElement('div');
      item.className = 'notification-item border-bottom py-2 px-1';
      item.setAttribute('role', 'button');
      item.tabIndex = 0;
      item.addEventListener('click', () => markNotificationRead(n.notification_id));
      const msg = document.createElement('div');
      msg.className = 'small';
      msg.textContent = n.message;
      const meta = document.createElement('div');
      meta.className = 'text-muted small';
      meta.textContent = new Date(n.created_at).toLocaleString('ja-JP');
      item.appendChild(msg);
      item.appendChild(meta);
      list.appendChild(item);
    }
  } catch (_) {}
}

async function markNotificationRead(notificationId) {
  try {
    await fetchJSON(`/api/notifications/${notificationId}/read`, { method: 'PUT' });
    refreshUnreadBadge();
    loadNotifications();
  } catch (err) {
    showToast(`既読処理に失敗: ${err.message}`, 'danger');
  }
}

async function markAllNotificationsRead() {
  try {
    await fetchJSON('/api/notifications/read-all', { method: 'PUT' });
    refreshUnreadBadge();
    loadNotifications();
    showToast('すべて既読にしました', 'success');
  } catch (err) {
    showToast(`既読処理に失敗: ${err.message}`, 'danger');
  }
}

async function submitLogin() {
  const form = document.getElementById('loginForm');
  if (!form.checkValidity()) { form.reportValidity(); return; }
  const username = document.getElementById('loginUsername').value.trim();
  const password = document.getElementById('loginPassword').value;
  const errorEl = document.getElementById('loginError');
  errorEl.classList.add('d-none');

  showLoading();
  try {
    const data = await fetchJSON('/api/auth/login', {
      method: 'POST',
      body: { username, password },
    });
    setAuth({ token: data.access_token, user: data.user });
    bootstrap.Modal.getInstance(document.getElementById('loginModal')).hide();
    updateAuthUI();
    showToast(`ようこそ、${data.user.display_name || data.user.username} さん`, 'success');
    navigateTo(currentPage === 'dashboard' ? 'dashboard' : currentPage);
  } catch (err) {
    errorEl.textContent = `ログイン失敗: ${err.message}`;
    errorEl.classList.remove('d-none');
  } finally {
    hideLoading();
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
    case 'dashboard': loadDashboard(); break;
    case 'projects': loadProjects(); break;
    case 'activities': populateProjectSelects(); break;
    case 'calculation': populateProjectSelects(); break;
    case 'reports': populateProjectSelects(); break;
    case 'factors': loadFactors(); break;
    case 'actions': populateProjectSelects().then(loadActions); break;
    case 'audit': loadAuditLogs(); break;
    case 'users': loadUsers(); break;
  }
}

// ===== Dashboard =====
async function loadDashboard() {
  try {
    const data = await fetchJSON('/api/emissions/dashboard');
    document.getElementById('dashProjects').textContent = formatNumber(data.project_count, 0);
    document.getElementById('dashTotal').textContent = formatNumber(data.total_co2_t, 3);
    document.getElementById('dashMissing').textContent = formatNumber(data.missing_factor_count, 0);
    document.getElementById('dashApproved').textContent = formatNumber(data.approved_activity_count, 0);

    renderDashboardCharts(data);
  } catch (err) {
    showToast(`ダッシュボード取得失敗: ${err.message}`, 'danger');
  }
}

function renderDashboardCharts(data) {
  destroyChart('dashTrend');
  const ctx = document.getElementById('dashTrendChart').getContext('2d');
  const trend = data.trend || [];
  charts['dashTrend'] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: trend.map(m => m.target_month),
      datasets: [{
        label: 'CO2排出量 (t-CO2)',
        data: trend.map(m => Number((m.total_co2_t || 0).toFixed(4))),
        backgroundColor: '#2d7d46',
        borderRadius: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, title: { display: true, text: 't-CO2' } } },
    },
  });

  destroyChart('dashCategory');
  const ctx2 = document.getElementById('dashCategoryChart').getContext('2d');
  const bc = data.by_category || {};
  const cats = Object.keys(bc).sort();
  charts['dashCategory'] = new Chart(ctx2, {
    type: 'doughnut',
    data: {
      labels: cats.map(c => CATEGORY_LABELS[c] || c),
      datasets: [{
        data: cats.map(c => Number((bc[c] / 1000).toFixed(4))),
        backgroundColor: cats.map(c => CATEGORY_COLORS[c] || '#95a5a6'),
        borderWidth: 2,
        borderColor: '#fff',
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'right' },
        tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${formatNumber(ctx.raw, 3)} t-CO2` } },
      },
    },
  });
}

// ===== Projects =====
async function loadProjects() {
  const tbody = document.getElementById('projectsTableBody');
  setTbodyRow(tbody, makeLoadingRow(7));
  try {
    const projects = await fetchJSON('/api/projects');
    renderProjectsTable(projects);
  } catch (err) {
    setTbodyRow(tbody, makeErrorRow(7, err.message));
  }
}

function renderProjectsTable(projects) {
  const tbody = document.getElementById('projectsTableBody');
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);

  if (!projects || projects.length === 0) {
    tbody.appendChild(makeEmptyRow(7, '🏗️', '工事が登録されていません。「新規登録」から追加してください。'));
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
    tr.appendChild(td(p.work_type || p.construction_type || '-'));
    tr.appendChild(td(p.start_date || '-'));
    tr.appendChild(td(p.end_date || '-'));

    const badgeTd = document.createElement('td');
    badgeTd.className = 'text-center';
    badgeTd.appendChild(makeBadge(isSelected ? '選択中' : '選択', isSelected ? 'bg-success' : 'bg-secondary'));
    tr.appendChild(badgeTd);

    const actionTd = document.createElement('td');
    actionTd.className = 'text-center';
    if (hasRole('site')) {
      actionTd.appendChild(makeActionButton('編集', 'bi-pencil', ev => {
        ev.stopPropagation();
        openProjectModal(p);
      }, 'btn-outline-primary', '工事を編集'));
      actionTd.appendChild(makeActionButton('削除', 'bi-trash', ev => {
        ev.stopPropagation();
        deleteProject(p);
      }, 'btn-outline-danger', '工事を削除'));
    } else {
      actionTd.textContent = '-';
    }
    tr.appendChild(actionTd);

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

function openProjectModal(project = null) {
  const form = document.getElementById('projectForm');
  form.reset();
  document.getElementById('fProjectEditId').value = project ? project.project_id : '';
  if (project) {
    document.getElementById('fProjectName').value = project.name || '';
    document.getElementById('fBranch').value = project.branch || '';
    document.getElementById('fConstructionType').value = project.work_type || '';
    document.getElementById('fStartDate').value = project.start_date || '';
    document.getElementById('fEndDate').value = project.end_date || '';
    document.getElementById('fNotes').value = project.description || '';
    document.getElementById('projectModalLabel').textContent = '工事の編集';
  } else {
    document.getElementById('projectModalLabel').textContent = '工事の新規登録';
  }
  bootstrap.Modal.getOrCreateInstance(document.getElementById('projectModal')).show();
}

async function submitProjectForm() {
  const form = document.getElementById('projectForm');
  if (!form.checkValidity()) { form.reportValidity(); return; }

  const data = {
    name: document.getElementById('fProjectName').value.trim(),
    branch: document.getElementById('fBranch').value.trim(),
    work_type: document.getElementById('fConstructionType').value.trim(),
    start_date: document.getElementById('fStartDate').value || null,
    end_date: document.getElementById('fEndDate').value || null,
    description: document.getElementById('fNotes').value.trim(),
  };
  const editId = document.getElementById('fProjectEditId').value;

  showLoading();
  try {
    if (editId) {
      await fetchJSON(`/api/projects/${editId}`, { method: 'PUT', body: data });
      showToast('工事を更新しました', 'success');
    } else {
      await fetchJSON('/api/projects', { method: 'POST', body: data });
      showToast('工事を登録しました', 'success');
    }
    bootstrap.Modal.getInstance(document.getElementById('projectModal')).hide();
    loadProjects();
    loadDashboard();
    refreshUnreadBadge();
  } catch (err) {
    showToast(`保存失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function deleteProject(project) {
  if (!window.confirm(`工事「${project.name}」を削除しますか？関連する活動量・算定結果・削減アクションも削除されます。`)) return;
  showLoading();
  try {
    await fetchJSON(`/api/projects/${project.project_id}`, { method: 'DELETE' });
    if (currentProjectId === project.project_id) currentProjectId = null;
    showToast('工事を削除しました', 'success');
    loadProjects();
    loadDashboard();
  } catch (err) {
    showToast(`削除失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

// ===== Project Select Populate =====
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
        opt.value = p.project_id;
        opt.textContent = p.name || p.project_id;
        if (current === p.project_id) opt.selected = true;
        sel.appendChild(opt);
      }
      if (currentProjectId && !sel.value) sel.value = currentProjectId;
    });
  } catch (err) {
    console.warn('Project select populate failed:', err.message);
  }
}

// ===== Activities =====
async function loadActivities(projectId, month) {
  if (!projectId || !month) return;
  const tbody = document.getElementById('activitiesTableBody');
  setTbodyRow(tbody, makeLoadingRow(8));
  try {
    const params = new URLSearchParams({ project_id: projectId, target_month: month });
    const activities = await fetchJSON(`/api/activities?${params}`);
    renderActivitiesTable(activities);
  } catch (err) {
    setTbodyRow(tbody, makeErrorRow(8, err.message));
  }
}

function renderActivitiesTable(activities) {
  const tbody = document.getElementById('activitiesTableBody');
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);

  if (!activities || activities.length === 0) {
    tbody.appendChild(makeEmptyRow(8, '📋', '活動量データがありません。フォームまたはExcel取込から登録してください。'));
    return;
  }

  for (const a of activities) {
    const tr = document.createElement('tr');
    if (a.approved) tr.classList.add('approved-row');

    const catTd = document.createElement('td');
    catTd.appendChild(makeCategoryBadge(a.category));
    tr.appendChild(catTd);
    tr.appendChild(td(a.item_name));
    tr.appendChild(td(formatNumber(a.quantity, 3), 'text-end'));
    tr.appendChild(td(a.unit));
    tr.appendChild(td(a.source_file || '-'));

    const chkTd = document.createElement('td');
    chkTd.className = 'text-center';
    const chk = document.createElement('input');
    chk.type = 'checkbox';
    chk.className = 'form-check-input approve-checkbox';
    chk.dataset.id = a.activity_id;
    chk.checked = !!a.approved;
    chk.disabled = !hasRole('reviewer');
    chk.addEventListener('change', () => toggleApprove(chk));
    chkTd.appendChild(chk);
    tr.appendChild(chkTd);

    const statusTd = document.createElement('td');
    statusTd.className = 'text-center';
    statusTd.appendChild(makeBadge(a.approved ? '承認済' : '未承認', a.approved ? 'bg-success' : 'bg-secondary'));
    tr.appendChild(statusTd);

    const actionTd = document.createElement('td');
    actionTd.className = 'text-center';
    if (hasRole('site')) {
      actionTd.appendChild(makeActionButton('', 'bi-pencil', () => openActivityEditModal(a), 'btn-outline-primary btn-icon', '編集'));
      actionTd.appendChild(makeActionButton('', 'bi-trash', () => deleteActivity(a), 'btn-outline-danger btn-icon', '削除'));
    } else {
      actionTd.textContent = '-';
    }
    tr.appendChild(actionTd);
    tbody.appendChild(tr);
  }
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
    note: document.getElementById('fNote').value.trim() || null,
  };

  showLoading();
  try {
    await fetchJSON('/api/activities', { method: 'POST', body: data });
    form.reset();
    document.getElementById('actProjectSelect').value = projectId;
    document.getElementById('actMonthPicker').value = month;
    showToast('活動量を登録しました', 'success');
    loadActivities(projectId, month);
    refreshUnreadBadge();
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

async function toggleApprove(checkbox) {
  const activityId = checkbox.dataset.id;
  const row = checkbox.closest('tr');
  try {
    await fetchJSON(`/api/activities/${activityId}/approve`, {
      method: 'PUT',
      body: { approved: checkbox.checked },
    });
    const statusTd = row.querySelector('td:nth-last-child(2)');
    if (statusTd) {
      while (statusTd.firstChild) statusTd.removeChild(statusTd.firstChild);
      statusTd.appendChild(makeBadge(checkbox.checked ? '承認済' : '未承認', checkbox.checked ? 'bg-success' : 'bg-secondary'));
    }
    row.classList.toggle('approved-row', checkbox.checked);
    showToast(checkbox.checked ? '承認しました' : '承認を取消しました', 'success');
  } catch (err) {
    checkbox.checked = !checkbox.checked;
    showToast(`承認操作に失敗しました: ${err.message}`, 'danger');
  }
}

async function downloadTemplate() {
  showLoading();
  try {
    await downloadFile('/api/activities/template', 'activity_import_template.xlsx');
    showToast('テンプレートをダウンロードしました', 'success');
  } catch (err) {
    showToast(`ダウンロード失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function bulkApprove() {
  const unchecked = document.querySelectorAll('.approve-checkbox:not(:checked)');
  if (!unchecked.length) { showToast('未承認のデータはありません', 'info'); return; }
  if (!window.confirm(`${unchecked.length}件を一括承認しますか？`)) return;

  showLoading();
  let success = 0;
  let failed = 0;
  for (const cb of unchecked) {
    try {
      await fetchJSON(`/api/activities/${cb.dataset.id}/approve`, {
        method: 'PUT',
        body: { approved: true },
      });
      cb.checked = true;
      const row = cb.closest('tr');
      if (row) {
        row.classList.add('approved-row');
        const statusTd = row.querySelector('td:nth-last-child(2)');
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
  showToast(`一括承認完了: 成功 ${success}件${failed ? ` / 失敗 ${failed}件` : ''}`, failed ? 'warning' : 'success');
  refreshUnreadBadge();
}

function openActivityEditModal(activity) {
  document.getElementById('eActivityId').value = activity.activity_id;
  document.getElementById('eQuantity').value = activity.quantity;
  document.getElementById('eUnit').value = activity.unit;
  document.getElementById('eSourceFile').value = activity.source_file || '';
  document.getElementById('eNote').value = activity.note || '';
  bootstrap.Modal.getOrCreateInstance(document.getElementById('activityEditModal')).show();
}

async function submitActivityEdit() {
  const form = document.getElementById('activityEditForm');
  if (!form.checkValidity()) { form.reportValidity(); return; }
  const activityId = document.getElementById('eActivityId').value;
  const data = {
    quantity: parseFloat(document.getElementById('eQuantity').value),
    unit: document.getElementById('eUnit').value.trim(),
    source_file: document.getElementById('eSourceFile').value.trim() || null,
    note: document.getElementById('eNote').value.trim() || null,
  };
  showLoading();
  try {
    await fetchJSON(`/api/activities/${activityId}`, { method: 'PUT', body: data });
    bootstrap.Modal.getInstance(document.getElementById('activityEditModal')).hide();
    showToast('活動量を更新しました（承認は解除されます）', 'success');
    onActivityFilterChange();
  } catch (err) {
    showToast(`更新失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function deleteActivity(activity) {
  if (!window.confirm(`活動量「${activity.item_name} ${activity.quantity}${activity.unit}」を削除しますか？`)) return;
  showLoading();
  try {
    await fetchJSON(`/api/activities/${activity.activity_id}`, { method: 'DELETE' });
    showToast('活動量を削除しました', 'success');
    onActivityFilterChange();
  } catch (err) {
    showToast(`削除失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

// ===== Activity Excel Import =====
async function importActivities() {
  const fileInput = document.getElementById('importFile');
  if (!fileInput.files || !fileInput.files.length) {
    showToast('取込ファイルを選択してください', 'warning');
    return;
  }
  const file = fileInput.files[0];
  const formData = new FormData();
  formData.append('file', file);
  const auth = getAuth();
  showLoading();
  try {
    const res = await fetch(API_BASE + '/api/activities/import', {
      method: 'POST',
      headers: auth && auth.token ? { Authorization: `Bearer ${auth.token}` } : {},
      body: formData,
    });
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { msg = (await res.json()).detail || msg; } catch (_) {}
      throw new Error(msg);
    }
    const data = await res.json();
    const resultEl = document.getElementById('importResult');
    resultEl.textContent = `取込完了: 成功 ${data.imported}件 / スキップ ${data.skipped}件`;
    resultEl.className = data.errors && data.errors.length ? 'mt-2 small text-danger' : 'mt-2 small text-success';
    if (data.errors && data.errors.length) {
      resultEl.textContent += `\n${data.errors.slice(0, 10).join('\n')}${data.errors.length > 10 ? `\n他 ${data.errors.length - 10}件` : ''}`;
    }
    showToast(`取込完了: 成功 ${data.imported}件`, data.errors && data.errors.length ? 'warning' : 'success');
    fileInput.value = '';
    onActivityFilterChange();
    refreshUnreadBadge();
  } catch (err) {
    showToast(`取込失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

// ===== Emissions Calculation =====
async function executeCalculation() {
  const projectId = document.getElementById('calcProjectSelect').value;
  const month = document.getElementById('calcMonthPicker').value;
  if (!projectId) { showToast('工事を選択してください', 'warning'); return; }
  if (!month) { showToast('対象月を選択してください', 'warning'); return; }

  showLoading();
  try {
    const result = await fetchJSON('/api/emissions/calculate', {
      method: 'POST',
      body: { project_id: projectId, target_month: month },
    });
    showToast('算定を実行しました', 'success');

    const summary = await fetchJSON(`/api/emissions/summary?${new URLSearchParams({ project_id: projectId, target_month: month })}`);
    renderCalculationResults(result, summary);
    renderEmissionChart(summary);
    await loadMissingFactors(projectId, month);
    await Promise.all([loadBenchmark(projectId, month), loadAnomalies(projectId, month)]);

    try {
      const suggestions = await fetchJSON(`/api/emissions/reduction/${encodeURIComponent(projectId)}/${encodeURIComponent(month)}`);
      lastSuggestions = suggestions;
      lastSuggestionProject = projectId;
      lastSuggestionMonth = month;
      renderReductionSuggestions(suggestions);
    } catch (_) {
      lastSuggestions = [];
      renderReductionSuggestions([]);
    }
    refreshUnreadBadge();
  } catch (err) {
    showToast(`算定失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function loadBenchmark(projectId, month) {
  const card = document.getElementById('benchmarkCard');
  const body = document.getElementById('benchmarkBody');
  try {
    const data = await fetchJSON(`/api/emissions/benchmark?${new URLSearchParams({ project_id: projectId, target_month: month })}`);
    if (!data.peer_project_count) {
      card.style.display = 'none';
      return;
    }
    while (body.firstChild) body.removeChild(body.firstChild);
    const currentT = (data.current_total_t || 0).toFixed(3);
    const peerT = data.peer_avg_monthly_t == null ? '-' : data.peer_avg_monthly_t.toFixed(3);
    const ratio = data.comparison_ratio == null ? '-' : `${(data.comparison_ratio * 100).toFixed(0)}%`;
    const badgeClass = data.comparison_ratio == null ? 'bg-secondary'
      : data.comparison_ratio <= 1.0 ? 'bg-success' : 'bg-danger';
    const ratioBadge = document.createElement('span');
    ratioBadge.className = `badge ${badgeClass}`;
    ratioBadge.textContent = `同工種平均比 ${ratio}`;
    const text = document.createElement('div');
    text.className = 'small';
    text.textContent = `対象工事: ${currentT} t-CO2 / 同工種(${data.work_type || '不明'})の他工事 ${data.peer_project_count} 件の月平均: ${peerT} t-CO2`;
    text.appendChild(document.createTextNode(' '));
    text.appendChild(ratioBadge);
    body.appendChild(text);
    card.style.display = 'block';
  } catch (_) {
    card.style.display = 'none';
  }
}

async function loadAnomalies(projectId, month) {
  const alertEl = document.getElementById('anomalyAlert');
  try {
    const anomalies = await fetchJSON(`/api/emissions/anomalies?${new URLSearchParams({ project_id: projectId, target_month: month })}`);
    if (anomalies && anomalies.length) {
      const lines = anomalies.map(a => `${a.item_name} (${a.category}/${a.quantity}${a.unit}): ${a.reasons.join('、')}`);
      alertEl.textContent = `⚠️ 異常値の可能性がある活動量が ${anomalies.length} 件あります。\n${lines.slice(0, 5).join('\n')}${lines.length > 5 ? `\n他 ${lines.length - 5} 件` : ''}`;
      alertEl.classList.remove('d-none');
    } else {
      alertEl.classList.add('d-none');
    }
  } catch (_) {
    alertEl.classList.add('d-none');
  }
}

function renderCalculationResults(items, summary) {
  document.getElementById('calcResultsSection').style.display = 'block';
  const tbody = document.getElementById('calcTableBody');
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);

  if (!items || !items.length) {
    const tr = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 8;
    cell.className = 'text-center text-muted py-3';
    cell.textContent = '算定結果データがありません（承認済み活動量がないか、係数未設定です）';
    tr.appendChild(cell);
    tbody.appendChild(tr);
  } else {
    for (const item of items) {
      const co2kg = item.co2_kg ?? 0;
      const tr = document.createElement('tr');
      const catTd = document.createElement('td');
      catTd.appendChild(makeCategoryBadge(item.category));
      tr.appendChild(catTd);
      tr.appendChild(td(item.item_name || '-'));
      tr.appendChild(td(formatNumber(item.quantity, 3), 'text-end'));
      tr.appendChild(td(item.unit || '-'));
      tr.appendChild(td(formatNumber(item.factor_value, 4), 'text-end'));
      tr.appendChild(td(item.factor_effective_from || '-'));
      tr.appendChild(td(formatNumber(co2kg), 'text-end co2-value'));
      tr.appendChild(td(formatNumber(co2kg / 1000, 4), 'text-end co2-value'));
      tbody.appendChild(tr);
    }
  }

  const totals = extractTotals(summary);
  document.getElementById('statTotal').textContent = formatNumber(totals.total_t, 3);
  document.getElementById('statFuel').textContent = formatNumber(totals.fuel_t, 3);
  document.getElementById('statPower').textContent = formatNumber(totals.power_t, 3);
  document.getElementById('statMaterial').textContent = formatNumber(totals.material_t, 3);
  document.getElementById('statTransport').textContent = formatNumber(totals.transport_t, 3);
}

function extractTotals(data) {
  const r = { total_t: 0, fuel_t: 0, power_t: 0, material_t: 0, transport_t: 0 };
  if (Array.isArray(data)) {
    for (const item of data) {
      const cat = item.category;
      const kg = Number(item.total_co2_kg || 0);
      if (cat === 'fuel') r.fuel_t += kg;
      else if (cat === 'power') r.power_t += kg;
      else if (cat === 'material') r.material_t += kg;
      else if (cat === 'transport') r.transport_t += kg;
    }
    r.total_t = (r.fuel_t + r.power_t + r.material_t + r.transport_t) / 1000;
    r.fuel_t /= 1000;
    r.power_t /= 1000;
    r.material_t /= 1000;
    r.transport_t /= 1000;
    return r;
  }
  if (!data) return r;
  r.total_t = data.total_co2_t ?? data.total_t ?? data.total ?? 0;
  r.fuel_t = data.fuel_co2_t ?? data.fuel_t ?? data.fuel ?? 0;
  r.power_t = data.power_co2_t ?? data.power_t ?? data.power ?? 0;
  r.material_t = data.material_co2_t ?? data.material_t ?? data.material ?? 0;
  r.transport_t = data.transport_co2_t ?? data.transport_t ?? data.transport ?? 0;
  if (data.by_category) {
    const bc = data.by_category;
    r.fuel_t = bc.fuel ?? r.fuel_t;
    r.power_t = bc.power ?? r.power_t;
    r.material_t = bc.material ?? r.material_t;
    r.transport_t = bc.transport ?? r.transport_t;
  }
  if (!r.total_t) r.total_t = r.fuel_t + r.power_t + r.material_t + r.transport_t;
  return r;
}

function renderEmissionChart(data) {
  destroyChart('emission');
  const ctx = document.getElementById('emissionChart').getContext('2d');
  const totals = extractTotals(data);
  const labels = ['燃料', '電力', '材料', '輸送'];
  const values = [totals.fuel_t, totals.power_t, totals.material_t, totals.transport_t];
  charts['emission'] = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: ['#e67e22', '#f1c40f', '#7f8c8d', '#2980b9'],
        borderWidth: 2,
        borderColor: '#fff',
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'right' },
        tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${formatNumber(ctx.raw, 3)} t-CO2` } },
      },
    },
  });
}

async function loadMissingFactors(projectId, month) {
  const alertEl = document.getElementById('missingFactorsAlert');
  try {
    const params = new URLSearchParams({ project_id: projectId, target_month: month });
    const missing = await fetchJSON(`/api/emissions/missing-factors?${params}`);
    if (missing && missing.length) {
      const items = missing.map(m => `${m.item_name} (${m.category}/${m.quantity}${m.unit})`).join('、');
      alertEl.textContent = `⚠️ 排出係数が未設定のため算定されなかった活動量が ${missing.length} 件あります: ${items}`;
      alertEl.classList.remove('d-none');
    } else {
      alertEl.classList.add('d-none');
    }
  } catch (_) {
    alertEl.classList.add('d-none');
  }
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
    const strong = document.createElement('strong');
    strong.textContent = `${CATEGORY_LABELS[s.category] || s.category} (${formatNumber((s.total_co2_kg || 0) / 1000, 3)} t-CO2, 順位${s.rank})`;
    div.appendChild(strong);
    const ul = document.createElement('ul');
    ul.className = 'mb-0 mt-1 small';
    for (const text of (s.suggestions || [])) {
      const li = document.createElement('li');
      li.textContent = text;
      ul.appendChild(li);
    }
    div.appendChild(ul);
    container.appendChild(div);
  }
}

async function createActionFromSuggestions() {
  if (!lastSuggestions.length || !lastSuggestionProject) {
    showToast('算定後に削減提案を取得してください', 'warning');
    return;
  }
  const first = lastSuggestions[0];
  await openActionModal();
  document.getElementById('eActionProject').value = lastSuggestionProject;
  document.getElementById('eActionMonth').value = lastSuggestionMonth;
  document.getElementById('eActionCategory').value = first.category;
  document.getElementById('eActionSuggestion').value = first.suggestions[0] || '';
  document.getElementById('eActionStatus').value = 'planned';
  document.getElementById('eActionEst').value = '';
  document.getElementById('eActionActual').value = '';
  document.getElementById('eActionNote').value = '';
  bootstrap.Modal.getOrCreateInstance(document.getElementById('actionModal')).show();
}

// ===== Reports =====
async function downloadCurrentReport(format) {
  const projectId = document.getElementById('rptProjectSelect').value;
  const month = document.getElementById('rptMonthPicker').value;
  if (!projectId) { showToast('工事を選択してください', 'warning'); return; }
  if (!month) { showToast('対象月を選択してください', 'warning'); return; }
  showLoading();
  try {
    await downloadFile(
      `/api/reports/monthly/${encodeURIComponent(projectId)}/${encodeURIComponent(month)}?format=${format}`,
      `co2_report_${month}.${format}`
    );
    showToast('レポートをダウンロードしました', 'success');
  } catch (err) {
    showToast(`ダウンロード失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
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
  const labels = months.map(m => m.target_month || m.month || '');
  const values = months.map(m => Number((m.total_co2_t ?? m.co2_t ?? m.total ?? 0).toFixed(4)));

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
        tooltip: { callbacks: { label: ctx => ` ${formatNumber(ctx.raw, 3)} t-CO2` } },
      },
      scales: {
        y: { beginAtZero: true, title: { display: true, text: 't-CO2' } },
        x: { title: { display: true, text: '対象月' } },
      },
    },
  });
}

function onReportFilterChange() {
  const projectId = document.getElementById('rptProjectSelect').value;
  if (projectId) loadMonthlyTrend();
}

// ===== Factors =====
async function loadFactors() {
  const tbody = document.getElementById('factorsTableBody');
  setTbodyRow(tbody, makeLoadingRow(7));
  try {
    const category = document.getElementById('factorCategoryFilter').value;
    const url = category ? `/api/factors?category=${encodeURIComponent(category)}` : '/api/factors';
    const factors = await fetchJSON(url);
    renderFactorsTable(factors);
  } catch (err) {
    setTbodyRow(tbody, makeErrorRow(7, err.message));
  }
}

function renderFactorsTable(factors) {
  const tbody = document.getElementById('factorsTableBody');
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
  if (!factors || factors.length === 0) {
    tbody.appendChild(makeEmptyRow(7, '📊', '排出係数が登録されていません。'));
    return;
  }
  for (const f of factors) {
    const tr = document.createElement('tr');
    const catTd = document.createElement('td');
    catTd.appendChild(makeCategoryBadge(f.category));
    tr.appendChild(catTd);
    tr.appendChild(td(f.item_name));
    tr.appendChild(td(f.unit));
    tr.appendChild(td(formatNumber(f.factor_value, 4), 'text-end'));
    tr.appendChild(td(f.effective_from || '-'));
    tr.appendChild(td(f.source || '-'));
    const actionTd = document.createElement('td');
    actionTd.className = 'text-center';
    if (hasRole('admin')) {
      actionTd.appendChild(makeActionButton('', 'bi-pencil', () => openFactorModal(f), 'btn-outline-primary btn-icon', '編集'));
      actionTd.appendChild(makeActionButton('', 'bi-trash', () => deleteFactor(f), 'btn-outline-danger btn-icon', '削除'));
    } else {
      actionTd.textContent = '-';
    }
    tr.appendChild(actionTd);
    tbody.appendChild(tr);
  }
}

function openFactorModal(factor = null) {
  const form = document.getElementById('factorForm');
  form.reset();
  document.getElementById('eFactorId').value = factor ? factor.factor_id : '';
  if (factor) {
    document.getElementById('eFactorCategory').value = factor.category;
    document.getElementById('eFactorItem').value = factor.item_name;
    document.getElementById('eFactorUnit').value = factor.unit;
    document.getElementById('eFactorValue').value = factor.factor_value;
    document.getElementById('eFactorDate').value = factor.effective_from || '';
    document.getElementById('eFactorSource').value = factor.source || '';
    document.getElementById('factorModalLabel').textContent = '排出係数の編集';
  } else {
    document.getElementById('factorModalLabel').textContent = '排出係数の新規登録';
  }
  bootstrap.Modal.getOrCreateInstance(document.getElementById('factorModal')).show();
}

async function submitFactorForm() {
  const form = document.getElementById('factorForm');
  if (!form.checkValidity()) { form.reportValidity(); return; }
  const editId = document.getElementById('eFactorId').value;
  const data = {
    category: document.getElementById('eFactorCategory').value,
    item_name: document.getElementById('eFactorItem').value.trim(),
    unit: document.getElementById('eFactorUnit').value.trim(),
    factor_value: parseFloat(document.getElementById('eFactorValue').value),
    effective_from: document.getElementById('eFactorDate').value,
    source: document.getElementById('eFactorSource').value.trim(),
  };
  showLoading();
  try {
    if (editId) {
      await fetchJSON(`/api/factors/${editId}`, { method: 'PUT', body: data });
      showToast('排出係数を更新しました', 'success');
    } else {
      await fetchJSON('/api/factors', { method: 'POST', body: data });
      showToast('排出係数を登録しました', 'success');
    }
    bootstrap.Modal.getInstance(document.getElementById('factorModal')).hide();
    loadFactors();
    refreshUnreadBadge();
  } catch (err) {
    showToast(`保存失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function deleteFactor(factor) {
  if (!window.confirm(`係数「${factor.item_name} (${factor.unit})」を削除しますか？`)) return;
  showLoading();
  try {
    await fetchJSON(`/api/factors/${factor.factor_id}`, { method: 'DELETE' });
    showToast('排出係数を削除しました', 'success');
    loadFactors();
  } catch (err) {
    showToast(`削除失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

// ===== Reduction Actions =====
async function loadActions() {
  const tbody = document.getElementById('actionsTableBody');
  setTbodyRow(tbody, makeLoadingRow(8));
  try {
    const projectId = document.getElementById('actionProjectSelect').value;
    const status = document.getElementById('actionStatusFilter').value;
    const params = new URLSearchParams();
    if (projectId) params.set('project_id', projectId);
    if (status) params.set('status', status);
    const qs = params.toString();
    const actions = await fetchJSON(`/api/actions${qs ? `?${qs}` : ''}`);
    renderActionsTable(actions);
  } catch (err) {
    setTbodyRow(tbody, makeErrorRow(8, err.message));
  }
}

async function renderActionsTable(actions) {
  const tbody = document.getElementById('actionsTableBody');
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
  if (!actions || actions.length === 0) {
    tbody.appendChild(makeEmptyRow(8, '💡', '削減アクションがありません。算定結果の提案から登録できます。'));
    return;
  }
  const projects = await fetchJSON('/api/projects').catch(() => []);
  const projectNames = {};
  for (const p of projects) projectNames[p.project_id] = p.name;

  for (const a of actions) {
    const tr = document.createElement('tr');
    tr.appendChild(td(projectNames[a.project_id] || a.project_id));
    tr.appendChild(td(a.target_month));
    const catTd = document.createElement('td');
    catTd.appendChild(makeCategoryBadge(a.category));
    tr.appendChild(catTd);
    tr.appendChild(td(a.suggestion));
    const statusTd = document.createElement('td');
    statusTd.appendChild(makeBadge(
      a.status === 'implemented' ? '実施済み' : a.status === 'declined' ? '見送り' : '計画',
      a.status === 'implemented' ? 'bg-success' : a.status === 'declined' ? 'bg-secondary' : 'bg-warning'
    ));
    tr.appendChild(statusTd);
    tr.appendChild(td(a.estimated_reduction_kg == null ? '-' : formatNumber(a.estimated_reduction_kg), 'text-end'));
    tr.appendChild(td(a.actual_reduction_kg == null ? '-' : formatNumber(a.actual_reduction_kg), 'text-end'));
    const actionTd = document.createElement('td');
    actionTd.className = 'text-center';
    if (hasRole('site')) {
      actionTd.appendChild(makeActionButton('', 'bi-pencil', () => openActionModal(a), 'btn-outline-primary btn-icon', '編集'));
    }
    if (hasRole('reviewer')) {
      actionTd.appendChild(makeActionButton('', 'bi-trash', () => deleteAction(a), 'btn-outline-danger btn-icon', '削除'));
    }
    tr.appendChild(actionTd);
    tbody.appendChild(tr);
  }
}

async function openActionModal(action = null) {
  await populateProjectSelects();
  const form = document.getElementById('actionForm');
  form.reset();
  document.getElementById('eActionId').value = action ? action.action_id : '';
  if (action) {
    document.getElementById('eActionProject').value = action.project_id;
    document.getElementById('eActionMonth').value = action.target_month;
    document.getElementById('eActionCategory').value = action.category;
    document.getElementById('eActionSuggestion').value = action.suggestion;
    document.getElementById('eActionStatus').value = action.status;
    document.getElementById('eActionEst').value = action.estimated_reduction_kg ?? '';
    document.getElementById('eActionActual').value = action.actual_reduction_kg ?? '';
    document.getElementById('eActionNote').value = action.note || '';
  } else {
    const now = new Date();
    document.getElementById('eActionMonth').value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  }
  bootstrap.Modal.getOrCreateInstance(document.getElementById('actionModal')).show();
}

async function submitActionForm() {
  const form = document.getElementById('actionForm');
  if (!form.checkValidity()) { form.reportValidity(); return; }
  const editId = document.getElementById('eActionId').value;
  const data = {
    project_id: document.getElementById('eActionProject').value,
    target_month: document.getElementById('eActionMonth').value,
    category: document.getElementById('eActionCategory').value,
    suggestion: document.getElementById('eActionSuggestion').value.trim(),
    status: document.getElementById('eActionStatus').value,
    estimated_reduction_kg: document.getElementById('eActionEst').value === '' ? null : parseFloat(document.getElementById('eActionEst').value),
    actual_reduction_kg: document.getElementById('eActionActual').value === '' ? null : parseFloat(document.getElementById('eActionActual').value),
    note: document.getElementById('eActionNote').value.trim() || null,
  };
  showLoading();
  try {
    if (editId) {
      await fetchJSON(`/api/actions/${editId}`, { method: 'PUT', body: data });
      showToast('削減アクションを更新しました', 'success');
    } else {
      await fetchJSON('/api/actions', { method: 'POST', body: data });
      showToast('削減アクションを登録しました', 'success');
    }
    bootstrap.Modal.getInstance(document.getElementById('actionModal')).hide();
    loadActions();
    refreshUnreadBadge();
  } catch (err) {
    showToast(`保存失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function deleteAction(action) {
  if (!window.confirm('この削減アクションを削除しますか？')) return;
  showLoading();
  try {
    await fetchJSON(`/api/actions/${action.action_id}`, { method: 'DELETE' });
    showToast('削減アクションを削除しました', 'success');
    loadActions();
  } catch (err) {
    showToast(`削除失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

// ===== Audit Logs =====
async function loadAuditLogs() {
  const tbody = document.getElementById('auditTableBody');
  setTbodyRow(tbody, makeLoadingRow(6));
  try {
    const logs = await fetchJSON('/api/audit-logs?limit=300');
    renderAuditLogs(logs);
  } catch (err) {
    setTbodyRow(tbody, makeErrorRow(6, err.message));
  }
}

function renderAuditLogs(logs) {
  const tbody = document.getElementById('auditTableBody');
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
  if (!logs || logs.length === 0) {
    tbody.appendChild(makeEmptyRow(6, '🗂️', '監査ログがありません。'));
    return;
  }
  const actionLabels = {
    create: '作成', update: '更新', delete: '削除', approve: '承認',
    unapprove: '承認取消', login: 'ログイン',
  };
  for (const log of logs) {
    const tr = document.createElement('tr');
    tr.appendChild(td(new Date(log.created_at).toLocaleString('ja-JP')));
    tr.appendChild(td(log.actor));
    tr.appendChild(td(makeBadge(actionLabels[log.action] || log.action, 'bg-info')));
    tr.appendChild(td(log.resource_type));
    tr.appendChild(td(log.resource_id || '-'));
    tr.appendChild(td(log.detail || '-'));
    tbody.appendChild(tr);
  }
}

// ===== Users =====
async function loadUsers() {
  const tbody = document.getElementById('usersTableBody');
  setTbodyRow(tbody, makeLoadingRow(6));
  try {
    const users = await fetchJSON('/api/users');
    renderUsersTable(users);
  } catch (err) {
    setTbodyRow(tbody, makeErrorRow(6, err.message));
  }
}

function renderUsersTable(users) {
  const tbody = document.getElementById('usersTableBody');
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
  if (!users || users.length === 0) {
    tbody.appendChild(makeEmptyRow(6, '👤', 'ユーザーが登録されていません。'));
    return;
  }
  const auth = getAuth();
  for (const u of users) {
    const tr = document.createElement('tr');
    tr.appendChild(td(u.username));
    tr.appendChild(td(u.display_name || '-'));
    const roleTd = document.createElement('td');
    roleTd.appendChild(makeBadge(ROLE_LABELS[u.role] || u.role,
      u.role === 'admin' ? 'bg-danger' : u.role === 'reviewer' ? 'bg-info' : u.role === 'site' ? 'bg-primary' : 'bg-secondary'));
    tr.appendChild(roleTd);
    tr.appendChild(td(makeBadge(u.is_active ? '有効' : '無効', u.is_active ? 'bg-success' : 'bg-secondary')));
    tr.appendChild(td(new Date(u.created_at).toLocaleDateString('ja-JP')));
    const actionTd = document.createElement('td');
    actionTd.className = 'text-center';
    if (u.user_id !== auth.user.user_id) {
      actionTd.appendChild(makeActionButton('', 'bi-pencil', () => openUserModal(u), 'btn-outline-primary btn-icon', '編集'));
      actionTd.appendChild(makeActionButton(
        u.is_active ? '無効化' : '有効化',
        u.is_active ? 'bi-pause-circle' : 'bi-play-circle',
        () => toggleUserActive(u),
        u.is_active ? 'btn-outline-warning' : 'btn-outline-success'
      ));
    } else {
      actionTd.appendChild(document.createTextNode('自分'));
    }
    tr.appendChild(actionTd);
    tbody.appendChild(tr);
  }
}

function openUserModal(user = null) {
  const form = document.getElementById('userForm');
  form.reset();
  document.getElementById('eUserId').value = user ? user.user_id : '';
  document.getElementById('pwRequiredMark').style.display = user ? 'none' : '';
  document.getElementById('pwHelp').textContent = user ? '編集時は空欄でパスワードを変更しません。' : '新規作成時は必須。6文字以上。';
  document.getElementById('eUserPassword').required = !user;
  if (user) {
    document.getElementById('eUsername').value = user.username;
    document.getElementById('eUsername').readOnly = true;
    document.getElementById('eDisplayName').value = user.display_name || '';
    document.getElementById('eUserRole').value = user.role;
    document.getElementById('userModalLabel').textContent = 'ユーザーの編集';
  } else {
    document.getElementById('eUsername').readOnly = false;
    document.getElementById('userModalLabel').textContent = 'ユーザーの新規登録';
  }
  bootstrap.Modal.getOrCreateInstance(document.getElementById('userModal')).show();
}

async function submitUserForm() {
  const form = document.getElementById('userForm');
  if (!form.checkValidity()) { form.reportValidity(); return; }
  const editId = document.getElementById('eUserId').value;
  const username = document.getElementById('eUsername').value.trim();
  const displayName = document.getElementById('eDisplayName').value.trim();
  const role = document.getElementById('eUserRole').value;
  const password = document.getElementById('eUserPassword').value;

  showLoading();
  try {
    if (editId) {
      const data = { display_name: displayName, role };
      if (password) data.password = password;
      await fetchJSON(`/api/users/${editId}`, { method: 'PUT', body: data });
      showToast('ユーザーを更新しました', 'success');
    } else {
      if (!password) { showToast('パスワードを入力してください', 'warning'); hideLoading(); return; }
      await fetchJSON('/api/users', {
        method: 'POST',
        body: { username, display_name: displayName, role, password },
      });
      showToast('ユーザーを登録しました', 'success');
    }
    bootstrap.Modal.getInstance(document.getElementById('userModal')).hide();
    loadUsers();
    refreshUnreadBadge();
  } catch (err) {
    showToast(`保存失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function toggleUserActive(user) {
  const next = !user.is_active;
  if (!window.confirm(`ユーザー「${user.username}」を${next ? '有効化' : '無効化'}しますか？`)) return;
  showLoading();
  try {
    await fetchJSON(`/api/users/${user.user_id}/active?is_active=${next}`, { method: 'PUT' });
    showToast(`ユーザーを${next ? '有効化' : '無効化'}しました`, 'success');
    loadUsers();
  } catch (err) {
    showToast(`操作失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
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

  document.getElementById('notificationMenu').addEventListener('show.bs.dropdown', loadNotifications);

  updateAuthUI();

  if (getAuth()) {
    navigateTo('dashboard');
    refreshUnreadBadge();
    setInterval(refreshUnreadBadge, 60000);
  } else {
    showLoginModal();
  }
});
