// ============================================================
// FinSight AI — Frontend (Production)
// Polling 30s + XSS escape + retry backoff + CSRF-free
// + Member Management + Participant Selector
// ============================================================

const API = '/api';
const POLL_INTERVAL_MS = 30000;
let currentUser = null;
let groupsCache = [];
let pollInterval = null;
let currentGroupId = null;
let consecutiveErrors = 0;
let currentGroupMembers = [];
let selectedParticipants = new Set();

// ============================================================
// XSS ESCAPE
// ============================================================
function escapeHtml(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  })[c]);
}

// ============================================================
// HTTP Helper
// ============================================================
async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    cache: 'no-store',
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

function money(n) {
  return '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

function shortMoney(n) {
  n = Number(n || 0);
  if (n >= 10000000) return '₹' + (n / 10000000).toFixed(1) + 'Cr';
  if (n >= 100000) return '₹' + (n / 100000).toFixed(1) + 'L';
  if (n >= 1000) return '₹' + (n / 1000).toFixed(1) + 'K';
  return money(n);
}

// ============================================================
// Toast
// ============================================================
function showToast(msg, type = 'info') {
  const toast = document.createElement('div');
  toast.style.cssText = `
    position:fixed; top:24px; right:24px; z-index:99999;
    background:${type === 'error' ? '#ef5b67' : type === 'success' ? '#20a779' : '#101525'};
    color:#fff; padding:13px 18px; border-radius:12px; font-size:12px;
    box-shadow:0 10px 30px rgba(0,0,0,.2); font-family:inherit;
    max-width:320px;
  `;
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = '.3s';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ============================================================
// DASHBOARD
// ============================================================
async function loadDashboard() {
  try {
    const d = await api('/dashboard/');

    document.getElementById('dashBalance').textContent = money(d.balance);
    document.getElementById('dashIncome').textContent = money(d.income);
    document.getElementById('dashExpenses').textContent = money(d.total_expenses);

    const spentPct = d.income ? Math.min((d.total_expenses / d.income) * 100, 100) : 0;
    document.getElementById('dashProgress').style.width = spentPct + '%';
    document.getElementById('dashProgressLabel').textContent =
      `${spentPct.toFixed(0)}% of your income spent this month`;

    const predValue = d.prediction.prediction;
    if (predValue > 0) {
      document.getElementById('dashPrediction').textContent = money(predValue);
      document.getElementById('dashConfidence').textContent =
        Math.round(d.prediction.confidence * 100) + '% confidence';
      document.getElementById('dashConfidence').style.background = '';
      document.getElementById('dashConfidence').style.color = '';
    } else {
      document.getElementById('dashPrediction').textContent = 'Learning...';
      document.getElementById('dashConfidence').textContent = 'AI training';
      document.getElementById('dashConfidence').style.background = '#fff0df';
      document.getElementById('dashConfidence').style.color = '#ed922e';
    }

    const gap = predValue - d.total_expenses;
    let predMsg;
    if (predValue === 0) {
      predMsg = '<b>AI is learning your spending patterns.</b> Predictions unlock after 2-3 months of data.';
    } else if (gap > 0) {
      predMsg = `Predicted: <b>${money(predValue)}</b> (${money(gap)} above current). Trend: <b>${escapeHtml(d.prediction.trend)}</b>.`;
    } else {
      predMsg = `You're within predicted limits. Trend: <b>${escapeHtml(d.prediction.trend)}</b>.`;
    }
    document.getElementById('dashPredictionText').innerHTML = predMsg;

    const predPct = d.income ? Math.min((predValue / d.income) * 100, 100) : 0;
    document.getElementById('dashPredBar').style.width = predPct + '%';
    document.getElementById('dashPredBarLabel').textContent = shortMoney(predValue);

    document.getElementById('statIncome').textContent = money(d.income);
    document.getElementById('statExpenses').textContent = money(d.total_expenses);
    document.getElementById('statSavings').textContent = d.savings_rate + '%';
    document.getElementById('statExpenseCount').textContent =
      `${d.category_breakdown.length} categories`;

    const warnings = d.alerts.filter(a => a.type === 'warning').length;
    const dangers = d.alerts.filter(a => a.type === 'danger').length;
    const total = warnings + dangers;
    document.getElementById('statRisk').textContent =
      dangers > 0 ? 'High' : warnings > 0 ? 'Medium' : 'Low';
    document.getElementById('statRiskDetail').textContent =
      total === 0 ? 'All categories healthy ✓' : `${total} categories need attention`;

    renderCategoryDonut(d.category_breakdown, d.total_expenses);
    renderRecentTransactions(d.recent_transactions);
    renderAlerts(d.alerts);

    const trends = await api('/analytics/trends?months=6');
    renderTrendChart(trends.trends, d.prediction);
  } catch (e) {
    console.error('Dashboard:', e);
    throw e;
  }
}

function renderCategoryDonut(breakdown, total) {
  const donut = document.getElementById('donutChart');
  const list = document.getElementById('categoryList');
  document.getElementById('donutTotal').textContent = shortMoney(total);

  if (!breakdown.length) {
    donut.style.background = '#f0f1f5';
    list.innerHTML = '<p style="font-size:11px;color:#999">No expenses yet.</p>';
    return;
  }

  const colors = {
    Food: '#665eff', Travel: '#5eb1ff', Shopping: '#ffb15c',
    Bills: '#ef6e8a', Entertainment: '#20a779', Other: '#d5d9e1'
  };

  let cumulative = 0;
  const stops = breakdown.map(b => {
    const start = cumulative;
    cumulative += b.percentage;
    return `${colors[b.category] || '#c5cad4'} ${start}% ${cumulative}%`;
  }).join(', ');
  donut.style.background = `conic-gradient(${stops})`;

  list.innerHTML = breakdown.map(b => `
    <div>
      <span class="cat-dot" style="background:${colors[b.category] || '#c5cad4'}"></span>
      <span>${escapeHtml(b.category)}</span>
      <b>${money(b.amount)}</b>
      <small>${b.percentage}%</small>
    </div>`).join('');
}

function renderRecentTransactions(transactions) {
  const el = document.getElementById('recentTransactions');
  if (!transactions.length) {
    el.innerHTML = '<p style="font-size:11px;color:#999">No transactions yet.</p>';
    return;
  }
  el.innerHTML = transactions.map(t => `
    <div class="transaction-row">
      <div class="merchant-icon">${escapeHtml((t.merchant || '?')[0])}</div>
      <div>
        <b>${escapeHtml(t.merchant)}</b>
        <small>${escapeHtml(t.description)} · ${escapeHtml(t.date)}</small>
      </div>
      <span class="tag">${escapeHtml(t.category)}</span>
      <span class="amount">-${money(t.amount)}</span>
    </div>`).join('');
}

function renderAlerts(alerts) {
  const el = document.getElementById('alertsList');
  document.getElementById('alertCount').textContent = alerts.length;
  if (!alerts.length) {
    el.innerHTML = '<p style="font-size:11px;color:#999">No alerts. All good! ✓</p>';
    return;
  }
  el.innerHTML = alerts.map(a => `
    <div class="alert-item ${a.type === 'danger' ? 'danger' : ''}">
      <span class="alert-symbol">${a.type === 'danger' ? '!' : '✦'}</span>
      <div>
        <b>${escapeHtml(a.category || 'Alert')}</b>
        <p>${escapeHtml(a.message)}</p>
      </div>
    </div>`).join('');
}

function renderTrendChart(trends, prediction) {
  const svg = document.getElementById('trendChart');
  const xAxis = document.getElementById('trendXAxis');
  const yAxis = document.getElementById('trendYAxis');
  const actualLine = document.getElementById('actualLine');
  const predLine = document.getElementById('predLine');

  if (!trends.length) return;

  const values = trends.map(t => t.total);
  const predValue = prediction.prediction;
  const maxVal = Math.max(...values, predValue, 100) * 1.15;

  const steps = [1, 0.75, 0.5, 0.25, 0];
  yAxis.innerHTML = steps.map(s => `<span>${shortMoney(maxVal * s)}</span>`).join('');

  const labels = trends.slice(-5).map(t => t.label);
  xAxis.innerHTML = labels.map(l => `<span>${escapeHtml(l)}</span>`).join('');

  const W = 700, H = 200;
  const n = trends.length;
  const xStep = n > 1 ? W / (n - 1) : W;
  const toPoint = (val, i) => `${i * xStep},${H - (val / maxVal) * H}`;

  actualLine.setAttribute('points', trends.map((t, i) => toPoint(t.total, i)).join(' '));

  const predPoints = trends.map((t, i) => toPoint(t.total, i));
  const lastX = (n - 1) * xStep;
  predPoints.push(`${lastX + 60},${H - (predValue / maxVal) * H}`);
  predLine.setAttribute('points', predPoints.join(' '));

  svg.setAttribute('viewBox', predPoints.length > 0 ? `0 0 ${lastX + 100} 260` : '0 0 700 260');
}

// ============================================================
// TRANSACTIONS
// ============================================================
async function loadTransactions() {
  try {
    const category = document.getElementById('filterCategory')?.value;
    const search = document.getElementById('searchInput')?.value || '';
    const params = new URLSearchParams();
    if (category && category !== 'All categories') params.append('category', category);
    if (search) params.append('search', search);

    const data = await api('/expenses/?' + params.toString());
    const body = document.getElementById('transactionTable');

    if (!data.expenses.length) {
      body.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:30px;color:#999">No transactions found.</td></tr>';
      return;
    }

    body.innerHTML = data.expenses.map(t => `
      <tr>
        <td>
          <strong>${escapeHtml(t.merchant)}</strong>
          <br><small>${escapeHtml(t.description)}${t.is_anomaly ? ' ⚠' : ''}${t.receipt_path ? ' 📎' : ''}</small>
        </td>
        <td>${escapeHtml(t.date)}</td>
        <td><span class="category-pill">${escapeHtml(t.category)}</span></td>
        <td>${escapeHtml(t.source)}</td>
        <td><strong>-${money(t.amount)}</strong></td>
        <td><span class="confidence-pill">${escapeHtml(t.ai_confidence)}</span></td>
        <td>
          ${t.receipt_path
            ? `<button class="more" onclick="viewReceipt(${t.id})" title="View Receipt">📎</button>`
            : `<button class="more" onclick="openReceiptUpload(${t.id})" title="Upload Receipt">+📎</button>`
          }
          <button class="more" onclick="openComments(${t.id})" title="Comments">💬</button>
          <button class="more" onclick="deleteExpense(${t.id})" title="Delete">🗑</button>
        </td>
      </tr>`).join('');
  } catch (e) {
    console.error('Transactions:', e);
    throw e;
  }
}

async function deleteExpense(id) {
  if (!confirm('Delete this transaction?')) return;
  try {
    await api('/expenses/' + id, { method: 'DELETE' });
    showToast('Deleted', 'success');
    loadTransactions();
    loadDashboard();
  } catch (e) { showToast(e.message, 'error'); }
}
window.deleteExpense = deleteExpense;

// ============================================================
// GROUPS
// ============================================================
async function loadGroups() {
  try {
    const data = await api('/groups/');
    groupsCache = data.groups;
    const grid = document.getElementById('groupsGrid');
    const select = document.getElementById('expenseGroup');

    if (select) {
      select.innerHTML = '<option value="">Personal (no group)</option>' +
        groupsCache.map(g => `<option value="${g.id}">${escapeHtml(g.name)}</option>`).join('');
    }

    if (!groupsCache.length) {
      grid.innerHTML = '<p style="font-size:11px;color:#999;padding:20px">No groups yet. Create one!</p>';
      return;
    }

    grid.innerHTML = groupsCache.map(g => `
      <div class="budget-card" style="cursor:pointer" onclick="viewGroup(${g.id})">
        <div class="b-top">
          <h3>◈ &nbsp;${escapeHtml(g.name)}</h3>
          <span class="muted">${g.member_count} members</span>
        </div>
        <p style="font-size:11px;color:#8b929d;margin:12px 0 0;line-height:1.5">
          ${escapeHtml(g.description || 'No description')}
        </p>
        <div class="budget-foot" style="margin-top:14px">
          <span>Created ${escapeHtml(g.created_at)}</span>
          <span style="color:#635bff;font-weight:700">Open →</span>
        </div>
      </div>`).join('');
  } catch (e) {
    console.error('Groups:', e);
    throw e;
  }
}

async function viewGroup(id) {
  currentGroupId = id;
  try {
    showModal('<div style="padding:40px;text-align:center;color:#8b929d">Loading group dashboard...</div>');

    const data = await api('/groups/' + id + '/dashboard');
    const html = renderGroupDashboard(data);

    const modal = document.getElementById('genericModal');
    if (modal) modal.remove();

    const m = document.createElement('div');
    m.id = 'genericModal';
    m.className = 'modal open';
    m.innerHTML = `<div class="modal-card group-dashboard-modal">
      <button class="close" onclick="this.closest('.modal').remove()">×</button>
      ${html}
    </div>`;
    m.addEventListener('click', e => { if (e.target === m) m.remove(); });
    document.body.appendChild(m);
  } catch (e) {
    showToast(e.message, 'error');
  }
}
window.viewGroup = viewGroup;

function renderGroupDashboard(data) {
  const { group, balances, suggested_settlements, leaderboard, activities, heatmap, story, expenses } = data;

  const isAdmin = (group.members || []).some(
    m => m.user && m.user.id === currentUser?.id && m.role === 'admin'
  );

  const header = `
    <div class="gd-header">
      <div>
        <h2>◈ ${escapeHtml(group.name)}</h2>
        <p>${escapeHtml(group.description || 'Group details')} · ${group.member_count} members</p>
      </div>
      <div style="display:flex;gap:8px">
        ${isAdmin ? `<button class="primary-btn" onclick="closeGroupDashboardAndOpenSettings(${group.id})" style="background:#635bff">⚙ Manage</button>` : ''}
      </div>
    </div>
  `;

  let storyHTML = '';
  if (story && story.txn_count > 0) {
    storyHTML = `
      <div class="gd-section">
        <div class="gd-section-title">🎬 This Month's Story</div>
        <div class="story-card">
          <div class="story-brand">FinSight AI · ${escapeHtml(story.month_label)}</div>
          <div class="story-total">${money(story.total)}</div>
          <div class="story-subtitle">across ${story.txn_count} transactions</div>
          <div class="story-stats">
            ${story.top_spender ? `
              <div class="story-stat">
                <span>🥇 Top Spender</span>
                <b>${escapeHtml(story.top_spender.name)}</b>
                <small>${money(story.top_spender.amount)}</small>
              </div>` : ''}
            ${story.top_category ? `
              <div class="story-stat">
                <span>🏆 Top Category</span>
                <b>${escapeHtml(story.top_category.name)}</b>
                <small>${story.top_category.percentage}%</small>
              </div>` : ''}
            ${story.most_active_day ? `
              <div class="story-stat">
                <span>📅 Most Active</span>
                <b>${escapeHtml(story.most_active_day.date || '-')}</b>
                <small>${story.most_active_day.txn_count} txns</small>
              </div>` : ''}
          </div>
        </div>
      </div>
    `;
  }

  const medals = ['🥇', '🥈', '🥉'];
  const leaderboardHTML = leaderboard.length ? leaderboard.map((l, i) => `
    <div class="gd-leader-row">
      <div class="gd-rank">${medals[i] || '#' + (i + 1)}</div>
      <div class="gd-avatar">${escapeHtml(l.user.avatar)}</div>
      <div class="gd-leader-info">
        <b>${escapeHtml(l.user.name)}${l.user.id === currentUser?.id ? ' (You)' : ''}</b>
        <small>${l.txn_count} transactions</small>
      </div>
      <div class="gd-leader-stats">
        <div class="gd-stat-main">${money(l.total_paid)}</div>
        <div class="gd-stat-net ${l.net > 0 ? 'positive' : l.net < 0 ? 'negative' : ''}">
          ${l.net > 0 ? '+' : ''}${money(l.net)}
        </div>
      </div>
    </div>
  `).join('') : '<p style="font-size:11px;color:#999">No activity yet</p>';

  const settlementsHTML = suggested_settlements.length ? suggested_settlements.map(s => `
    <div class="gd-settlement">
      <div class="gd-avatar">${escapeHtml(s.from_user.avatar || 'U')}</div>
      <div class="gd-settlement-info">
        <b>${escapeHtml(s.from_user.name)}</b> → <b>${escapeHtml(s.to_user.name)}</b>
      </div>
      <div class="gd-settlement-amount">${money(s.amount)}</div>
    </div>
  `).join('') : '<p style="font-size:11px;color:#20a779">✓ All settled up!</p>';

  const activitiesHTML = activities.length ? activities.map(a => `
    <div class="gd-activity">
      <div class="gd-activity-dot"></div>
      <div class="gd-activity-content">
        <div class="gd-activity-text">${formatActivity(a)}</div>
        <div class="gd-activity-time">${escapeHtml(a.time_ago)}</div>
      </div>
    </div>
  `).join('') : '<p style="font-size:11px;color:#999">No activity yet</p>';

  const heatmapHTML = renderHeatmap(heatmap);

  const expensesHTML = expenses.length ? expenses.map(e => `
    <div class="gd-expense-card">
      <div class="gd-expense-header">
        <div class="gd-avatar" style="background:#f1f2f8;color:#635bff">
          ${escapeHtml((e.merchant || '?')[0])}
        </div>
        <div class="gd-expense-info">
          <b>${escapeHtml(e.merchant)}</b>
          <small>${escapeHtml(e.description)} · paid by ${escapeHtml(e.paid_by.name)}</small>
        </div>
        <div class="gd-expense-amount">-${money(e.amount)}</div>
      </div>
      <div class="gd-expense-tags">
        <span class="category-pill">${escapeHtml(e.category)}</span>
        ${e.receipt_path
          ? `<button class="receipt-badge" onclick="viewReceipt(${e.id})" style="cursor:pointer;border:0;font-family:inherit">📎 View Receipt</button>`
          : ''}
        <button class="gd-btn-small" onclick="openComments(${e.id})">💬 Comments</button>
        <button class="gd-btn-small" onclick="openReceiptUpload(${e.id})">📎 Add Receipt</button>
      </div>
    </div>
  `).join('') : '<p style="font-size:11px;color:#999">No expenses yet</p>';

  return `
    ${header}
    <div class="gd-grid">
      <div class="gd-section">
        <div class="gd-section-title">🏆 Leaderboard</div>
        <div class="gd-leaderboard">${leaderboardHTML}</div>
      </div>
      <div class="gd-section">
        <div class="gd-section-title">💡 Smart Settlements</div>
        <div class="gd-settlements">${settlementsHTML}</div>
      </div>
    </div>
    ${storyHTML}
    <div class="gd-section">
      <div class="gd-section-title">🔥 Spending Heatmap (Last 12 weeks)</div>
      ${heatmapHTML}
    </div>
    <div class="gd-grid">
      <div class="gd-section">
        <div class="gd-section-title">📅 Activity Timeline</div>
        <div class="gd-timeline">${activitiesHTML}</div>
      </div>
      <div class="gd-section">
        <div class="gd-section-title">💰 Recent Expenses</div>
        <div class="gd-expenses-list">${expensesHTML}</div>
      </div>
    </div>
  `;
}

function closeGroupDashboardAndOpenSettings(groupId) {
  document.getElementById('genericModal')?.remove();
  setTimeout(() => openGroupSettings(groupId), 200);
}
window.closeGroupDashboardAndOpenSettings = closeGroupDashboardAndOpenSettings;

function formatActivity(a) {
  const name = `<b>${escapeHtml(a.user.name)}</b>`;
  const meta = a.meta || {};
  switch (a.action) {
    case 'group_created': return `${name} created the group`;
    case 'member_added': return `${name} added <b>${escapeHtml(meta.member_name || 'a member')}</b>`;
    case 'member_removed': return `${name} removed a member`;
    case 'expense_added':
      return `${name} added <b>${escapeHtml(meta.description || 'an expense')}</b> (${money(meta.amount || 0)})`;
    case 'expense_deleted': return `${name} deleted an expense`;
    case 'settlement_initiated': return `${name} initiated a settlement (${money(meta.amount || 0)})`;
    case 'settlement_completed':
      return `${name} completed a settlement (${money(meta.amount || 0)})`;
    case 'settlement_rejected': return `${name} rejected a settlement`;
    case 'comment_added': return `${name} commented`;
    case 'receipt_uploaded': return `${name} uploaded a receipt`;
    default: return `${name} did something`;
  }
}

function renderHeatmap(heatmap) {
  if (!heatmap || !heatmap.days || !heatmap.days.length) {
    return '<p style="font-size:11px;color:#999">No data</p>';
  }

  const days = heatmap.days;
  const weeks = [];
  let currentWeek = [];

  const firstDay = new Date(days[0].date).getDay();
  for (let i = 0; i < firstDay; i++) currentWeek.push(null);

  days.forEach((d) => {
    currentWeek.push(d);
    if (currentWeek.length === 7) {
      weeks.push(currentWeek);
      currentWeek = [];
    }
  });
  if (currentWeek.length > 0) {
    while (currentWeek.length < 7) currentWeek.push(null);
    weeks.push(currentWeek);
  }

  const dayLabels = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

  return `
    <div class="heatmap-container">
      <div class="heatmap-day-labels">
        ${dayLabels.map(d => `<span>${d}</span>`).join('')}
      </div>
      <div class="heatmap-grid">
        ${weeks.map(week => `
          <div class="heatmap-week">
            ${week.map(day => {
              if (!day) return `<div class="heatmap-cell empty"></div>`;
              return `<div class="heatmap-cell level-${day.level}" title="${escapeHtml(day.date)}: ${money(day.amount)}"></div>`;
            }).join('')}
          </div>
        `).join('')}
      </div>
      <div class="heatmap-legend">
        <span>Less</span>
        <div class="heatmap-cell level-0"></div>
        <div class="heatmap-cell level-1"></div>
        <div class="heatmap-cell level-2"></div>
        <div class="heatmap-cell level-3"></div>
        <div class="heatmap-cell level-4"></div>
        <span>More</span>
      </div>
    </div>
  `;
}

// ============================================================
// ⭐ GROUP MEMBER MANAGEMENT
// ============================================================
async function openGroupSettings(groupId) {
  try {
    const group = await api('/groups/' + groupId);
    currentGroupMembers = group.members || [];

    document.getElementById('groupModalTitle').textContent = '◈ ' + group.name;
    document.getElementById('groupModalSubtitle').textContent =
      `${group.member_count} members · Created ${group.created_at}`;

    document.getElementById('groupName').value = group.name;
    document.getElementById('groupDesc').value = group.description || '';
    document.getElementById('groupName').disabled = true;
    document.getElementById('groupDesc').disabled = true;

    document.getElementById('groupAddMemberSection').style.display = 'block';
    document.getElementById('saveGroup').textContent = 'Close';
    document.getElementById('saveGroup').onclick = () => {
      document.getElementById('groupModal').classList.remove('open');
      document.getElementById('groupName').disabled = false;
      document.getElementById('groupDesc').disabled = false;
      window._currentGroupId = null;
    };

    renderGroupMemberList();
    window._currentGroupId = groupId;

    document.getElementById('groupModal').classList.add('open');
  } catch (e) {
    showToast(e.message, 'error');
  }
}
window.openGroupSettings = openGroupSettings;

function renderGroupMemberList() {
  const el = document.getElementById('groupMemberList');
  const isAdmin = currentGroupMembers.some(
    m => m.user && m.user.id === currentUser?.id && m.role === 'admin'
  );

  if (!currentGroupMembers.length) {
    el.innerHTML = '<p style="font-size:11px;color:#999">No members yet</p>';
    return;
  }

  el.innerHTML = currentGroupMembers.map(m => `
    <div class="member-row">
      <div class="gd-avatar">${escapeHtml(m.user.avatar)}</div>
      <div class="member-info">
        <b>${escapeHtml(m.user.name)}${m.user.id === currentUser.id ? ' (You)' : ''}</b>
        <small>${escapeHtml(m.user.email)}</small>
      </div>
      <span class="member-role ${m.role === 'admin' ? 'admin' : ''}">
        ${m.role === 'admin' ? '★ Admin' : 'Member'}
      </span>
      ${(isAdmin && m.user.id !== currentUser.id) ? `
        <button class="member-remove" onclick="removeMemberFromGroup(${m.user.id})" title="Remove">×</button>
      ` : ''}
    </div>
  `).join('');
}

async function addMemberToGroup() {
  const emailInput = document.getElementById('addMemberEmail');
  const status = document.getElementById('addMemberStatus');
  const email = emailInput.value.trim().toLowerCase();

  if (!email) {
    status.innerHTML = '<span style="color:#ef5b67">Email required</span>';
    return;
  }

  const groupId = window._currentGroupId;
  if (!groupId) {
    status.innerHTML = '<span style="color:#ef5b67">No group selected</span>';
    return;
  }

  status.innerHTML = '<span style="color:#635bff">Adding...</span>';

  try {
    await api(`/groups/${groupId}/members`, {
      method: 'POST',
      body: { email }
    });

    status.innerHTML = '<span style="color:#20a779">✓ Member added!</span>';
    emailInput.value = '';

    const group = await api('/groups/' + groupId);
    currentGroupMembers = group.members || [];
    renderGroupMemberList();

    loadGroups();
  } catch (e) {
    status.innerHTML = `<span style="color:#ef5b67">${escapeHtml(e.message)}</span>`;
  }
}
window.addMemberToGroup = addMemberToGroup;

async function removeMemberFromGroup(userId) {
  if (!confirm('Remove this member? Their splits in this group will be deleted.')) return;

  const groupId = window._currentGroupId;
  if (!groupId) return;

  try {
    await api(`/groups/${groupId}/members/${userId}`, { method: 'DELETE' });
    showToast('Member removed', 'success');

    const group = await api('/groups/' + groupId);
    currentGroupMembers = group.members || [];
    renderGroupMemberList();
    loadGroups();
  } catch (e) {
    showToast(e.message, 'error');
  }
}
window.removeMemberFromGroup = removeMemberFromGroup;

function resetGroupModal() {
  document.getElementById('groupModalTitle').textContent = 'Create group';
  document.getElementById('groupModalSubtitle').textContent = 'Create a group to split expenses.';
  document.getElementById('groupName').value = '';
  document.getElementById('groupDesc').value = '';
  document.getElementById('groupName').disabled = false;
  document.getElementById('groupDesc').disabled = false;
  document.getElementById('groupAddMemberSection').style.display = 'none';
  document.getElementById('saveGroup').textContent = 'Create group';
  window._currentGroupId = null;
}
window.resetGroupModal = resetGroupModal;

// ============================================================
// ⭐ PARTICIPANT SELECTOR
// ============================================================
async function onExpenseGroupChange() {
  const groupId = document.getElementById('expenseGroup').value;
  const section = document.getElementById('participantSection');

  if (!groupId) {
    section.style.display = 'none';
    selectedParticipants.clear();
    return;
  }

  section.style.display = 'block';

  try {
    const group = await api('/groups/' + groupId);
    const members = group.members || [];

    selectedParticipants.clear();
    members.forEach(m => {
      if (m.user) selectedParticipants.add(m.user.id);
    });

    renderParticipantList(members);
  } catch (e) {
    section.style.display = 'none';
    showToast('Failed to load group members', 'error');
  }
}
window.onExpenseGroupChange = onExpenseGroupChange;

function renderParticipantList(members) {
  const el = document.getElementById('participantList');
  if (!el) return;

  el.innerHTML = members.map(m => {
    const u = m.user;
    const checked = selectedParticipants.has(u.id);
    return `
      <label class="participant-item ${checked ? 'selected' : ''}">
        <input type="checkbox"
               ${checked ? 'checked' : ''}
               onchange="toggleParticipant(${u.id})">
        <div class="gd-avatar" style="width:28px;height:28px;font-size:10px">
          ${escapeHtml(u.avatar)}
        </div>
        <div class="participant-info">
          <b>${escapeHtml(u.name)}${u.id === currentUser.id ? ' (You)' : ''}</b>
          ${m.role === 'admin' ? '<small>★ Admin</small>' : ''}
        </div>
      </label>
    `;
  }).join('');

  updateParticipantSummary();
}

async function toggleParticipant(userId) {
  if (selectedParticipants.has(userId)) {
    selectedParticipants.delete(userId);
  } else {
    selectedParticipants.add(userId);
  }

  const groupId = document.getElementById('expenseGroup').value;
  if (groupId) {
    try {
      const group = await api('/groups/' + groupId);
      renderParticipantList(group.members || []);
    } catch (e) {}
  }
}
window.toggleParticipant = toggleParticipant;

async function selectAllParticipants() {
  const groupId = document.getElementById('expenseGroup').value;
  if (!groupId) return;
  try {
    const group = await api('/groups/' + groupId);
    selectedParticipants.clear();
    (group.members || []).forEach(m => {
      if (m.user) selectedParticipants.add(m.user.id);
    });
    renderParticipantList(group.members || []);
  } catch (e) {}
}
window.selectAllParticipants = selectAllParticipants;

async function clearAllParticipants() {
  selectedParticipants.clear();
  if (currentUser) selectedParticipants.add(currentUser.id);

  const groupId = document.getElementById('expenseGroup').value;
  if (groupId) {
    try {
      const group = await api('/groups/' + groupId);
      renderParticipantList(group.members || []);
    } catch (e) {}
  }
}
window.clearAllParticipants = clearAllParticipants;

function updateParticipantSummary() {
  const el = document.getElementById('participantSummary');
  if (!el) return;

  const amount = Number(document.getElementById('expenseAmount')?.value) || 0;
  const count = selectedParticipants.size;

  if (count === 0) {
    el.innerHTML = '<span style="color:#ef5b67">⚠ Select at least 1 participant</span>';
    return;
  }

  const each = amount / count;
  el.innerHTML = `<b>${count}</b> selected · Each pays <b>${money(each)}</b>`;
}

// ============================================================
// COMMENTS
// ============================================================
async function openComments(expenseId) {
  try {
    const data = await api(`/expenses/${expenseId}/comments`);
    const comments = data.comments || [];

    const modal = document.getElementById('genericModal');
    if (modal) modal.remove();

    const m = document.createElement('div');
    m.id = 'genericModal';
    m.className = 'modal open';
    m.innerHTML = `<div class="modal-card">
      <button class="close" onclick="this.closest('.modal').remove()">×</button>
      <h2>💬 Comments</h2>
      <div class="comments-list" id="commentsList">
        ${comments.length ? comments.map(c => renderComment(c)).join('')
          : '<p style="font-size:11px;color:#999;padding:12px">No comments yet.</p>'}
      </div>
      <div class="comment-input-row">
        <input id="newCommentInput" placeholder="Add a comment..." maxlength="1000"
               style="flex:1;padding:10px;border:1px solid #e9ebf0;border-radius:10px;font:inherit;font-size:12px;outline:none">
        <button class="primary-btn" onclick="postComment(${expenseId})">Post</button>
      </div>
    </div>`;
    m.addEventListener('click', e => { if (e.target === m) m.remove(); });
    document.body.appendChild(m);

    document.getElementById('newCommentInput').focus();
    document.getElementById('newCommentInput').addEventListener('keypress', e => {
      if (e.key === 'Enter') postComment(expenseId);
    });
  } catch (e) {
    showToast(e.message, 'error');
  }
}
window.openComments = openComments;

function renderComment(c) {
  return `
    <div class="comment-item">
      <div class="gd-avatar" style="width:28px;height:28px;font-size:10px">${escapeHtml(c.user.avatar)}</div>
      <div class="comment-content">
        <b>${escapeHtml(c.user.name)}</b>
        <p>${escapeHtml(c.comment)}</p>
        <small>${escapeHtml(c.time_ago)}</small>
      </div>
    </div>
  `;
}

async function postComment(expenseId) {
  const input = document.getElementById('newCommentInput');
  const text = input.value.trim();
  if (!text) return;

  try {
    await api(`/expenses/${expenseId}/comments`, {
      method: 'POST',
      body: { comment: text }
    });
    input.value = '';
    const data = await api(`/expenses/${expenseId}/comments`);
    document.getElementById('commentsList').innerHTML =
      data.comments.map(x => renderComment(x)).join('');
  } catch (e) {
    showToast(e.message, 'error');
  }
}
window.postComment = postComment;

// ============================================================
// RECEIPT
// ============================================================
async function openReceiptUpload(expenseId) {
  const modal = document.getElementById('genericModal');
  if (modal) modal.remove();

  const m = document.createElement('div');
  m.id = 'genericModal';
  m.className = 'modal open';
  m.innerHTML = `<div class="modal-card">
    <button class="close" onclick="this.closest('.modal').remove()">×</button>
    <h2>📎 Upload Receipt</h2>
    <p>Attach a photo or PDF (max 5 MB)</p>
    <input type="file" id="receiptFile" accept="image/jpeg,image/png,image/gif,application/pdf"
           style="width:100%;padding:10px;border:1px solid #e9ebf0;border-radius:10px;font-size:12px">
    <button class="primary-btn full" onclick="uploadReceipt(${expenseId})" style="margin-top:14px">
      Upload
    </button>
  </div>`;
  m.addEventListener('click', e => { if (e.target === m) m.remove(); });
  document.body.appendChild(m);
}
window.openReceiptUpload = openReceiptUpload;

async function uploadReceipt(expenseId) {
  const fileInput = document.getElementById('receiptFile');
  if (!fileInput.files.length) {
    showToast('Select a file first', 'error');
    return;
  }

  const file = fileInput.files[0];
  if (file.size > 5 * 1024 * 1024) {
    showToast('File too large (max 5 MB)', 'error');
    return;
  }

  const formData = new FormData();
  formData.append('receipt', file);

  try {
    const res = await fetch(`/api/expenses/${expenseId}/receipt`, {
      method: 'POST',
      body: formData,
      credentials: 'same-origin'
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || 'Upload failed');
    }
    showToast('Receipt uploaded!', 'success');
    document.getElementById('genericModal')?.remove();
    if (currentGroupId) viewGroup(currentGroupId);
    loadTransactions();
  } catch (e) {
    showToast(e.message, 'error');
  }
}
window.uploadReceipt = uploadReceipt;

async function viewReceipt(expenseId) {
  try {
    const data = await api(`/expenses/${expenseId}/receipt`);

    if (!data.has_receipt) {
      showToast('No receipt attached', 'info');
      return;
    }

    const path = data.receipt_path;
    const isPDF = path.toLowerCase().endsWith('.pdf');
    const isImage = /\.(jpg|jpeg|png|gif)$/i.test(path);

    const modal = document.getElementById('genericModal');
    if (modal) modal.remove();

    const m = document.createElement('div');
    m.id = 'genericModal';
    m.className = 'modal open';
    m.innerHTML = `<div class="modal-card" style="width:min(700px,95vw)">
      <button class="close" onclick="this.closest('.modal').remove()">×</button>
      <h2>📎 Receipt</h2>
      <p>${escapeHtml(data.merchant || '')} · ${escapeHtml(data.description || '')}</p>
      <div style="margin-top:14px;background:#fafbfc;border-radius:12px;padding:16px;text-align:center">
        ${isImage
          ? `<img src="${escapeHtml(path)}" style="max-width:100%;max-height:60vh;border-radius:10px">`
          : isPDF
            ? `<iframe src="${escapeHtml(path)}" style="width:100%;height:60vh;border:0;border-radius:10px"></iframe>`
            : `<p>Preview not available</p><a href="${escapeHtml(path)}" target="_blank" class="primary-btn">Open File</a>`
        }
      </div>
      <div style="margin-top:12px;font-size:10px;color:#8b929d;text-align:center">
        Uploaded ${escapeHtml(data.uploaded_at || 'recently')}
      </div>
    </div>`;
    m.addEventListener('click', e => { if (e.target === m) m.remove(); });
    document.body.appendChild(m);
  } catch (e) {
    showToast(e.message, 'error');
  }
}
window.viewReceipt = viewReceipt;

// ============================================================
// SETTLEMENTS
// ============================================================
async function loadSettlements() {
  try {
    const pending = await api('/settlements/pending');
    const all = await api('/settlements/');
    const incoming = await api('/settlements/incoming');
    const outgoing = await api('/settlements/outgoing');

    // 1. You need to pay
    const toPay = document.getElementById('toPayList');
    toPay.innerHTML = ''; // Clear
    if (pending.to_pay && pending.to_pay.length) {
      toPay.innerHTML = pending.to_pay.map(p => `
        <div class="settle-row">
          <div class="settle-avatar">${escapeHtml(p.user?.avatar || 'U')}</div>
          <div class="settle-info">
            <b>${escapeHtml(p.user?.name || 'User')}</b>
            <small>You owe</small>
          </div>
          <div class="settle-amount pay">-${money(p.amount)}</div>
          <button onclick="settleUp(${p.user_id}, ${p.amount})">Pay</button>
        </div>`).join('');
    } else {
      toPay.innerHTML = '<p style="font-size:11px;color:#20a779">You don\'t owe anyone ✓</p>';
    }

    // 2. You will receive
    const toRecv = document.getElementById('toReceiveList');
    toRecv.innerHTML = ''; // Clear
    if (pending.to_receive && pending.to_receive.length) {
      toRecv.innerHTML = pending.to_receive.map(p => `
        <div class="settle-row">
          <div class="settle-avatar" style="background:#20a779">${escapeHtml(p.user?.avatar || 'U')}</div>
          <div class="settle-info">
            <b>${escapeHtml(p.user?.name || 'User')}</b>
            <small>Owes you</small>
          </div>
          <div class="settle-amount receive">+${money(p.amount)}</div>
          <button onclick="remindUser(${p.user_id})" style="background:#f0a34a">Remind</button>
        </div>`).join('');
    } else {
      toRecv.innerHTML = '<p style="font-size:11px;color:#999">Nobody owes you.</p>';
    }

    // 3. Incoming
    const incomingEl = document.getElementById('incomingSettlements');
    if (incomingEl) {
      if (incoming.incoming && incoming.incoming.length) {
        incomingEl.innerHTML = incoming.incoming.map(s => `
          <div class="settle-row" style="background:#e8f8ee;border:1px solid #b8e8c9">
            <div class="settle-avatar" style="background:#20a779">${escapeHtml(s.payer.avatar)}</div>
            <div class="settle-info">
              <b>${escapeHtml(s.payer.name)} sent ₹${escapeHtml(s.amount)}</b>
              <small>${escapeHtml(s.created_at)} · Awaiting your confirmation</small>
            </div>
            <div class="settle-amount receive">+${money(s.amount)}</div>
            <button onclick="confirmSettlement(${s.id})" style="background:#20a779">Mark as received</button>
          </div>`).join('');
      } else {
        incomingEl.innerHTML = '<p style="font-size:11px;color:#999">No pending confirmations.</p>';
      }
    }

    // 4. Outgoing
    const outgoingEl = document.getElementById('outgoingSettlements');
    if (outgoingEl) {
      if (outgoing.outgoing && outgoing.outgoing.length) {
        outgoingEl.innerHTML = outgoing.outgoing.map(s => `
          <div class="settle-row" style="background:#fff8eb;border:1px solid #ffe0b0">
            <div class="settle-avatar" style="background:#f0a34a">${escapeHtml(s.receiver.avatar)}</div>
            <div class="settle-info">
              <b>You paid ₹${escapeHtml(s.amount)} to ${escapeHtml(s.receiver.name)}</b>
              <small>${escapeHtml(s.created_at)} · Awaiting their confirmation</small>
            </div>
            <div class="settle-amount pay">-${money(s.amount)}</div>
            <span style="font-size:10px;color:#f0a34a;font-weight:700">PENDING</span>
          </div>`).join('');
      } else {
        outgoingEl.innerHTML = '<p style="font-size:11px;color:#999">No outgoing settlements pending.</p>';
      }
    }

    // 5. History
    const history = document.getElementById('settlementHistory');
    const completed = all.settlements.filter(s => s.status !== 'pending');
    
    if (completed.length) {
      history.innerHTML = completed.map(s => {
        const isCompleted = s.status === 'completed';
        const icon = isCompleted ? '✓' : '✗';
        const bg = isCompleted ? '#e6f8f1' : '#ffeaec';
        const color = isCompleted ? '#20a779' : '#ef5b67';
        return `
          <div class="transaction-row">
            <div class="merchant-icon" style="background:${bg};color:${color}">
              ${icon}
            </div>
            <div>
              <b>${escapeHtml(s.payer.name)} → ${escapeHtml(s.receiver.name)}</b>
              <small>${escapeHtml(s.created_at)} · ${escapeHtml(s.status)}</small>
            </div>
            <span class="amount">${money(s.amount)}</span>
          </div>`;
      }).join('');
    } else {
      history.innerHTML = '<p style="font-size:11px;color:#999">No completed settlements yet.</p>';
    }

  } catch (e) {
    console.error('Settlements:', e);
  }
}

async function settleUp(receiverId, amount) {
  if (!confirm(`Settle ₹${amount}? Receiver will need to confirm.`)) return;
  try {
    await api('/settlements/', {
      method: 'POST',
      body: { receiver_id: receiverId, amount }
    });
    showToast('Payment initiated! Waiting for receiver to confirm.', 'success');
    loadSettlements();
    loadDashboard();
  } catch (e) {
    showToast(e.message, 'error');
  }
}
window.settleUp = settleUp;

async function remindUser(userId) {
  try {
    await api('/settlements/remind/' + userId, { method: 'POST' });
    showToast('Reminder sent!', 'success');
  } catch (e) { showToast(e.message, 'error'); }
}
window.remindUser = remindUser;

async function confirmSettlement(id) {
  if (!confirm('Confirm that you received this payment?')) return;
  try {
    await api('/settlements/' + id + '/complete', { method: 'POST' });
    showToast('Settlement confirmed! Balances updated.', 'success');
    loadSettlements();
    loadDashboard();
  } catch (e) {
    showToast(e.message, 'error');
  }
}
window.confirmSettlement = confirmSettlement;

async function rejectSettlement(id) {
  if (!confirm('Reject this settlement?')) return;
  try {
    await api('/settlements/' + id + '/reject', { method: 'POST' });
    showToast('Settlement rejected.', 'info');
    loadSettlements();
  } catch (e) {
    showToast(e.message, 'error');
  }
}
window.rejectSettlement = rejectSettlement;

async function completeSettlement(id) {
  return confirmSettlement(id);
}
window.completeSettlement = completeSettlement;

// ============================================================
// BUDGETS
// ============================================================
async function loadBudgets() {
  try {
    const data = await api('/budgets/');
    const grid = document.getElementById('budgetGrid');

    if (!data.budgets.length) {
      grid.innerHTML = '<p style="font-size:11px;color:#999;padding:20px">No budgets yet.</p>';
      const sug = document.getElementById('budgetSuggestion');
      if (sug) sug.style.display = 'none';
      return;
    }

    grid.innerHTML = data.budgets.map(b => {
      const cls = b.status === 'danger' ? 'danger' : b.status === 'warn' ? 'warn' : '';
      return `<div class="budget-card">
        <div class="b-top">
          <h3>◫ &nbsp;${escapeHtml(b.category)}</h3>
          <span class="muted">${b.percentage}%</span>
        </div>
        <div class="spent">${money(b.spent)}</div>
        <small>of ${money(b.limit)} budget</small>
        <div class="budget-progress ${cls}"><span style="width:${Math.min(b.percentage, 100)}%"></span></div>
        <div class="budget-foot">
          <span>${money(b.remaining)} remaining</span>
          <span>${escapeHtml(b.month)}</span>
        </div>
      </div>`;
    }).join('');

    const sug = await api('/analytics/suggestions');
    if (sug.suggestions.length && sug.suggestions[0].type !== 'info') {
      const s = sug.suggestions[0];
      document.getElementById('budgetSuggestionTitle').textContent = s.category || 'Suggestion';
      document.getElementById('budgetSuggestionText').textContent = s.message;
      document.getElementById('budgetSuggestion').style.display = 'flex';
    } else {
      document.getElementById('budgetSuggestion').style.display = 'none';
    }
  } catch (e) {
    console.error('Budgets:', e);
    throw e;
  }
}

// ============================================================
// ML INSIGHTS
// ============================================================
async function loadInsights() {
  try {
    const [pred, risk] = await Promise.all([
      api('/analytics/predict'),
      api('/analytics/risk')
    ]);

    const current = pred.history.length ? pred.history[pred.history.length - 1] : 0;
    document.getElementById('forecastPanel').innerHTML = `
      <div><span>Current</span><b>${shortMoney(current)}</b></div>
      <span class="arrow">→</span>
      <div><span>Predicted</span><b>${shortMoney(pred.total_prediction.prediction)}</b></div>
    `;
    document.getElementById('predAccuracy').textContent =
      Math.round(pred.total_prediction.confidence * 100) + '%';

    const maxVal = Math.max(...pred.history, pred.total_prediction.prediction, 1);
    const bars = pred.history.map(h => Math.max((h / maxVal) * 100, 4));
    bars.push(Math.max((pred.total_prediction.prediction / maxVal) * 100, 4));
    document.getElementById('miniBars').innerHTML =
      bars.map((h, i) => `<i style="height:${h}%;${i === bars.length - 1 ? 'background:#665eff' : ''}"></i>`).join('');

    const riskEl = document.getElementById('riskList');
    const badge = document.getElementById('riskBadge');
    const highCount = risk.risk.filter(r => r.level === 'high').length;
    const medCount = risk.risk.filter(r => r.level === 'medium').length;
    badge.textContent = highCount > 0 ? `${highCount} high` : medCount > 0 ? `${medCount} medium` : 'All low';

    if (!risk.risk.length) {
      riskEl.innerHTML = '<p style="font-size:11px;color:#999">No budgets to analyze.</p>';
    } else {
      riskEl.innerHTML = risk.risk.map(r => `
        <div class="anomaly-item">
          <span>${escapeHtml(r.category)}</span>
          <div class="risk-bar"><i class="${r.level}" style="width:${Math.min(r.percentage, 100)}%"></i></div>
          <b style="text-transform:capitalize">${escapeHtml(r.level)}</b>
        </div>`).join('');
    }
  } catch (e) {
    console.error('Insights:', e);
    throw e;
  }
}

document.getElementById('testClassifyBtn').onclick = async () => {
  const input = document.getElementById('testClassifyInput').value.trim();
  if (!input) return;
  try {
    const result = await api('/expenses/classify', {
      method: 'POST',
      body: { description: input }
    });
    document.getElementById('classifyResult').innerHTML = `
      <div style="margin-top:8px;padding:10px;background:#fff;border-radius:9px">
        <b style="font-size:11px;color:#635bff">${escapeHtml(result.category)}</b>
        <span style="font-size:9px;color:#8b929d"> · ${Math.round(result.confidence * 100)}% confidence</span>
        <div class="chips" style="margin-top:6px">
          ${result.keywords.map(k => `<span>${escapeHtml(k)}</span>`).join('')}
        </div>
      </div>`;
  } catch (e) { showToast(e.message, 'error'); }
};

// ============================================================
// REPORTS
// ============================================================
async function loadReports() {
  try {
    const [dash, breakdown] = await Promise.all([
      api('/dashboard/'),
      api('/analytics/category-breakdown')
    ]);
    const avg = dash.total_expenses / 30;
    document.getElementById('reportCards').innerHTML = `
      <div class="report-card"><span>Monthly spend</span><b>${shortMoney(dash.total_expenses)}</b><small>${dash.income ? ((dash.total_expenses / dash.income) * 100).toFixed(0) : 0}% of income</small></div>
      <div class="report-card"><span>Average daily</span><b>${shortMoney(avg)}</b><small>30 days</small></div>
      <div class="report-card"><span>Top category</span><b>${escapeHtml(breakdown.breakdown[0]?.category || '-')}</b><small>${breakdown.breakdown[0] ? money(breakdown.breakdown[0].amount) : '-'}</small></div>
      <div class="report-card"><span>Projected</span><b>${shortMoney(dash.prediction.prediction)}</b><small>AI forecast</small></div>
    `;
    document.getElementById('reportSummary').textContent =
      `Spending: ${money(dash.total_expenses)}. Savings rate: ${dash.savings_rate}%. ${dash.alerts.length} alerts.`;
  } catch (e) {
    console.error('Reports:', e);
    throw e;
  }
}

// ============================================================
// SETTINGS
// ============================================================
async function loadSettings() {
  if (!currentUser) return;
  document.getElementById('settingsName').value = currentUser.name || '';
  document.getElementById('settingsEmail').value = currentUser.email || '';
  document.getElementById('settingsIncome').value = currentUser.monthly_income || 0;
}

document.getElementById('saveSettingsBtn').onclick = async () => {
  try {
    const res = await api('/auth/me', {
      method: 'PUT',
      body: {
        name: document.getElementById('settingsName').value,
        monthly_income: Number(document.getElementById('settingsIncome').value) || 0
      }
    });
    currentUser = res.user;
    document.getElementById('userName').textContent = currentUser.name;
    document.getElementById('userAvatar').textContent = currentUser.avatar;
    showToast('Settings saved!', 'success');
    loadDashboard();
  } catch (e) { showToast(e.message, 'error'); }
};

document.getElementById('logoutBtn').onclick = async () => {
  try { await api('/auth/logout', { method: 'POST' }); } catch (e) {}
  window.location.href = '/api/auth/login-page';
};

// ============================================================
// PAGE NAVIGATION
// ============================================================
function openPage(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active-page'));
  const t = document.getElementById(page);
  if (t) t.classList.add('active-page');

  document.querySelectorAll('.nav-item[data-page]').forEach(n =>
    n.classList.toggle('active', n.dataset.page === page));

  const titles = {
    dashboard: ['OVERVIEW', `Good morning${currentUser ? ', ' + currentUser.name.split(' ')[0] : ''} 👋`],
    transactions: ['TRANSACTIONS', 'Your transactions'],
    groups: ['GROUPS', 'Manage your groups'],
    settlements: ['SETTLEMENTS', 'Who owes whom'],
    budgets: ['BUDGETING', 'Personalized budgets'],
    insights: ['MACHINE LEARNING', 'ML insights & explanations'],
    reports: ['REPORTS', 'Financial reports'],
    settings: ['PREFERENCES', 'Settings']
  };
  document.getElementById('pageEyebrow').textContent = titles[page]?.[0] || '';
  document.getElementById('pageTitle').textContent = titles[page]?.[1] || '';

  if (page === 'dashboard') loadDashboard().catch(() => {});
  if (page === 'transactions') loadTransactions().catch(() => {});
  if (page === 'groups') loadGroups().catch(() => {});
  if (page === 'settlements') loadSettlements().catch(() => {});
  if (page === 'budgets') loadBudgets().catch(() => {});
  if (page === 'insights') loadInsights().catch(() => {});
  if (page === 'reports') loadReports().catch(() => {});
  if (page === 'settings') loadSettings();
}
window.openPage = openPage;

document.querySelectorAll('[data-page]').forEach(el =>
  el.addEventListener('click', () => openPage(el.dataset.page)));

// ============================================================
// MODALS
// ============================================================
function showModal(html) {
  const existing = document.getElementById('genericModal');
  if (existing) existing.remove();

  const modal = document.createElement('div');
  modal.id = 'genericModal';
  modal.className = 'modal open';
  modal.innerHTML = `<div class="modal-card">${html}</div>`;
  modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });
  document.body.appendChild(modal);
}
window.showModal = showModal;

