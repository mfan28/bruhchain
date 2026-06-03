import { $, show, hide, escapeHtml, jsonHighlight, apiGet, apiPost } from '../helpers.js';

// ─── Transactions ───

export async function fetchNonce() {
  const addr = $('txFrom').value.trim();
  if (!addr) { alert('Enter From address first'); return; }
  try {
    const data = await apiGet('/account/' + addr);
    $('txNonce').value = data.nonce;
    show($('txResult'), `✅ Nonce fetched: ${data.nonce}`);
  } catch {
    $('txNonce').value = 0;
    show($('txResult'), 'ℹ️ New account, nonce = 0');
  }
}

export function updatePayloadPreset() {
  const action = $('txAction').value;
  const presets = {
    send_message: '{"message": "Hello blockchain!"}',
    create_account: '{"action": "create_account", "name": "MyName", "description": "My profile"}',
    update_profile: '{"action": "update_profile", "name": "NewName"}',
    set_online: '{"action": "set_online"}',
    set_offline: '{"action": "set_offline"}',
  };
  $('txPayload').value = presets[action] || '{}';
}

export function initTxForm() {
  $('txForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    let payload;
    try { payload = JSON.parse($('txPayload').value); } catch { show($('txResult'), '❌ Invalid JSON'); return; }
    const body = {
      from: $('txFrom').value, to: $('txTo').value,
      nonce: parseInt($('txNonce').value), payload,
      signature: $('txSignature').value, timestamp: Math.floor(Date.now() / 1000),
    };
    try {
      const res = await apiPost('/transaction', body);
      show($('txResult'), jsonHighlight(res));
      setTimeout(refreshTransactions, 500);
    } catch (e) { show($('txResult'), '❌ ' + e.message); }
  });
}

export async function refreshTransactions() {
  try {
    const data = await apiGet('/transactions/recent?limit=15');
    const txs = data.transactions || [];
    const list = $('recentTxList');
    if (txs.length === 0) { show(list, '<div class="loading">No transactions yet</div>'); return; }
    let html = '<table class="cassandra-table"><tr><th>Hash</th><th>From</th><th>To</th><th>Action</th><th>Block</th></tr>';
    txs.forEach(tx => {
      const action = tx.payload?.action || 'generic';
      html += `<tr>
        <td class="mono" style="max-width:100px;overflow:hidden;text-overflow:ellipsis;">${(tx.hash||'').slice(0,12)}…</td>
        <td class="mono" style="max-width:80px;overflow:hidden;text-overflow:ellipsis;">${(tx.from||'').slice(0,10)}…</td>
        <td class="mono" style="max-width:80px;overflow:hidden;text-overflow:ellipsis;">${(tx.to||'').slice(0,10)}…</td>
        <td>${action}</td>
        <td>#${tx.block_height ?? '?'}</td>
      </tr>`;
    });
    html += '</table>';
    show(list, html);
  } catch { show($('recentTxList'), '<div class="loading">Could not load</div>'); }
}

export async function lookupTx() {
  const hash = $('txLookupHash').value.trim();
  if (!hash) return;
  try { show($('txLookupResult'), jsonHighlight(await apiGet('/transaction/' + hash))); }
  catch (e) { show($('txLookupResult'), '❌ ' + e.message); }
}

export async function lookupAddressTxs() {
  const addr = $('txAddress').value.trim();
  if (!addr) return;
  try { show($('txAddressResult'), jsonHighlight(await apiGet('/transactions/' + addr))); }
  catch (e) { show($('txAddressResult'), '❌ ' + e.message); }
}

// Expose for onclick
window.fetchNonce = fetchNonce;
window.updatePayloadPreset = updatePayloadPreset;
window.refreshTransactions = refreshTransactions;
window.lookupTx = lookupTx;
window.lookupAddressTxs = lookupAddressTxs;