import { $, show, setEl, escapeHtml, formatTimeAgo, apiPost, apiGet } from '../helpers.js';

// ─── Nodes ───

export async function refreshNodes() {
  try {
    const data = await apiGet('/nodes');
    const nodes = data.nodes || [];
    const active = nodes.filter(n => n.is_active !== false);
    setEl('nodesTotal', nodes.length); setEl('nodesActive', active.length);
    const selfNode = nodes.find(n => n.is_self);
    setEl('nodesSelfId', selfNode ? (selfNode.node_id || '').slice(0, 16) + '...' : '—');
    if (nodes.length === 0) { show($('nodesList'), '<div class="loading">Нод нет</div>'); return; }
    const now = Math.floor(Date.now() / 1000);
    let html = '<table class="cassandra-table"><tr><th>ID</th><th>Адрес</th><th>Высота</th><th>Был в сети</th><th>Статус</th></tr>';
    nodes.forEach(n => {
      const isSelf = n.is_self;
      const status = n.is_active === false ? '🔴 Неактивна' : '🟢 Активна';
      const lastSeen = n.last_seen ? formatTimeAgo(n.last_seen, now) + ' назад' : '—';
      html += `<tr style="${isSelf ? 'opacity:0.7;' : ''}">
        <td class="mono">${escapeHtml((n.node_id||'').slice(0,16))}${isSelf ? ' (это я)' : ''}</td>
        <td class="mono" style="color:var(--accent);">${escapeHtml(n.api_host||'')}:${n.api_port||'—'}</td>
        <td>${n.chain_height ?? '—'}</td>
        <td style="font-size:12px;">${lastSeen}</td>
        <td>${status}</td>
      </tr>`;
    });
    html += '</table>'; show($('nodesList'), html);
  } catch (e) { show($('nodesList'), '❌ ' + e.message); }
}

export async function registerNode() {
  const nodeId = $('newNodeId').value.trim();
  let urlRaw = $('newNodeUrl').value.trim();
  if (!urlRaw) { show($('nodeRegisterResult'), '❌ Укажите API-адрес'); return; }
  if (!urlRaw.startsWith('http')) urlRaw = 'http://' + urlRaw;
  let host, port;
  try { const p = new URL(urlRaw); host = p.hostname; port = p.port || '8000'; }
  catch { show($('nodeRegisterResult'), '❌ Невалидный URL'); return; }
  try {
    const res = await apiPost('/node/register', { node_id: nodeId || `node-${Date.now().toString(36)}`, name: nodeId || `node-${host}`, api_host: host, api_port: parseInt(port) });
    show($('nodeRegisterResult'), `✅ ${res.status} — ${res.node_id}`);
    setTimeout(refreshNodes, 1000);
  } catch (e) { show($('nodeRegisterResult'), '❌ ' + e.message); }
}

// Expose for onclick
window.refreshNodes = refreshNodes;
window.registerNode = registerNode;