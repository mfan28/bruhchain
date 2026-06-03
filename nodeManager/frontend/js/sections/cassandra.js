import { $, show, escapeHtml, apiGet } from '../helpers.js';

// ─── Cassandra Viewer ───

export async function refreshCassandra() {
  const sel = $('cassandraTable'); sel.innerHTML = '<option value="">— Select table —</option>';
  try {
    const data = await apiGet('/cassandra/tables');
    data.tables.forEach(t => { const o = document.createElement('option'); o.value = t; o.textContent = t; sel.appendChild(o); });
  } catch (e) { $('cassandraError').style.display = 'block'; $('cassandraError').textContent = '❌ ' + e.message; }
}

export async function loadCassandraTable() {
  const table = $('cassandraTable').value, limit = parseInt($('cassandraLimit').value) || 20;
  $('cassandraError').style.display = 'none';
  if (!table) { show($('cassandraResult'), '<div class="loading">Select a table</div>'); return; }
  try {
    const data = await apiGet(`/cassandra/table/${table}?limit=${limit}`);
    if (data.count === 0) { show($('cassandraResult'), '<div class="loading">Empty table</div>'); return; }
    let html = `<div style="margin-bottom:8px;color:var(--text-muted);font-size:11px;">${data.count} row(s)</div>`;
    html += '<table class="cassandra-table"><tr>' + data.columns.map(c => `<th>${c}</th>`).join('') + '</tr>';
    data.rows.forEach(row => {
      html += '<tr>' + data.columns.map(c => {
        let val = row[c];
        if (val === null || val === undefined) return '<td class="null">null</td>';
        val = String(val); if (val.length > 80) val = val.slice(0, 80) + '…';
        return `<td>${escapeHtml(val)}</td>`;
      }).join('') + '</tr>';
    });
    html += '</table>'; show($('cassandraResult'), html);
  } catch (e) { $('cassandraError').style.display = 'block'; $('cassandraError').textContent = '❌ ' + e.message; }
}

// Expose for onclick
window.refreshCassandra = refreshCassandra;
window.loadCassandraTable = loadCassandraTable;