// Expense modal
const modal = document.getElementById('expenseModal');
function openExpenseModal() {
  modal.classList.add('open');
  document.getElementById('expenseDesc').focus();
  document.getElementById('classificationPreview').style.display = 'none';
  document.getElementById('participantSection').style.display = 'none';
  selectedParticipants.clear();
}
function closeExpenseModal() { modal.classList.remove('open'); }

document.getElementById('quickAddBtn').onclick = openExpenseModal;
document.getElementById('addTransactionBtn').onclick = openExpenseModal;
document.getElementById('closeModal').onclick = closeExpenseModal;
modal.addEventListener('click', e => { if (e.target === modal) closeExpenseModal(); });

document.getElementById('expenseDesc').addEventListener('input', async (e) => {
  const desc = e.target.value.trim();
  if (desc.length < 3) {
    document.getElementById('classificationPreview').style.display = 'none';
    return;
  }
  clearTimeout(window._classifyTimer);
  window._classifyTimer = setTimeout(async () => {
    try {
      const r = await api('/expenses/classify', { method: 'POST', body: { description: desc } });
      const el = document.getElementById('classificationPreview');
      el.innerHTML = `<b>✦ AI suggests: ${escapeHtml(r.category)}</b> (${Math.round(r.confidence * 100)}% confidence)`;
      el.style.display = 'block';
    } catch (e) {}
  }, 500);
});

