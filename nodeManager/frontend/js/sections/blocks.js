import { $, show, setEl, escapeHtml, apiGet } from '../helpers.js';

// ─── Blocks ───

let blocksPageOffset = 0;
const BLOCKS_PAGE_SIZE = 15;

export async function refreshBlocks() {
  try {
    blocksPageOffset = 0; await loadBlocksPage();
    const latest = await apiGet('/block/latest');
    setEl('blocksLatestHeight', `#${latest.height}`);
    setEl('blocksLastMiner', latest.miner_address?.slice(0, 16) + '…' || '—');
    setEl('blocksLastTime', new Date(latest.timestamp * 1000).toLocaleString());
    setEl('blocksTotal', latest.height + 1);
  } catch {
    setEl('blocksLatestHeight', '—'); setEl('blocksLastMiner', '—');
    setEl('blocksLastTime', '—'); setEl('blocksTotal', '0');
  }
}

async function loadBlocksPage() {
  const listEl = $('blocksList');
  try {
    const data = await apiGet(`/blocks?limit=${BLOCKS_PAGE_SIZE}&offset=${blocksPageOffset}`);
    if (data.count === 0) { show(listEl, '<div class="loading">Блоков ещё нет</div>'); return; }
    let html = '<table class="cassandra-table"><tr><th>Высота</th><th>Хеш</th><th>Майнер</th><th>TX</th><th>Время</th><th></th></tr>';
    data.blocks.forEach(b => {
      const time = new Date(b.timestamp * 1000).toLocaleString();
      html += `<tr onclick="window.showBlockFromList(${b.height})" style="cursor:pointer;">
        <td style="font-weight:600;color:var(--accent);">#${b.height}</td>
        <td style="max-width:140px;overflow:hidden;text-overflow:ellipsis;">${b.hash.slice(0,20)}…</td>
        <td style="max-width:100px;overflow:hidden;text-overflow:ellipsis;">${(b.miner_address||'').slice(0,12)}…</td>
        <td>${b.tx_count}</td>
        <td style="font-size:10px;white-space:nowrap;">${time}</td>
        <td><button class="btn btn-sm" onclick="event.stopPropagation();window.showBlockFromList(${b.height})">🔍</button></td>
      </tr>`;
    });
    html += '</table>';
    show(listEl, html);
    $('blocksPageInfo').textContent = `Page ${Math.floor(blocksPageOffset / BLOCKS_PAGE_SIZE) + 1}`;
    $('blocksPrevBtn').disabled = blocksPageOffset === 0;
    $('blocksNextBtn').disabled = data.count < BLOCKS_PAGE_SIZE;
  } catch (e) { show(listEl, `<div style="color:var(--red);">❌ ${e.message}</div>`); }
}

export async function showBlockFromList(height) {
  try { showBlockDetail(await apiGet('/block/' + height)); }
  catch (e) { $('blockDetailCard').style.display = 'block'; $('blockDetailTitle').textContent = `Блок #${height}`;
    show($('blockDetailBody'), `<div style="color:var(--red)">❌ ${e.message}</div>`); }
}

export function blocksPage(dir) {
  if (dir === 'prev' && blocksPageOffset > 0) blocksPageOffset = Math.max(0, blocksPageOffset - BLOCKS_PAGE_SIZE);
  else if (dir === 'next') blocksPageOffset += BLOCKS_PAGE_SIZE;
  loadBlocksPage();
}

export async function lookupBlock() {
  const height = $('blockHeight').value.trim();
  if (!height) return;
  try { showBlockDetail(await apiGet('/block/' + height)); }
  catch (e) { $('blockDetailCard').style.display = 'block'; $('blockDetailTitle').textContent = `Блок #${height}`;
    show($('blockDetailBody'), `<div style="color:var(--red)">❌ ${e.message}</div>`); }
}

export async function searchBlockByHash() {
  const hash = $('blockHashSearch').value.trim();
  if (!hash) return;
  try { showBlockDetail(await apiGet('/block/search/hash?hash=' + encodeURIComponent(hash))); }
  catch (e) { $('blockDetailCard').style.display = 'block'; $('blockDetailTitle').textContent = 'Блок';
    show($('blockDetailBody'), `<div style="color:var(--red)">❌ ${e.message}</div>`); }
}

export function closeBlockDetail() { $('blockDetailCard').style.display = 'none'; }

function showBlockDetail(data) {
  $('blockDetailCard').style.display = 'block';
  $('blockDetailTitle').textContent = `Block #${data.height}`;
  const body = $('blockDetailBody');
  let html = '<div class="block-detail-grid">';
  html += blockField('Высота', `#${data.height}`, '🧱');
  html += blockField('Хеш', data.hash, '#');
  html += blockField('Предыдущий хеш', data.previous_hash, '⬅');
  html += blockField('Merkle Root', data.merkle_root, '🌲');
  html += blockField('State Root', data.state_root, '🌳');
  html += blockField('Время', new Date(data.timestamp * 1000).toLocaleString(), '⏱');
  html += blockField('Сложность', data.difficulty, '🎯');
  html += blockField('Nonce', data.nonce?.toLocaleString() ?? '—', '🔢');
  html += blockField('Майнер', data.miner_address, '⛏️');
  html += blockField('Транзакции', data.tx_count + ' шт.', '💳');
  html += '</div>';
  if (data.transactions && data.transactions.length > 0) {
    html += '<h3 style="margin:16px 0 8px;font-size:14px;color:var(--text-secondary);">📋 Транзакции</h3>';
    html += '<table class="cassandra-table"><tr><th>Хеш</th><th>Отправитель</th><th>Получатель</th><th>Действие</th></tr>';
    data.transactions.forEach(tx => {
      const action = tx.payload?.action || 'generic';
      html += `<tr><td style="max-width:120px;overflow:hidden;text-overflow:ellipsis;">${(tx.hash||'').slice(0,16)}…</td>
        <td style="max-width:100px;overflow:hidden;text-overflow:ellipsis;">${(tx.from||'').slice(0,10)}…</td>
        <td style="max-width:100px;overflow:hidden;text-overflow:ellipsis;">${(tx.to||'').slice(0,10)}…</td>
        <td>${action}</td></tr>`;
    });
    html += '</table>';
  }
  show(body, html);
}

function blockField(label, value, icon) {
  return `<div class="block-field"><span class="block-field-label">${icon} ${label}</span><span class="block-field-value">${escapeHtml(String(value))}</span></div>`;
}

export function goToBlock(height) {
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelector('[data-section="blocks"]').classList.add('active');
  document.getElementById('section-blocks').classList.add('active');
  showBlockFromList(height);
}

// Expose for onclick
window.showBlockFromList = showBlockFromList;
window.blocksPage = blocksPage;
window.lookupBlock = lookupBlock;
window.searchBlockByHash = searchBlockByHash;
window.closeBlockDetail = closeBlockDetail;
window.refreshBlocks = refreshBlocks;