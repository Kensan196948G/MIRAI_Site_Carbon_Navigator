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
  business_travel: '出張交通',
  commuting: '通勤',
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
  water: '#3498db',
  business_travel: '#9b59b6',
  commuting: '#e84393',
  other: '#95a5a6',
};

const ROLE_LEVELS = { viewer: 0, client: 0, site: 1, reviewer: 2, admin: 3 };
const ROLE_LABELS = { viewer: '閲覧', client: '発注者', site: '現場入力', reviewer: 'レビュアー', admin: '管理者' };

let currentProjectId = null;
let currentPage = 'dashboard';
let charts = {};
let lastSuggestions = [];
let lastSuggestionProject = null;
let lastSuggestionMonth = null;
let pending2faToken = null;

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
  document.getElementById('twofaField').classList.add('d-none');
  pending2faToken = null;
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
  const code = document.getElementById('login2faCode').value.trim();
  const errorEl = document.getElementById('loginError');
  errorEl.classList.add('d-none');

  showLoading();
  try {
    if (pending2faToken) {
      const data = await fetchJSON('/api/auth/2fa/login', {
        method: 'POST',
        body: { temp_token: pending2faToken, code },
      });
      setAuth({ token: data.access_token, user: data.user });
      bootstrap.Modal.getInstance(document.getElementById('loginModal')).hide();
      updateAuthUI();
      showToast('二要素認証が完了しました', 'success');
      navigateTo(currentPage === 'dashboard' ? 'dashboard' : currentPage);
      return;
    }
    const data = await fetchJSON('/api/auth/login', {
      method: 'POST',
      body: { username, password },
    });
    if (data.requires_2fa) {
      pending2faToken = data.temp_token;
      document.getElementById('twofaField').classList.remove('d-none');
      errorEl.textContent = '認証アプリのコードを入力してください';
      errorEl.classList.remove('d-none');
      document.getElementById('login2faCode').focus();
      return;
    }
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

function oidcLogin() {
  window.location.href = '/api/auth/oidc/login';
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
    case 'feedbacks': populateProjectSelects().then(loadFeedbacks); break;
    case 'sbti': loadSbti(); break;
    case 'credits': loadCredits(); break;
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
    loadDashboardSbti();
    loadDemoStatus();
    loadReminders();
    loadMonthSchedule();
  } catch (err) {
    showToast(`ダッシュボード取得失敗: ${err.message}`, 'danger');
  }
}

async function loadMonthSchedule() {
  const list = document.getElementById('monthScheduleList');
  if (!list) return;
  try {
    const now = new Date();
    const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const statuses = await fetchJSON(`/api/emissions/month-status?target_month=${month}`);
    while (list.firstChild) list.removeChild(list.firstChild);
    if (!statuses || !statuses.length) {
      const p = document.createElement('p');
      p.className = 'text-muted small mb-0';
      p.textContent = '対象工事がありません';
      list.appendChild(p);
      return;
    }
    for (const s of statuses.slice(0, 12)) {
      const row = document.createElement('div');
      row.className = 'd-flex justify-content-between align-items-center border-bottom py-1 small';
      const left = document.createElement('span');
      left.textContent = `${s.project_name}（${s.branch || '-'}）`;
      const right = document.createElement('span');
      const parts = [];
      parts.push(s.is_closed ? '🔒 締め済み' : `締め日 ${s.close_day}日 まで${s.days_remaining}日`);
      parts.push(s.activity_count ? `登録${s.activity_count}件` : '未登録');
      if (s.approved_count < s.activity_count) parts.push(`未承認 ${s.activity_count - s.approved_count}件`);
      right.textContent = parts.join(' / ');
      right.className = s.is_closed ? 'text-secondary' : (s.activity_count === 0 || s.approved_count < s.activity_count) ? 'text-danger' : 'text-success';
      row.appendChild(left);
      row.appendChild(right);
      list.appendChild(row);
    }
  } catch (_) {
    const p = document.createElement('p');
    p.className = 'text-muted small mb-0';
    p.textContent = '月次スケジュールを取得できませんでした';
    list.appendChild(p);
  }
}

async function loadReminders() {
  const list = document.getElementById('reminderList');
  if (!list) return;
  try {
    const now = new Date();
    const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const reminders = await fetchJSON(`/api/emissions/reminders?target_month=${month}`);
    while (list.firstChild) list.removeChild(list.firstChild);
    if (!reminders || !reminders.length) {
      const p = document.createElement('p');
      p.className = 'text-muted small mb-0';
      p.textContent = '督促対象はありません';
      list.appendChild(p);
      return;
    }
    const ul = document.createElement('ul');
    ul.className = 'mb-0 small';
    for (const r of reminders.slice(0, 8)) {
      const li = document.createElement('li');
      li.textContent = `${r.project_name}（${r.branch || '-'}）: ${r.status === 'no_data' ? 'データ未登録' : `未承認 ${r.activity_count}件`}`;
      ul.appendChild(li);
    }
    list.appendChild(ul);
  } catch (_) {
    const p = document.createElement('p');
    p.className = 'text-muted small mb-0';
    p.textContent = '督促状況を取得できませんでした';
    list.appendChild(p);
  }
}