document.getElementById('expenseAmount')?.addEventListener('input', updateParticipantSummary);

document.getElementById('saveExpense').onclick = async () => {
  const desc = document.getElementById('expenseDesc').value.trim();
  const amount = Number(document.getElementById('expenseAmount').value);
  const source = document.getElementById('expenseSource').value;
  const groupId = document.getElementById('expenseGroup').value;
  const category = document.getElementById('expenseCategory').value;

  if (!desc || amount <= 0) {
    showToast('Enter description and valid amount', 'error');
    return;
  }

  // If group selected, build participants list
  let participants = null;
  if (groupId) {
    participants = Array.from(selectedParticipants);
    if (participants.length === 0) {
      showToast('Select at least 1 participant', 'error');
      return;
    }
    if (!participants.includes(currentUser.id)) {
      participants.push(currentUser.id);
    }
  }

  const btn = document.getElementById('saveExpense');
  btn.disabled = true;
  btn.textContent = 'Saving...';

  try {
    await api('/expenses/', {
      method: 'POST',
      body: {
        description: desc,
        amount,
        source,
        category: category === 'Auto-classify with AI' ? null : category,
        group_id: groupId ? Number(groupId) : null,
        split_type: 'equal',
        participants: participants,
      }
    });
    closeExpenseModal();
    document.getElementById('expenseDesc').value = '';
    document.getElementById('expenseAmount').value = '';
    document.getElementById('participantSection').style.display = 'none';
    selectedParticipants.clear();
    showToast('Expense added!', 'success');
    loadTransactions();
    loadDashboard();
    if (groupId) loadGroups();
    openPage('transactions');
  } catch (e) {
    showToast(e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Save expense';
  }
};

// Group modal
const groupModal = document.getElementById('groupModal');
document.getElementById('createGroupBtn').onclick = () => {
  resetGroupModal();
  groupModal.classList.add('open');
};
document.getElementById('closeGroupModal').onclick = () => {
  groupModal.classList.remove('open');
  resetGroupModal();
};
groupModal.addEventListener('click', e => {
  if (e.target === groupModal) {
    groupModal.classList.remove('open');
    resetGroupModal();
  }
});

document.getElementById('saveGroup').onclick = async () => {
  // If editing existing group — just close
  if (window._currentGroupId) {
    document.getElementById('groupModal').classList.remove('open');
    document.getElementById('groupName').disabled = false;
    document.getElementById('groupDesc').disabled = false;
    window._currentGroupId = null;
    return;
  }

  const name = document.getElementById('groupName').value.trim();
  if (!name) { showToast('Group name required', 'error'); return; }

  try {
    await api('/groups/', {
      method: 'POST',
      body: {
        name,
        description: document.getElementById('groupDesc').value.trim(),
      }
    });
    document.getElementById('groupModal').classList.remove('open');
    document.getElementById('groupName').value = '';
    document.getElementById('groupDesc').value = '';
    showToast('Group created!', 'success');
    loadGroups();
  } catch (e) {
    showToast(e.message, 'error');
  }
};

// Budget modal
const budgetModal = document.getElementById('budgetModal');
document.getElementById('createBudgetBtn').onclick = () => budgetModal.classList.add('open');
document.getElementById('closeBudgetModal').onclick = () => budgetModal.classList.remove('open');
budgetModal.addEventListener('click', e => { if (e.target === budgetModal) budgetModal.classList.remove('open'); });

document.getElementById('saveBudget').onclick = async () => {
  const category = document.getElementById('budgetCategory').value;
  const limit = Number(document.getElementById('budgetLimit').value);
  if (!limit || limit <= 0) { showToast('Enter valid limit', 'error'); return; }
  try {
    await api('/budgets/', { method: 'POST', body: { category, limit } });
    budgetModal.classList.remove('open');
    document.getElementById('budgetLimit').value = '';
    showToast('Budget saved!', 'success');
    loadBudgets();
  } catch (e) { showToast(e.message, 'error'); }
};

document.getElementById('searchInput')?.addEventListener('input', () => loadTransactions().catch(() => {}));
document.getElementById('filterCategory')?.addEventListener('change', () => loadTransactions().catch(() => {}));
document.getElementById('refreshTransactionsBtn')?.addEventListener('click', () => {
  loadTransactions().catch(() => {});
  showToast('Refreshed', 'success');
});
document.getElementById('refreshSettlementsBtn')?.addEventListener('click', () => {
  loadSettlements().catch(() => {});
  showToast('Refreshed', 'success');
});

// ============================================================
// POLLING — 30 seconds + exponential backoff
// ============================================================
function initPolling() {
  console.log('📡 Auto-sync active (30s interval)');
  const liveIcon = document.getElementById('liveIcon');
  if (liveIcon) {
    liveIcon.style.color = '#20a779';
    liveIcon.style.animation = 'pulse 2s infinite';
  }
  if (!document.getElementById('pollStyles')) {
    const style = document.createElement('style');
    style.id = 'pollStyles';
    style.textContent = `@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }`;
    document.head.appendChild(style);
  }

  async function pollActivePage() {
    if (document.hidden) return;
    const active = document.querySelector('.page.active-page')?.id;
    if (!active) return;

    try {
      if (active === 'dashboard') await loadDashboard();
      else if (active === 'transactions') await loadTransactions();
      else if (active === 'settlements') await loadSettlements();
      else if (active === 'budgets') await loadBudgets();
      else if (active === 'groups') await loadGroups();
      consecutiveErrors = 0;
    } catch (e) {
      consecutiveErrors++;
      if (consecutiveErrors >= 5) {
        clearInterval(pollInterval);
        const backoff = Math.min(POLL_INTERVAL_MS * Math.pow(2, consecutiveErrors - 5), 300000);
        console.warn(`Polling backed off to ${backoff}ms`);
        pollInterval = setInterval(pollActivePage, backoff);
      }
    }
  }

  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(pollActivePage, POLL_INTERVAL_MS);

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      consecutiveErrors = 0;
      if (pollInterval) clearInterval(pollInterval);
      pollInterval = setInterval(pollActivePage, POLL_INTERVAL_MS);
      pollActivePage();
    }
  });
  window.addEventListener('focus', pollActivePage);
}

// ============================================================
// INIT
// ============================================================
(async function init() {
  try {
    currentUser = await api('/auth/me');
    document.getElementById('userName').textContent = currentUser.name;
    document.getElementById('userAvatar').textContent = currentUser.avatar;

    try {
      const g = await api('/groups/');
      groupsCache = g.groups;
    } catch (e) {}

    initPolling();
    loadDashboard().catch(() => {});
    console.log('✅ FinSight AI ready');
  } catch (e) {
    window.location.href = '/api/auth/login-page';
  }
})();