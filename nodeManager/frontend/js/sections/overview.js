import { $, show, setEl, styleEl, escapeHtml, apiGet, formatTimeAgo } from '../helpers.js';

// ─── Overview ───
let autoRefreshTimer = null;

export async function refreshAll() {
  try {
    const data = await apiGet('/');
    setEl('statHeight', data.chain_height);
    setEl('statPending', data.pending_txs);
    setEl('statTotalTxs', data.total_txs?.toLocaleString() ?? '—');
    setEl('statAccounts', data.accounts_count?.toLocaleString() ?? '—');
    setEl('statDifficulty', data.difficulty ?? '—');
    setEl('sidebarHeight', data.chain_height);
    setEl('sidebarPending', data.pending_txs);
    setEl('statStatus', '● Здорова');
    styleEl('statStatus', 'color', 'var(--green)');
    setEl('liveIndicator', '● В сети');
    styleEl('liveIndicator', 'color', 'var(--green)');
  } catch {
    setEl('statStatus', '✖ Недоступна');
    styleEl('statStatus', 'color', 'var(--red)');
    setEl('liveIndicator', '✖ Недоступна');
    styleEl('liveIndicator', 'color', 'var(--red)');
  }
  await loadRecentBlocks();
  await loadActivityChart();
}

async function loadRecentBlocks() {
  try {
    const data = await apiGet('/blocks?limit=10&offset=0');
    const blocks = data.blocks || [];
    const list = $('recentBlocksList');
    if (blocks.length === 0) { show(list, '<div class="loading">Блоков ещё нет. Начните майнинг!</div>'); return; }
    const now = Math.floor(Date.now() / 1000);
    let html = '<div class="block-timeline">';
    blocks.forEach(b => {
      const ago = formatTimeAgo(b.timestamp, now);
      const minerShort = b.miner_address ? b.miner_address.slice(0, 10) + '…' : '—';
      html += `<div class="block-timeline-item" onclick="window.goToBlock(${b.height})">
        <div class="block-timeline-height">#${b.height}</div>
        <div class="block-timeline-hash" title="${escapeHtml(b.hash)}">${b.hash.slice(0, 20)}…</div>
        <div class="block-timeline-stats">
          <span>💳 ${b.tx_count}</span><span>⛏️ ${escapeHtml(minerShort)}</span><span>⏱ ${ago}</span>
        </div>
      </div>`;
    });
    html += '</div>';
    show(list, html);
  } catch { show($('recentBlocksList'), '<div class="loading">Не удалось загрузить блоки</div>'); }
}

async function loadActivityChart() {
  try {
    const data = await apiGet('/blocks?limit=20&offset=0');
    const blocks = data.blocks || [];
    const chart = $('activityChart');
    if (blocks.length === 0) { show(chart, '<div class="loading">Пока нет данных...</div>'); return; }
    const maxTx = Math.max(1, ...blocks.map(b => b.tx_count || 0));
    const now = Math.floor(Date.now() / 1000);
    let html = '<div class="activity-chart">';
    blocks.forEach(b => {
      const pct = Math.max(4, ((b.tx_count || 0) / maxTx) * 60);
      const ago = formatTimeAgo(b.timestamp, now);
      html += `<div class="activity-bar activity-bar-block" style="height:${pct}px" title="#${b.height}: ${b.tx_count} TX, ${ago}"></div>`;
    });
    html += '</div><div class="activity-legend">';
    html += '<span><div class="legend-dot" style="background:var(--green)"></div> Блоки</span>';
    html += '<span style="color:var(--text-muted);font-size:10px;">↕ высота столбца = кол-во TX</span></div>';
    show(chart, html);
  } catch { show($('activityChart'), '<div class="loading">Пока нет данных...</div>'); }
}

export function startAutoRefresh() {
  if (autoRefreshTimer) clearInterval(autoRefreshTimer);
  autoRefreshTimer = setInterval(refreshAll, 5000);
}

// Expose for onclick
window.goToBlock = (height) => {
  import('./blocks.js').then(m => m.goToBlock(height));
};
window.refreshAll = refreshAll;