async function sendReminders() {
  if (!window.confirm('督促通知を全対象へ送信しますか？')) return;
  showLoading();
  try {
    const now = new Date();
    const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const data = await fetchJSON('/api/notifications/remind', { method: 'POST', body: { target_month: month } });
    showToast(`督促を${data.reminded_projects}件送信しました`, 'success');
    refreshUnreadBadge();
    loadReminders();
  } catch (err) {
    showToast(`督促送信失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function exportFull() {
  showLoading();
  try {
    await downloadFile('/api/export/full', `mirai_carbon_export_${new Date().toISOString().slice(0, 10)}.zip`);
    showToast('全量エクスポートをダウンロードしました', 'success');
  } catch (err) {
    showToast(`エクスポート失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function loadDashboardSbti() {
  const body = document.getElementById('dashSbtiBody');
  if (!body) return;
  try {
    const items = await fetchJSON('/api/sbti/progress');
    while (body.firstChild) body.removeChild(body.firstChild);
    if (!items || !items.length) {
      const p = document.createElement('p');
      p.className = 'text-muted small mb-0';
      p.textContent = 'SBTi目標が未設定です。「SBTi」ページから登録できます。';
      body.appendChild(p);
      return;
    }
    for (const item of items) {
      const row = document.createElement('div');
      row.className = 'mb-2';
      const label = document.createElement('div');
      label.className = 'small d-flex justify-content-between';
      const nameSpan = document.createElement('span');
      nameSpan.textContent = item.name;
      const pctSpan = document.createElement('span');
      pctSpan.textContent = `達成 ${Math.max(0, item.reduction_achieved_percent).toFixed(1)}% / 目標 ${item.reduction_percent}%`;
      pctSpan.className = item.on_track ? 'text-success fw-bold' : 'text-danger fw-bold';
      label.appendChild(nameSpan);
      label.appendChild(pctSpan);
      const progress = document.createElement('div');
      progress.className = 'progress';
      progress.style.height = '8px';
      const bar = document.createElement('div');
      bar.className = 'progress-bar ' + (item.on_track ? 'bg-success' : 'bg-danger');
      bar.style.width = `${Math.min(100, Math.max(0, (item.progress_ratio ?? 0) * 100))}%`;
      progress.appendChild(bar);
      row.appendChild(label);
      row.appendChild(progress);
      body.appendChild(row);
    }
  } catch (_) {}
}

async function loadDemoStatus() {
  const el = document.getElementById('demoStatusText');
  if (!el) return;
  try {
    const data = await fetchJSON('/api/demo/status');
    if (data.project_count > 0) {
      el.textContent = `デモデータ: 生成済み（工事${data.project_count}件 / 活動量${data.activity_count}件 / フィードバック${data.feedback_count}件）`;
    } else {
      el.textContent = 'デモデータ: 未生成';
    }
  } catch (_) {}
}

async function generateDemoData() {
  if (!window.confirm('2現場×7ヶ月のPoCデモデータを生成しますか？（既存デモがある場合はスキップされます）')) return;
  showLoading();
  try {
    const data = await fetchJSON('/api/demo/generate', { method: 'POST' });
    showToast(`デモデータ生成完了: 工事${data.project_count}件 / 活動量${data.activity_count}件`, 'success');
    loadDemoStatus();
    loadDashboard();
  } catch (err) {
    showToast(`生成失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function clearDemoData() {
  if (!window.confirm('デモデータをすべて削除しますか？')) return;
  showLoading();
  try {
    const data = await fetchJSON('/api/demo/clear', { method: 'DELETE' });
    showToast(`デモデータを削除しました（${data.removed}件）`, 'success');
    loadDemoStatus();
    loadDashboard();
  } catch (err) {
    showToast(`削除失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
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
    actionTd.appendChild(makeActionButton('', 'bi-file-earmark-pdf', ev => {
      ev.stopPropagation();
      downloadProjectCard(p);
    }, 'btn-outline-danger btn-icon', '工事カルテPDF'));
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

async function downloadProjectCard(project) {
  showLoading();
  try {
    await downloadFile(`/api/reports/card/${encodeURIComponent(project.project_id)}`, `project_card_${project.project_id.slice(0, 8)}.pdf`);
    showToast('工事カルテをダウンロードしました', 'success');
  } catch (err) {
    showToast(`ダウンロード失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function downloadProjectTemplate() {
  showLoading();
  try {
    await downloadFile('/api/projects/template', 'project_import_template.xlsx');
    showToast('取込テンプレートをダウンロードしました', 'success');
  } catch (err) {
    showToast(`ダウンロード失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function importProjects() {
  const input = document.getElementById('projectImportFile');
  if (!input.files || !input.files.length) { showToast('取込ファイルを選択してください', 'warning'); return; }
  const formData = new FormData();
  formData.append('file', input.files[0]);
  const auth = getAuth();
  showLoading();
  try {
    const res = await fetch(API_BASE + '/api/projects/import', {
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
    showToast(`工事取込完了: 成功${data.imported}件 / スキップ${data.skipped}件`, data.errors && data.errors.length ? 'warning' : 'success');
    if (data.errors && data.errors.length) console.warn(data.errors);
    input.value = '';
    loadProjects();
    loadDashboard();
  } catch (err) {
    showToast(`取込失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
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
    updateActivityLockState(projectId, month);
  } catch (err) {
    setTbodyRow(tbody, makeErrorRow(8, err.message));
  }
}

async function updateActivityLockState(projectId, month) {
  const alertEl = document.getElementById('activityLockAlert');
  const form = document.getElementById('activityForm');
  const buttons = document.querySelectorAll('#section-activities [data-role-min]');
  if (!alertEl) return;
  try {
    const closes = await fetchJSON(`/api/closes?${new URLSearchParams({ project_id: projectId, target_month: month })}`);
    const locked = closes && closes.length > 0;
    if (locked) {
      alertEl.textContent = '🔒 この工事・対象月は締め済みです。活動量の登録・編集・承認はできません。';
      alertEl.classList.remove('d-none');
    } else {
      alertEl.classList.add('d-none');
    }
    if (form) {
      form.querySelectorAll('input, select, button[type=button]').forEach(el => { el.disabled = locked; });
      const submit = form.querySelector('button[onclick="submitActivityForm()"]');
      if (submit) submit.disabled = locked;
    }
    buttons.forEach(el => {
      if (el.id !== 'bulkApproveBtn') el.disabled = locked;
    });
  } catch (_) {}
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
    const statusLabels = {
      draft: '下書き', site_submitted: '現場提出', branch_approved: '支店承認',
      env_approved: '環境部承認',
    };
    const statusClasses = {
      draft: 'bg-secondary', site_submitted: 'bg-info', branch_approved: 'bg-warning',
      env_approved: 'bg-success',
    };
    const approvalStatus = a.approval_status || (a.approved ? 'env_approved' : 'draft');
    statusTd.appendChild(makeBadge(
      statusLabels[approvalStatus] || approvalStatus,
      statusClasses[approvalStatus] || 'bg-secondary'
    ));
    tr.appendChild(statusTd);

    const actionTd = document.createElement('td');
    actionTd.className = 'text-center';
    actionTd.appendChild(makeActionButton('', 'bi-chat-dots', () => openComments(a.activity_id, a.item_name), 'btn-outline-secondary btn-icon', 'コメント'));
    if (approvalStatus === 'draft' && hasRole('site')) {
      actionTd.appendChild(makeActionButton('提出', 'bi-send', () => approvalAction(a.activity_id, 'submit'), 'btn-outline-info btn-sm'));
    }
    if (approvalStatus === 'site_submitted' && hasRole('reviewer')) {
      actionTd.appendChild(makeActionButton('支店承認', 'bi-check2', () => approvalAction(a.activity_id, 'approve_branch'), 'btn-outline-success btn-sm'));
      actionTd.appendChild(makeActionButton('却下', 'bi-x', () => approvalAction(a.activity_id, 'reject'), 'btn-outline-danger btn-sm'));
    }
    if (approvalStatus === 'branch_approved' && hasRole('reviewer')) {
      actionTd.appendChild(makeActionButton('環境部承認', 'bi-shield-check', () => approvalAction(a.activity_id, 'approve_env'), 'btn-outline-primary btn-sm'));
      actionTd.appendChild(makeActionButton('却下', 'bi-x', () => approvalAction(a.activity_id, 'reject'), 'btn-outline-danger btn-sm'));
    }
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

async function approvalAction(activityId, action) {
  let comment = null;
  if (action === 'reject') {
    comment = window.prompt('却下理由を入力してください', '');
    if (comment === null) return;
  }
  showLoading();
  try {
    await fetchJSON(`/api/activities/${activityId}/approval`, {
      method: 'PUT',
      body: { action, comment },
    });
    showToast('承認ステータスを更新しました', 'success');
    onActivityFilterChange();
    refreshUnreadBadge();
  } catch (err) {
    showToast(`更新失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
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
    supplier: document.getElementById('fSupplier').value.trim() || null,
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

function previousMonth(month) {
  const [y, m] = month.split('-').map(Number);
  if (m === 1) return `${y - 1}-12`;
  return `${y}-${String(m - 1).padStart(2, '0')}`;
}

async function copyPreviousMonth() {
  const projectId = document.getElementById('actProjectSelect').value;
  const month = document.getElementById('actMonthPicker').value;
  if (!projectId || !month) { showToast('工事と対象月を選択してください', 'warning'); return; }
  if (!window.confirm(`${previousMonth(month)} の活動量を ${month} へコピーしますか？（承認状態は解除されます）`)) return;
  showLoading();
  try {
    const data = await fetchJSON('/api/activities/copy-previous', {
      method: 'POST',
      body: { project_id: projectId, from_month: previousMonth(month), to_month: month },
    });
    showToast(`コピー完了: 成功${data.copied}件 / スキップ${data.skipped}件`, data.skipped ? 'warning' : 'success');
    loadActivities(projectId, month);
    refreshUnreadBadge();
  } catch (err) {
    showToast(`コピー失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function importTelematics() {
  const projectId = document.getElementById('actProjectSelect').value;
  const month = document.getElementById('actMonthPicker').value;
  if (!projectId || !month) { showToast('工事と対象月を選択してください', 'warning'); return; }
  if (!window.confirm('テレマティクスから建機稼働データを取り込みますか？')) return;
  showLoading();
  try {
    const data = await fetchJSON('/api/telematics/import', {
      method: 'POST',
      body: { project_id: projectId, target_month: month },
    });
    showToast(`取込完了: 成功${data.imported}件 / スキップ${data.skipped}件（provider: ${data.provider}）`, data.skipped ? 'warning' : 'success');
    loadActivities(projectId, month);
    refreshUnreadBadge();
  } catch (err) {
    showToast(`取込失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function convertUnit() {
  const value = parseFloat(document.getElementById('unitValue').value);
  const fromUnit = document.getElementById('unitFrom').value;
  const toUnit = document.getElementById('unitTo').value;
  if (isNaN(value)) { showToast('換算する値を入力してください', 'warning'); return; }
  try {
    const data = await fetchJSON('/api/units/convert', {
      method: 'POST',
      body: { value, from_unit: fromUnit, to_unit: toUnit },
    });
    document.getElementById('unitResult').textContent =
      `${formatNumber(data.value, 4)} ${data.from_unit} = ${formatNumber(data.converted_value, 4)} ${data.to_unit}（係数 ${formatNumber(data.conversion_factor, 6)}）`;
  } catch (err) {
    showToast(`換算失敗: ${err.message}`, 'danger');
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
  document.getElementById('eSupplier').value = activity.supplier || '';
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
    supplier: document.getElementById('eSupplier').value.trim() || null,
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

// ===== Activity Comments =====
async function openComments(activityId, itemName) {
  document.getElementById('commentActivityId').value = activityId;
  document.getElementById('commentModalLabel').textContent = `コメント: ${itemName || ''}`;
  document.getElementById('commentInput').value = '';
  bootstrap.Modal.getOrCreateInstance(document.getElementById('commentModal')).show();
  await loadComments();
}

async function loadComments() {
  const activityId = document.getElementById('commentActivityId').value;
  const list = document.getElementById('commentList');
  if (!activityId || !list) return;
  try {
    const [comments, history] = await Promise.all([
      fetchJSON(`/api/activities/${activityId}/comments`),
      fetchJSON(`/api/activities/${activityId}/history`),
    ]);
    while (list.firstChild) list.removeChild(list.firstChild);
    if (!comments || !comments.length) {
      const p = document.createElement('p');
      p.className = 'text-muted small';
      p.textContent = 'コメントはまだありません。';
      list.appendChild(p);
      return;
    }
    for (const c of comments) {
      const div = document.createElement('div');
      div.className = 'border rounded p-2 mb-2';
      const meta = document.createElement('div');
      meta.className = 'small text-muted';
      meta.textContent = `${c.author} / ${new Date(c.created_at).toLocaleString('ja-JP')}`;
      const body = document.createElement('div');
      body.className = 'small';
      body.textContent = c.content;
      div.appendChild(meta);
      div.appendChild(body);
      list.appendChild(div);
    }
    const historyList = document.getElementById('activityHistoryList');
    while (historyList.firstChild) historyList.removeChild(historyList.firstChild);
    if (!history || !history.length) {
      const p = document.createElement('p');
      p.className = 'text-muted small';
      p.textContent = '変更履歴はまだありません。';
      historyList.appendChild(p);
    } else {
      const fieldLabels = { quantity: '数量', unit: '単位', note: '備考', supplier: '供給者', source_file: '元ファイル', category: 'カテゴリ', item_name: '品目' };
      for (const h of history.slice(0, 10)) {
        const div = document.createElement('div');
        div.className = 'border rounded p-2 mb-2 small';
        const impact = (h.co2_kg_before != null && h.co2_kg_after != null)
          ? ` / CO2影響: ${formatNumber(h.co2_kg_before)}kg → ${formatNumber(h.co2_kg_after)}kg`
          : '';
        div.textContent = `${h.actor} / ${new Date(h.created_at).toLocaleString('ja-JP')}: ${fieldLabels[h.field] || h.field} ${h.old_value ?? '-'} → ${h.new_value ?? '-'}${impact}`;
        historyList.appendChild(div);
      }
    }
  } catch (err) {
    showToast(`コメント取得失敗: ${err.message}`, 'danger');
  }
}

async function addComment() {
  const activityId = document.getElementById('commentActivityId').value;
  const input = document.getElementById('commentInput');
  const content = input.value.trim();
  if (!content) { showToast('コメントを入力してください', 'warning'); return; }
  try {
    await fetchJSON(`/api/activities/${activityId}/comments`, { method: 'POST', body: { content } });
    input.value = '';
    showToast('コメントを送信しました', 'success');
    loadComments();
    refreshUnreadBadge();
  } catch (err) {
    showToast(`送信失敗: ${err.message}`, 'danger');
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

  try {
    const closes = await fetchJSON(`/api/closes?${new URLSearchParams({ project_id: projectId, target_month: month })}`);
    if (closes && closes.length) {
      const alertEl = document.getElementById('calcLockAlert');
      alertEl.textContent = '🔒 この対象月は締め済みのため再算定できません。';
      alertEl.classList.remove('d-none');
      showToast('対象月は締め済みです', 'warning');
      return;
    }
    document.getElementById('calcLockAlert').classList.add('d-none');
  } catch (_) {}

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
    await loadScopeSummary(projectId, month);
    await Promise.all([loadComparison(projectId, month), loadMissingMonths(projectId)]);
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
    loadAssistant(projectId, month);
    refreshUnreadBadge();
  } catch (err) {
    showToast(`算定失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function loadComparison(projectId, month) {
  try {
    const params = new URLSearchParams({ project_id: projectId, target_month: month });
    const data = await fetchJSON(`/api/emissions/comparison?${params}`);
    const mom = data.mom_ratio == null ? '-' : `${(data.mom_ratio * 100).toFixed(0)}%`;
    const yoy = data.yoy_ratio == null ? '-' : `${(data.yoy_ratio * 100).toFixed(0)}%`;
    document.getElementById('cmpMom').textContent = mom;
    document.getElementById('cmpYoy').textContent = yoy;
    document.getElementById('cmpPrev').textContent = data.previous_month_kg == null ? '-' : `${formatNumber(data.previous_month_t, 3)} t`;
    document.getElementById('cmpPrevYear').textContent = data.previous_year_kg == null ? '-' : `${formatNumber(data.previous_year_t, 3)} t`;
    document.getElementById('cmpMom').className = data.mom_ratio != null && data.mom_ratio > 1 ? 'fs-4 fw-bold text-danger' : 'fs-4 fw-bold text-success';
    document.getElementById('cmpYoy').className = data.yoy_ratio != null && data.yoy_ratio > 1 ? 'fs-4 fw-bold text-danger' : 'fs-4 fw-bold text-success';
  } catch (_) {
    document.getElementById('cmpMom').textContent = '-';
    document.getElementById('cmpYoy').textContent = '-';
    document.getElementById('cmpPrev').textContent = '-';
    document.getElementById('cmpPrevYear').textContent = '-';
  }
}

async function loadMissingMonths(projectId) {
  const alertEl = document.getElementById('missingMonthsAlert');
  if (!alertEl) return;
  try {
    const missing = await fetchJSON(`/api/emissions/missing-months?project_id=${projectId}`);
    const issues = missing.filter(m => m.reason === 'no_data');
    if (issues.length) {
      alertEl.textContent = `ℹ️ データ未登録の月が ${issues.length} ヶ月あります: ${issues.slice(0, 6).map(m => m.target_month).join('、')}${issues.length > 6 ? ' ほか' : ''}`;
      alertEl.classList.remove('d-none');
    } else {
      alertEl.classList.add('d-none');
    }
  } catch (_) {
    alertEl.classList.add('d-none');
  }
}

async function runScenario() {
  const projectId = document.getElementById('calcProjectSelect').value;
  const month = document.getElementById('calcMonthPicker').value;
  if (!projectId || !month) { showToast('工事と対象月を選択してください', 'warning'); return; }
  const adjustments = {
    fuel: parseFloat(document.getElementById('scFuel').value || 0),
    power: parseFloat(document.getElementById('scPower').value || 0),
    material: parseFloat(document.getElementById('scMaterial').value || 0),
    transport: parseFloat(document.getElementById('scTransport').value || 0),
    machine: parseFloat(document.getElementById('scMachine').value || 0),
    ship: parseFloat(document.getElementById('scShip').value || 0),
    waste: parseFloat(document.getElementById('scWaste').value || 0),
  };
  showLoading();
  try {
    const data = await fetchJSON('/api/emissions/scenario-simulate', {
      method: 'POST',
      body: { project_id: projectId, target_month: month, adjustments },
    });
    const el = document.getElementById('scenarioResult');
    const scopeLabels = { scope1: 'Scope1', scope2: 'Scope2', scope3: 'Scope3' };
    const scopeText = Object.entries(data.scope_after || {})
      .map(([scope, kg]) => `${scopeLabels[scope] || scope}: ${formatNumber(kg / 1000, 3)} t`)
      .join(' / ');
    el.textContent = `現状 ${formatNumber(data.current_total_kg / 1000, 3)} t → 試算 ${formatNumber(data.scenario_total_kg / 1000, 3)} t（削減 ${formatNumber(data.reduction_kg, 0)} kg / ${formatNumber(data.reduction_percent, 1)}%）／試算後 ${scopeText}`;
    el.className = data.reduction_kg > 0 ? 'small text-success' : 'small';
  } catch (err) {
    showToast(`試算失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function loadAssistant(projectId, month) {
  const container = document.getElementById('assistantList');
  if (!container) return;
  try {
    const suggestions = await fetchJSON(`/api/assistant/suggestions?${new URLSearchParams({ project_id: projectId, target_month: month })}`);
    while (container.firstChild) container.removeChild(container.firstChild);
    if (!suggestions || !suggestions.length) {
      const p = document.createElement('p');
      p.className = 'text-muted small mb-0';
      p.textContent = '提案を生成するデータがありません。';
      container.appendChild(p);
      return;
    }
    for (const s of suggestions) {
      const div = document.createElement('div');
      div.className = 'reduction-item';
      const head = document.createElement('strong');
      head.textContent = `${CATEGORY_LABELS[s.category] || s.category}: ${s.title}`;
      div.appendChild(head);
      const rationale = document.createElement('div');
      rationale.className = 'small text-muted mt-1';
      rationale.textContent = `根拠: ${s.rationale}（信頼度 ${Math.round(s.confidence * 100)}%）`;
      div.appendChild(rationale);
      const actions = document.createElement('ul');
      actions.className = 'mb-0 mt-1 small';
      for (const a of s.actions || []) {
        const li = document.createElement('li');
        li.textContent = a;
        actions.appendChild(li);
      }
      div.appendChild(actions);
      if (s.estimated_reduction_kg != null) {
        const est = document.createElement('div');
        est.className = 'small text-success';
        est.textContent = `参考: 同工種の実績では約 ${formatNumber(s.estimated_reduction_kg / 1000, 3)} t-CO2 の削減効果`;
        div.appendChild(est);
      }
      container.appendChild(div);
    }
  } catch (_) {
    const p = document.createElement('p');
    p.className = 'text-muted small mb-0';
    p.textContent = 'AI削減アシスタントを取得できませんでした。';
    container.appendChild(p);
  }
}

async function loadScopeSummary(projectId, month) {
  try {
    const params = new URLSearchParams({ project_id: projectId, target_month: month });
    const items = await fetchJSON(`/api/emissions/scope-summary?${params}`);
    const byScope = {};
    for (const item of items) byScope[item.scope] = item;
    document.getElementById('statScope1').textContent = formatNumber(byScope.scope1 ? byScope.scope1.total_co2_t : 0, 3);
    document.getElementById('statScope2').textContent = formatNumber(byScope.scope2 ? byScope.scope2.total_co2_t : 0, 3);
    document.getElementById('statScope3').textContent = formatNumber(byScope.scope3 ? byScope.scope3.total_co2_t : 0, 3);
  } catch (_) {
    document.getElementById('statScope1').textContent = '-';
    document.getElementById('statScope2').textContent = '-';
    document.getElementById('statScope3').textContent = '-';
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
  await checkReportClose(projectId, month, false);
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

async function checkReportClose(projectId, month, toast = true) {
  const badge = document.getElementById('closedBadge');
  const btn = document.getElementById('closeMonthBtn');
  try {
    const closes = await fetchJSON(`/api/closes?${new URLSearchParams({ project_id: projectId, target_month: month })}`);
    const closed = closes && closes.length > 0;
    if (badge) badge.classList.toggle('d-none', !closed);
    if (btn) {
      if (closed) {
        btn.innerHTML = '<i class="bi bi-unlock me-1" aria-hidden="true"></i>締め解除';
        btn.dataset.roleMin = 'admin';
      } else {
        btn.innerHTML = '<i class="bi bi-lock me-1" aria-hidden="true"></i>月次締め';
        btn.dataset.roleMin = 'reviewer';
      }
      updateAuthUI();
    }
    return closes || [];
  } catch (_) {
    return [];
  }
}

async function toggleMonthClose() {
  const projectId = document.getElementById('rptProjectSelect').value;
  const month = document.getElementById('rptMonthPicker').value;
  if (!projectId || !month) { showToast('工事と対象月を選択してください', 'warning'); return; }
  const closes = await checkReportClose(projectId, month, false);
  showLoading();
  try {
    if (closes.length) {
      if (!hasRole('admin')) { showToast('締め解除は管理者のみ可能です', 'warning'); hideLoading(); return; }
      await fetchJSON(`/api/closes/${closes[0].close_id}`, { method: 'DELETE' });
      showToast('締めを解除しました', 'success');
    } else {
      await fetchJSON('/api/closes', {
        method: 'POST',
        body: { project_id: projectId, target_month: month, note: 'レポート画面から締め' },
      });
      showToast('月次締めを実行しました', 'success');
    }
    checkReportClose(projectId, month, false);
    refreshUnreadBadge();
  } catch (err) {
    showToast(`締め処理失敗: ${err.message}`, 'danger');
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
    const [trend, forecast] = await Promise.all([
      fetchJSON(`/api/emissions/trend?${params}`),
      fetchJSON(`/api/emissions/forecast?project_id=${projectId}`),
    ]);
    renderTrendChart(trend, forecast);
  } catch (err) {
    showToast(`トレンドデータ取得失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

function renderTrendChart(data, forecast = null) {
  destroyChart('trend');
  const ctx = document.getElementById('trendChart').getContext('2d');
  const months = Array.isArray(data) ? data : (data.months || data.data || []);
  const labels = months.map(m => m.target_month || m.month || '');
  const values = months.map(m => Number((m.total_co2_t ?? m.co2_t ?? m.total ?? 0).toFixed(4)));
  const datasets = [{
    label: 'CO2排出量 (t-CO2)',
    data: values,
    borderColor: '#2d7d46',
    backgroundColor: 'rgba(45,125,70,0.1)',
    fill: true,
    tension: 0.3,
    pointBackgroundColor: '#2d7d46',
    pointRadius: 5,
  }];
  if (forecast && forecast.target_month && labels.length) {
    datasets.push({
      label: '翌月予測',
      data: [...labels.map(() => null), Number((forecast.forecast_total_t || 0).toFixed(4))],
      borderColor: '#e67e22',
      borderDash: [6, 4],
      pointBackgroundColor: '#e67e22',
      pointRadius: 6,
      fill: false,
    });
  }

  charts['trend'] = new Chart(ctx, {
    type: 'line',
    data: {
      labels: forecast && forecast.target_month ? [...labels, forecast.target_month] : labels,
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, position: 'bottom' },
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
  const month = document.getElementById('rptMonthPicker').value;
  if (projectId) {
    checkReportClose(projectId, month, false);
    loadMonthlyTrend();
  }
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
  setTbodyRow(tbody, makeLoadingRow(7));
  try {
    const [users, branches] = await Promise.all([
      fetchJSON('/api/users'),
      fetchJSON('/api/branches'),
    ]);
    renderUsersTable(users);
    renderBranches(branches);
    populateBranchSelect(branches);
  } catch (err) {
    setTbodyRow(tbody, makeErrorRow(7, err.message));
  }
}

function renderUsersTable(users) {
  const tbody = document.getElementById('usersTableBody');
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
  if (!users || users.length === 0) {
    tbody.appendChild(makeEmptyRow(7, '👤', 'ユーザーが登録されていません。'));
    return;
  }
  const auth = getAuth();
  for (const u of users) {
    const tr = document.createElement('tr');
    tr.appendChild(td(u.username));
    tr.appendChild(td(u.display_name || '-'));
    tr.appendChild(td(u.branch || '-'));
    const roleTd = document.createElement('td');
    roleTd.appendChild(makeBadge(ROLE_LABELS[u.role] || u.role,
      u.role === 'admin' ? 'bg-danger' : u.role === 'reviewer' ? 'bg-info' : u.role === 'site' ? 'bg-primary' : u.role === 'client' ? 'bg-dark' : 'bg-secondary'));
    tr.appendChild(roleTd);
    tr.appendChild(td(makeBadge(u.is_active ? '有効' : '無効', u.is_active ? 'bg-success' : 'bg-secondary')));
    tr.appendChild(td(new Date(u.created_at).toLocaleDateString('ja-JP')));
    const actionTd = document.createElement('td');
    actionTd.className = 'text-center';
    if (u.user_id !== auth.user.user_id) {
      actionTd.appendChild(makeActionButton('', 'bi-pencil', () => openUserModal(u), 'btn-outline-primary btn-icon', '編集'));
      if (u.role === 'client') {
        actionTd.appendChild(makeActionButton('', 'bi-folder-check', () => openAssignments(u), 'btn-outline-info btn-icon', '工事アクセス割当'));
      }
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

async function openUserModal(user = null) {
  await populateBranchesIntoSelect();
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
    document.getElementById('eUserBranch').value = user.branch || '';
    document.getElementById('eUserEmail').value = user.email || '';
    document.getElementById('eUserRole').value = user.role;
    document.getElementById('userModalLabel').textContent = 'ユーザーの編集';
  } else {
    document.getElementById('eUsername').readOnly = false;
    document.getElementById('eUserBranch').value = '';
    document.getElementById('eUserEmail').value = '';
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
  const branch = document.getElementById('eUserBranch').value;
  const email = document.getElementById('eUserEmail').value.trim() || null;
  const role = document.getElementById('eUserRole').value;
  const password = document.getElementById('eUserPassword').value;

  showLoading();
  try {
    if (editId) {
      const data = { display_name: displayName, role, branch, email };
      if (password) data.password = password;
      await fetchJSON(`/api/users/${editId}`, { method: 'PUT', body: data });
      showToast('ユーザーを更新しました', 'success');
    } else {
      if (!password) { showToast('パスワードを入力してください', 'warning'); hideLoading(); return; }
      await fetchJSON('/api/users', {
        method: 'POST',
        body: { username, display_name: displayName, role, password, branch, email },
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

async function populateBranchesIntoSelect() {
  try {
    const branches = await fetchJSON('/api/branches');
    populateBranchSelect(branches);
  } catch (_) {}
}

function populateBranchSelect(branches) {
  const sel = document.getElementById('eUserBranch');
  if (!sel) return;
  const current = sel.value;
  while (sel.firstChild) sel.removeChild(sel.firstChild);
  const none = document.createElement('option');
  none.value = '';
  none.textContent = '-- 指定なし --';
  sel.appendChild(none);
  for (const b of branches || []) {
    const opt = document.createElement('option');
    opt.value = b.name;
    opt.textContent = b.name;
    sel.appendChild(opt);
  }
  if (current) sel.value = current;
}

function renderBranches(branches) {
  const list = document.getElementById('branchList');
  if (!list) return;
  while (list.firstChild) list.removeChild(list.firstChild);
  for (const b of branches || []) {
    const span = document.createElement('span');
    span.className = 'badge bg-light text-dark border d-inline-flex align-items-center gap-1';
    const name = document.createElement('span');
    name.textContent = b.name;
    span.appendChild(name);
    if (hasRole('admin')) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn-close btn-close-sm ms-1';
      btn.setAttribute('aria-label', '削除');
      btn.style.fontSize = '0.6rem';
      btn.addEventListener('click', () => deleteBranch(b));
      span.appendChild(btn);
    }
    list.appendChild(span);
  }
}

async function addBranch() {
  const name = document.getElementById('newBranchName').value.trim();
  if (!name) { showToast('支店名を入力してください', 'warning'); return; }
  showLoading();
  try {
    await fetchJSON('/api/branches', { method: 'POST', body: { name } });
    document.getElementById('newBranchName').value = '';
    showToast('支店を追加しました', 'success');
    loadUsers();
  } catch (err) {
    showToast(`追加失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function deleteBranch(branch) {
  if (!window.confirm(`支店「${branch.name}」を削除しますか？`)) return;
  showLoading();
  try {
    await fetchJSON(`/api/branches/${branch.branch_id}`, { method: 'DELETE' });
    showToast('支店を削除しました', 'success');
    loadUsers();
  } catch (err) {
    showToast(`削除失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function openAssignments(user) {
  document.getElementById('assignUserId').value = user.user_id;
  document.getElementById('assignModalLabel').textContent = `工事アクセス割当: ${user.username}`;
  const container = document.getElementById('assignProjectList');
  while (container.firstChild) container.removeChild(container.firstChild);
  try {
    const [projects, current] = await Promise.all([
      fetchJSON('/api/projects'),
      fetchJSON(`/api/users/${user.user_id}/projects`),
    ]);
    const assigned = new Set(current.map(a => a.project_id));
    for (const p of projects) {
      const label = document.createElement('label');
      label.className = 'form-check';
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.className = 'form-check-input assign-check';
      input.value = p.project_id;
      input.checked = assigned.has(p.project_id);
      const text = document.createElement('span');
      text.className = 'form-check-label small';
      text.textContent = `${p.name}（${p.branch || '-'}）`;
      label.appendChild(input);
      label.appendChild(text);
      container.appendChild(label);
    }
    bootstrap.Modal.getOrCreateInstance(document.getElementById('assignModal')).show();
  } catch (err) {
    showToast(`割当情報の取得に失敗: ${err.message}`, 'danger');
  }
}

async function submitAssignments() {
  const userId = document.getElementById('assignUserId').value;
  const projectIds = Array.from(document.querySelectorAll('.assign-check:checked')).map(cb => cb.value);
  showLoading();
  try {
    await fetchJSON(`/api/users/${userId}/projects`, {
      method: 'PUT',
      body: { user_id: userId, project_ids: projectIds },
    });
    bootstrap.Modal.getInstance(document.getElementById('assignModal')).hide();
    showToast('工事アクセスを更新しました', 'success');
  } catch (err) {
    showToast(`更新失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

// ===== Site Feedbacks =====
async function loadFeedbacks() {
  const tbody = document.getElementById('feedbacksTableBody');
  setTbodyRow(tbody, makeLoadingRow(7));
  try {
    const projectId = document.getElementById('fbProjectSelect').value;
    const status = document.getElementById('fbStatusFilter').value;
    const params = new URLSearchParams();
    if (projectId) params.set('project_id', projectId);
    if (status) params.set('status', status);
    const qs = params.toString();
    const feedbacks = await fetchJSON(`/api/feedbacks${qs ? `?${qs}` : ''}`);
    await renderFeedbacksTable(feedbacks);
  } catch (err) {
    setTbodyRow(tbody, makeErrorRow(7, err.message));
  }
}

async function renderFeedbacksTable(feedbacks) {
  const tbody = document.getElementById('feedbacksTableBody');
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
  if (!feedbacks || feedbacks.length === 0) {
    tbody.appendChild(makeEmptyRow(7, '💬', 'フィードバックがありません。「フィードバック登録」から追加してください。'));
    return;
  }
  const projects = await fetchJSON('/api/projects').catch(() => []);
  const projectNames = {};
  for (const p of projects) projectNames[p.project_id] = p.name;
  const statusLabels = { open: '未対応', acknowledged: '対応中', resolved: '解決済み' };
  const statusClasses = { open: 'bg-danger', acknowledged: 'bg-warning', resolved: 'bg-success' };

  for (const f of feedbacks) {
    const tr = document.createElement('tr');
    tr.appendChild(td(projectNames[f.project_id] || f.project_id));
    tr.appendChild(td(f.target_month));
    const catTd = document.createElement('td');
    catTd.appendChild(makeCategoryBadge(f.category || 'other'));
    tr.appendChild(catTd);
    tr.appendChild(td(f.content));
    tr.appendChild(td(makeBadge(statusLabels[f.status] || f.status, statusClasses[f.status] || 'bg-secondary')));
    tr.appendChild(td(f.created_by));
    const actionTd = document.createElement('td');
    actionTd.className = 'text-center';
    if (hasRole('site')) {
      actionTd.appendChild(makeActionButton('', 'bi-pencil', () => openFeedbackModal(f), 'btn-outline-primary btn-icon', '編集'));
    }
    if (hasRole('reviewer')) {
      actionTd.appendChild(makeActionButton('', 'bi-trash', () => deleteFeedback(f), 'btn-outline-danger btn-icon', '削除'));
    }
    tr.appendChild(actionTd);
    tbody.appendChild(tr);
  }
}

async function openFeedbackModal(feedback = null) {
  await populateProjectSelects();
  const form = document.getElementById('feedbackForm');
  form.reset();
  document.getElementById('eFeedbackId').value = feedback ? feedback.feedback_id : '';
  if (feedback) {
    document.getElementById('eFeedbackProject').value = feedback.project_id;
    document.getElementById('eFeedbackMonth').value = feedback.target_month;
    document.getElementById('eFeedbackCategory').value = feedback.category || '';
    document.getElementById('eFeedbackContent').value = feedback.content;
    document.getElementById('eFeedbackStatus').value = feedback.status;
    document.getElementById('feedbackModalLabel').textContent = 'フィードバックの編集';
  } else {
    const now = new Date();
    document.getElementById('eFeedbackMonth').value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    document.getElementById('eFeedbackStatus').value = 'open';
    document.getElementById('feedbackModalLabel').textContent = 'フィードバック登録';
  }
  bootstrap.Modal.getOrCreateInstance(document.getElementById('feedbackModal')).show();
}

async function submitFeedbackForm() {
  const form = document.getElementById('feedbackForm');
  if (!form.checkValidity()) { form.reportValidity(); return; }
  const editId = document.getElementById('eFeedbackId').value;
  const data = {
    project_id: document.getElementById('eFeedbackProject').value,
    target_month: document.getElementById('eFeedbackMonth').value,
    category: document.getElementById('eFeedbackCategory').value || null,
    content: document.getElementById('eFeedbackContent').value.trim(),
    status: document.getElementById('eFeedbackStatus').value,
  };
  showLoading();
  try {
    if (editId) {
      await fetchJSON(`/api/feedbacks/${editId}`, { method: 'PUT', body: data });
      showToast('フィードバックを更新しました', 'success');
    } else {
      await fetchJSON('/api/feedbacks', { method: 'POST', body: data });
      showToast('フィードバックを登録しました', 'success');
    }
    bootstrap.Modal.getInstance(document.getElementById('feedbackModal')).hide();
    loadFeedbacks();
    refreshUnreadBadge();
  } catch (err) {
    showToast(`保存失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function deleteFeedback(feedback) {
  if (!window.confirm('このフィードバックを削除しますか？')) return;
  showLoading();
  try {
    await fetchJSON(`/api/feedbacks/${feedback.feedback_id}`, { method: 'DELETE' });
    showToast('フィードバックを削除しました', 'success');
    loadFeedbacks();
  } catch (err) {
    showToast(`削除失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

// ===== SBTi =====
async function loadSbti() {
  const tbody = document.getElementById('sbtiTableBody');
  setTbodyRow(tbody, makeLoadingRow(8));
  try {
    const [targets, progress] = await Promise.all([
      fetchJSON('/api/sbti/targets'),
      fetchJSON('/api/sbti/progress'),
    ]);
    renderSbtiTable(targets);
    renderSbtiProgressCards(progress);
  } catch (err) {
    setTbodyRow(tbody, makeErrorRow(8, err.message));
  }
}

function renderSbtiTable(targets) {
  const tbody = document.getElementById('sbtiTableBody');
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
  if (!targets || targets.length === 0) {
    tbody.appendChild(makeEmptyRow(8, '🎯', 'SBTi目標が未設定です。「目標登録」から追加してください。'));
    return;
  }
  const scopeLabels = { scope1: 'Scope1', scope2: 'Scope2', scope3: 'Scope3' };
  for (const t of targets) {
    const tr = document.createElement('tr');
    tr.appendChild(td(makeBadge(scopeLabels[t.scope] || t.scope,
      t.scope === 'scope1' ? 'bg-danger' : t.scope === 'scope2' ? 'bg-warning' : 'bg-info')));
    tr.appendChild(td(t.name));
    tr.appendChild(td(t.base_year));
    tr.appendChild(td(t.target_year));
    tr.appendChild(td(formatNumber(t.base_emissions_kg / 1000, 3), 'text-end'));
    tr.appendChild(td(`${formatNumber(t.reduction_percent, 1)}%`, 'text-end'));
    tr.appendChild(td(makeBadge(t.is_active ? '有効' : '無効', t.is_active ? 'bg-success' : 'bg-secondary')));
    const actionTd = document.createElement('td');
    actionTd.className = 'text-center';
    if (hasRole('admin')) {
      actionTd.appendChild(makeActionButton('', 'bi-pencil', () => openSbtiModal(t), 'btn-outline-primary btn-icon', '編集'));
      actionTd.appendChild(makeActionButton('', 'bi-trash', () => deleteSbtiTarget(t), 'btn-outline-danger btn-icon', '削除'));
    } else {
      actionTd.textContent = '-';
    }
    tr.appendChild(actionTd);
    tbody.appendChild(tr);
  }
}

function renderSbtiProgressCards(progress) {
  const container = document.getElementById('sbtiProgressCards');
  while (container.firstChild) container.removeChild(container.firstChild);
  if (!progress || !progress.length) {
    const p = document.createElement('p');
    p.className = 'text-muted small';
    p.textContent = '進捗表示対象の目標がありません。';
    container.appendChild(p);
    return;
  }
  for (const item of progress) {
    const col = document.createElement('div');
    col.className = 'col-md-4';
    const card = document.createElement('div');
    card.className = 'card h-100';
    const header = document.createElement('div');
    header.className = 'card-header';
    header.textContent = item.name;
    const body = document.createElement('div');
    body.className = 'card-body';
    const currentT = (item.current_emissions_kg / 1000).toFixed(2);
    const targetT = (item.target_emissions_kg / 1000).toFixed(2);
    const p1 = document.createElement('div');
    p1.className = 'small';
    p1.textContent = `現在 ${currentT} t-CO2 / 目標 ${targetT} t-CO2（基準 ${(item.base_emissions_kg / 1000).toFixed(2)} t-CO2）`;
    const p2 = document.createElement('div');
    p2.className = 'small mt-1';
    const badge = document.createElement('span');
    badge.className = `badge ${item.on_track ? 'bg-success' : 'bg-danger'}`;
    badge.textContent = item.on_track ? '順調' : '遅延';
    p2.appendChild(document.createTextNode(`達成率 ${Math.max(0, item.reduction_achieved_percent).toFixed(1)}% / ${item.reduction_percent}% `));
    p2.appendChild(badge);
    const progressBar = document.createElement('div');
    progressBar.className = 'progress mt-2';
    progressBar.style.height = '10px';
    const bar = document.createElement('div');
    bar.className = 'progress-bar ' + (item.on_track ? 'bg-success' : 'bg-danger');
    bar.style.width = `${Math.min(100, Math.max(0, (item.progress_ratio ?? 0) * 100))}%`;
    progressBar.appendChild(bar);
    body.appendChild(p1);
    body.appendChild(p2);
    body.appendChild(progressBar);
    card.appendChild(header);
    card.appendChild(body);
    col.appendChild(card);
    container.appendChild(col);
  }
}

function openSbtiModal(target = null) {
  const form = document.getElementById('sbtiForm');
  form.reset();
  document.getElementById('eSbtiId').value = target ? target.target_id : '';
  if (target) {
    document.getElementById('eSbtiScope').value = target.scope;
    document.getElementById('eSbtiName').value = target.name;
    document.getElementById('eSbtiDesc').value = target.description || '';
    document.getElementById('eSbtiBaseYear').value = target.base_year;
    document.getElementById('eSbtiTargetYear').value = target.target_year;
    document.getElementById('eSbtiBaseKg').value = Math.round(target.base_emissions_kg / 1000 * 100) / 100;
    document.getElementById('eSbtiReduction').value = target.reduction_percent;
    document.getElementById('sbtiModalLabel').textContent = 'SBTi目標の編集';
  } else {
    const now = new Date();
    document.getElementById('eSbtiBaseYear').value = now.getFullYear() - 1;
    document.getElementById('eSbtiTargetYear').value = now.getFullYear() + 5;
    document.getElementById('sbtiModalLabel').textContent = 'SBTi目標の新規登録';
  }
  bootstrap.Modal.getOrCreateInstance(document.getElementById('sbtiModal')).show();
}

async function submitSbtiForm() {
  const form = document.getElementById('sbtiForm');
  if (!form.checkValidity()) { form.reportValidity(); return; }
  const editId = document.getElementById('eSbtiId').value;
  const data = {
    scope: document.getElementById('eSbtiScope').value,
    name: document.getElementById('eSbtiName').value.trim(),
    description: document.getElementById('eSbtiDesc').value.trim() || null,
    base_year: parseInt(document.getElementById('eSbtiBaseYear').value, 10),
    target_year: parseInt(document.getElementById('eSbtiTargetYear').value, 10),
    base_emissions_kg: parseFloat(document.getElementById('eSbtiBaseKg').value) * 1000,
    reduction_percent: parseFloat(document.getElementById('eSbtiReduction').value),
  };
  showLoading();
  try {
    if (editId) {
      await fetchJSON(`/api/sbti/targets/${editId}`, { method: 'PUT', body: data });
      showToast('SBTi目標を更新しました', 'success');
    } else {
      await fetchJSON('/api/sbti/targets', { method: 'POST', body: data });
      showToast('SBTi目標を登録しました', 'success');
    }
    bootstrap.Modal.getInstance(document.getElementById('sbtiModal')).hide();
    loadSbti();
  } catch (err) {
    showToast(`保存失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function deleteSbtiTarget(target) {
  if (!window.confirm(`SBTi目標「${target.name}」を削除しますか？`)) return;
  showLoading();
  try {
    await fetchJSON(`/api/sbti/targets/${target.target_id}`, { method: 'DELETE' });
    showToast('SBTi目標を削除しました', 'success');
    loadSbti();
  } catch (err) {
    showToast(`削除失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

// ===== Security (2FA / OIDC) =====
async function openSecurityModal() {
  const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('securityModal'));
  modal.show();
  const statusEl = document.getElementById('securityStatus');
  const setupArea = document.getElementById('totpSetupArea');
  try {
    const me = await fetchJSON('/api/auth/me');
    if (me.is_2fa_enabled) {
      const setup = await fetchJSON('/api/auth/2fa/setup');
      document.getElementById('totpSecret').value = setup.secret;
      statusEl.textContent = '🔐 二要素認証: 有効';
      statusEl.className = 'small mb-3 text-success';
      setupArea.classList.remove('d-none');
      document.querySelector('#totpSetupArea .btn-primary').classList.add('d-none');
      document.querySelector('#totpSetupArea input').classList.add('d-none');
    } else {
      const setup = await fetchJSON('/api/auth/2fa/setup');
      document.getElementById('totpSecret').value = setup.secret;
      statusEl.textContent = '二要素認証: 未設定';
      statusEl.className = 'small mb-3 text-danger';
      setupArea.classList.remove('d-none');
      document.querySelector('#totpSetupArea .btn-primary').classList.remove('d-none');
      document.querySelector('#totpSetupArea input').classList.remove('d-none');
    }
    const oidc = await fetchJSON('/api/auth/oidc/status').catch(() => ({ enabled: false }));
    document.getElementById('oidcStatus').textContent = oidc.enabled
      ? `SSO（OIDC）: 有効（${oidc.provider || ''}）`
      : 'SSO（OIDC）: 未設定（環境変数 MIRAI_OIDC_ISSUER 等で有効化）';
  } catch (err) {
    statusEl.textContent = `セキュリティ情報の取得に失敗: ${err.message}`;
    statusEl.className = 'small mb-3 text-danger';
  }
}

async function enableTwofa() {
  const code = document.getElementById('totpCode').value.trim();
  if (!code) { showToast('認証コードを入力してください', 'warning'); return; }
  try {
    await fetchJSON('/api/auth/2fa/verify', { method: 'POST', body: { code } });
    showToast('二要素認証を有効化しました', 'success');
    openSecurityModal();
  } catch (err) {
    showToast(`有効化失敗: ${err.message}`, 'danger');
  }
}

async function disableTwofa() {
  const code = document.getElementById('totpCode').value.trim();
  if (!code) { showToast('認証コードを入力してください', 'warning'); return; }
  if (!window.confirm('二要素認証を無効化しますか？')) return;
  try {
    await fetchJSON('/api/auth/2fa/disable', { method: 'POST', body: { code } });
    showToast('二要素認証を無効化しました', 'success');
    bootstrap.Modal.getInstance(document.getElementById('securityModal')).hide();
  } catch (err) {
    showToast(`無効化失敗: ${err.message}`, 'danger');
  }
}

async function copyTotpSecret() {
  const secret = document.getElementById('totpSecret').value;
  try {
    await navigator.clipboard.writeText(secret);
    showToast('シークレットをコピーしました', 'success');
  } catch (_) {
    showToast(`シークレット: ${secret}`, 'info');
  }
}

// ===== Credits =====
async function loadCredits() {
  const tbody = document.getElementById('creditsTableBody');
  setTbodyRow(tbody, makeLoadingRow(8));
  try {
    const [credits, summary, projects] = await Promise.all([
      fetchJSON('/api/credits'),
      fetchJSON('/api/credits/summary'),
      fetchJSON('/api/projects'),
    ]);
    const projectNames = {};
    for (const p of projects) projectNames[p.project_id] = p.name;
    document.getElementById('creditAvailable').textContent = formatNumber(summary.available_tco2, 2);
    document.getElementById('creditAllocated').textContent = formatNumber(summary.allocated_tco2, 2);
    document.getElementById('creditRetired').textContent = formatNumber(summary.retired_tco2, 2);
    document.getElementById('creditTotal').textContent = formatNumber(summary.total_tco2, 2);
    renderCreditsTable(credits, projectNames);
  } catch (err) {
    setTbodyRow(tbody, makeErrorRow(8, err.message));
  }
}

function renderCreditsTable(credits, projectNames) {
  const tbody = document.getElementById('creditsTableBody');
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
  if (!credits || credits.length === 0) {
    tbody.appendChild(makeEmptyRow(8, '🎫', 'クレジットが登録されていません。'));
    return;
  }
  const typeLabels = { j_credit: 'J-クレジット', certificate: '再エネ証書', other: 'その他' };
  const statusLabels = { available: '利用可能', allocated: '充当済み', retired: '無効化' };
  const statusClasses = { available: 'bg-success', allocated: 'bg-info', retired: 'bg-secondary' };
  for (const c of credits) {
    const tr = document.createElement('tr');
    tr.appendChild(td(typeLabels[c.credit_type] || c.credit_type));
    tr.appendChild(td(c.name));
    tr.appendChild(td(c.serial_number || '-'));
    tr.appendChild(td(formatNumber(c.quantity_tco2, 2), 'text-end'));
    tr.appendChild(td(formatNumber(c.allocated_tco2 || 0, 2), 'text-end'));
    tr.appendChild(td(makeBadge(statusLabels[c.status] || c.status, statusClasses[c.status] || 'bg-secondary')));
    tr.appendChild(td(c.allocated_project_id ? projectNames[c.allocated_project_id] || c.allocated_project_id : '-'));
    const actionTd = document.createElement('td');
    actionTd.className = 'text-center';
    if (c.status === 'available' && hasRole('reviewer')) {
      actionTd.appendChild(makeActionButton('充当', 'bi-folder-check', () => allocateCredit(c), 'btn-outline-info btn-sm'));
    }
    if (c.status !== 'retired' && hasRole('admin')) {
      actionTd.appendChild(makeActionButton('無効化', 'bi-x-circle', () => retireCredit(c), 'btn-outline-warning btn-sm'));
      actionTd.appendChild(makeActionButton('', 'bi-trash', () => deleteCredit(c), 'btn-outline-danger btn-icon', '削除'));
    }
    tr.appendChild(actionTd);
    tbody.appendChild(tr);
  }
}

function openCreditModal() {
  document.getElementById('creditForm').reset();
  bootstrap.Modal.getOrCreateInstance(document.getElementById('creditModal')).show();
}

async function submitCreditForm() {
  const form = document.getElementById('creditForm');
  if (!form.checkValidity()) { form.reportValidity(); return; }
  const data = {
    credit_type: document.getElementById('eCreditType').value,
    name: document.getElementById('eCreditName').value.trim(),
    serial_number: document.getElementById('eCreditSerial').value.trim() || null,
    quantity_tco2: parseFloat(document.getElementById('eCreditQty').value),
    purchased_at: document.getElementById('eCreditDate').value || null,
    note: document.getElementById('eCreditNote').value.trim() || null,
  };
  showLoading();
  try {
    await fetchJSON('/api/credits', { method: 'POST', body: data });
    bootstrap.Modal.getInstance(document.getElementById('creditModal')).hide();
    showToast('クレジットを登録しました', 'success');
    loadCredits();
  } catch (err) {
    showToast(`登録失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function allocateCredit(credit) {
  const qty = window.prompt(`${credit.name} の充当量 (t-CO2)`, '');
  if (!qty) return;
  const projectId = window.prompt('充当先の工事IDを入力してください（工事一覧で確認可）', '');
  if (!projectId) return;
  showLoading();
  try {
    await fetchJSON(`/api/credits/${credit.credit_id}/allocate`, {
      method: 'POST',
      body: { project_id: projectId, quantity_tco2: parseFloat(qty) },
    });
    showToast('充当しました', 'success');
    loadCredits();
  } catch (err) {
    showToast(`充当失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function retireCredit(credit) {
  if (!window.confirm(`クレジット「${credit.name}」を無効化（retire）しますか？`)) return;
  showLoading();
  try {
    await fetchJSON(`/api/credits/${credit.credit_id}/retire`, { method: 'POST' });
    showToast('無効化しました', 'success');
    loadCredits();
  } catch (err) {
    showToast(`無効化失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

async function deleteCredit(credit) {
  if (!window.confirm(`クレジット「${credit.name}」を削除しますか？`)) return;
  showLoading();
  try {
    await fetchJSON(`/api/credits/${credit.credit_id}`, { method: 'DELETE' });
    showToast('削除しました', 'success');
    loadCredits();
  } catch (err) {
    showToast(`削除失敗: ${err.message}`, 'danger');
  } finally {
    hideLoading();
  }
}

// ===== Annual report =====
async function downloadAnnualReport() {
  const year = parseInt(document.getElementById('annualYear').value, 10);
  if (!year) { showToast('対象年を入力してください', 'warning'); return; }
  showLoading();
  try {
    await downloadFile(`/api/reports/annual/${year}`, `annual_report_${year}.pdf`);
    showToast('年次環境報告書をダウンロードしました', 'success');
  } catch (err) {
    showToast(`生成失敗: ${err.message}`, 'danger');
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
  document.getElementById('annualYear').value = now.getFullYear();

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
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');
    if (token) {
      setAuth({ token });
      history.replaceState({}, '', window.location.pathname);
      fetchJSON('/api/auth/me')
        .then(user => {
          const auth = getAuth();
          auth.user = user;
          setAuth(auth);
          updateAuthUI();
          showToast('SSOでログインしました', 'success');
          navigateTo('dashboard');
          refreshUnreadBadge();
        })
        .catch(() => showLoginModal());
    } else {
      showLoginModal();
    }
  }
});
