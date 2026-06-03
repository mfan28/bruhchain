import { $, show, setEl, escapeHtml, apiGet } from '../helpers.js';

// ─── Accounts ───

export async function refreshAccounts() {
  try {
    const data = await apiGet('/accounts');
    const accounts = data.accounts || [];
    setEl('accountsTotal', accounts.length);
    setEl('accountsOnline', '—');

    const list = $('allAccountsList');
    if (accounts.length === 0) { show(list, '<div class="loading">No accounts yet</div>'); return; }
    let html = '<table class="cassandra-table"><tr><th>Address</th><th>Nonce</th></tr>';
    accounts.forEach(a => {
      html += `<tr>
        <td class="mono" style="max-width:180px;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(a.address).slice(0,24)}…</td>
        <td>${a.nonce ?? 0}</td>
      </tr>`;
    });
    html += '</table>';
    show(list, html);
  } catch (e) { show($('allAccountsList'), '❌ ' + e.message); }
}

export async function lookupAccount() {
  const addr = $('accountAddress').value.trim();
  if (!addr) return;
  try {
    const data = await apiGet('/account/' + addr);
    let html = '<div class="account-card">';
    html += `<div class="account-card-header">
      <span class="account-address">📇 ${escapeHtml(data.address)}</span>
      <span class="account-status">—</span>
    </div>`;
    html += `<div class="account-card-body">
      <div><span class="ac-label">Nonce:</span> ${data.nonce ?? 0}</div>
      <div><span class="ac-label">Data:</span> <pre class="mono" style="font-size:12px;max-height:200px;overflow:auto;">${escapeHtml(JSON.stringify(data, null, 2))}</pre></div>
    </div>`;
    html += '</div>';
    show($('accountResult'), html);
  } catch (e) { show($('accountResult'), '❌ ' + e.message); }
}

// Expose for onclick
window.refreshAccounts = refreshAccounts;
window.lookupAccount = lookupAccount;