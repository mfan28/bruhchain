import { $, show, hide, setEl, escapeHtml, formatBytes, apiGet, apiPost, API } from '../helpers.js';

// ─── State ───
let clusterPeers = [];
let clusterAllocs = [];

// ─── Refresh All ───
export async function refreshIpfsAll() {
  await Promise.all([loadClusterPeers(), loadClusterAllocations()]);
}

export const refreshIpfsHistory = renderIpfsHistory;

// ─── Cluster Peers ───

async function loadClusterPeers() {
  try {
    const data = await apiGet('/ipfs/cluster/peers');
    // API может вернуть {cluster_peers: [...]} или просто [...]
    clusterPeers = Array.isArray(data) ? data : (data.cluster_peers || data.peers || []);
    renderClusterStats();
    renderClusterPeers();
  } catch (e) {
    clusterPeers = [];
    show($('ipfsPeersList'), `<div class="loading" style="color:var(--red);">❌ ${escapeHtml(e.message)}</div>`);
    setEl('ipfsPeersCount', '❌');
    setEl('ipfsPeersOnline', '0');
    setEl('ipfsAllocCount', '—');
    setEl('ipfsClusterHealth', '🔴 Down');
    $('ipfsLiveIndicator').textContent = '● Disconnected';
  }
}

function renderClusterStats() {
  const total = clusterPeers.length;
  const online = clusterPeers.filter(p => !p.error && !p.ipfs_error).length;
  setEl('ipfsPeersCount', total);
  setEl('ipfsPeersOnline', online);
  setEl('ipfsAllocCount', clusterAllocs.length || '—');
  setEl('ipfsClusterHealth', total > 0 ? `🟢 ${online}/${total} online` : '—');
  $('ipfsLiveIndicator').textContent = online > 0 ? '● Connected' : '● Disconnected';
}

function renderClusterPeers() {
  const list = $('ipfsPeersList');
  if (!clusterPeers || clusterPeers.length === 0) {
    show(list, '<div class="loading">No peers in cluster</div>');
    return;
  }
  let html = '<table class="cassandra-table"><tr><th>Peer ID</th><th>Name</th><th>IPFS ID</th><th>Addresses</th><th>Status</th></tr>';
  clusterPeers.forEach(p => {
    const peerId = (p.id || '').slice(0, 16) + '…';
    const ipfsId = (p.ipfs && p.ipfs.id ? p.ipfs.id : '').slice(0, 16) + '…';
    const addrs = (p.addresses || []).map(a => {
      const parts = a.split('/');
      return parts.length > 2 ? parts[parts.length - 3] : a;
    }).join(', ') || '—';
    const status = (p.error || p.ipfs_error || (p.ipfs && p.ipfs.error)) ? '🔴 Error' : '🟢 Online';
    const name = p.peer_name || p.name || '—';
    html += `<tr>
      <td class="mono" style="font-size:11px;">${escapeHtml(peerId)}</td>
      <td>${escapeHtml(name)}</td>
      <td class="mono" style="font-size:11px;">${escapeHtml(ipfsId)}</td>
      <td style="font-size:11px;max-width:200px;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(addrs)}</td>
      <td>${status}</td>
    </tr>`;
  });
  html += '</table>';
  show(list, html);
}

// ─── Cluster Allocations ───

async function loadClusterAllocations() {
  try {
    const data = await apiGet('/ipfs/cluster/allocations');
    clusterAllocs = Array.isArray(data) ? data : (data.allocations || data || []);
    renderClusterStats();
    renderIpfsAllocations();
  } catch (e) {
    clusterAllocs = [];
    show($('ipfsAllocationsList'), `<div class="loading" style="color:var(--red);">❌ ${escapeHtml(e.message)}</div>`);
  }
}

function renderIpfsAllocations() {
  const list = $('ipfsAllocationsList');
  const filter = ($('ipfsAllocFilter')?.value || '').toLowerCase().trim();

  let filtered = clusterAllocs;
  if (filter) {
    filtered = filtered.filter(a => {
      const cidStr = a.cid ? (typeof a.cid === 'object' ? (a.cid['/'] || JSON.stringify(a.cid)) : String(a.cid)) : '';
      return cidStr.toLowerCase().includes(filter);
    });
  }

  if (!filtered || filtered.length === 0) {
    show(list, '<div class="loading">No allocations</div>');
    return;
  }

  const peerNames = {};
  (clusterPeers || []).forEach(p => { peerNames[p.id || p.peer_id] = p.peer_name || p.name || (p.id || p.peer_id || '').slice(0, 12); });

  let html = '<table class="cassandra-table"><tr><th>CID</th><th>Node</th><th>RF</th><th>Actions</th></tr>';
  filtered.slice(0, 100).forEach(a => {
    const cidStr = a.cid ? (typeof a.cid === 'object' ? (a.cid['/'] || JSON.stringify(a.cid)) : String(a.cid)) : '?';
    const allocs = a.allocations || a.allocators || [];
    const nodes = allocs.map(id => peerNames[id] || id.slice(0, 12)).join(', ') || '—';
    const repl = `${a.replication_factor_min || a.rf_min || 1}–${a.replication_factor_max || a.rf_max || 1}`;
    html += `<tr>
      <td class="mono" style="font-size:11px;max-width:200px;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(cidStr)}</td>
      <td style="font-size:11px;max-width:150px;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(nodes)}</td>
      <td>${repl}</td>
      <td>
        <button class="btn btn-sm" onclick="document.getElementById('ipfsCid').value='${escapeHtml(cidStr)}';lookupIpfs();">🔍</button>
        <button class="btn btn-sm" onclick="recoverCid('${escapeHtml(cidStr)}')">🔄</button>
      </td>
    </tr>`;
  });
  html += '</table>';
  if (filtered.length > 100) html += `<div style="margin-top:8px;font-size:12px;color:var(--text-muted);">Showing 100 of ${filtered.length}</div>`;
  show(list, html);
}

export async function recoverCid(cid) {
  try {
    await apiPost(`/ipfs/cluster/recover/${encodeURIComponent(cid)}`);
    await loadClusterAllocations();
  } catch (e) { /* ignore */ }
}

// ─── Upload ───
export function initIpfsUpload() {
  const dropZone = $('ipfsDropZone');
  const fileInput = $('ipfsFileInput');
  dropZone.addEventListener('click', () => fileInput.click());
  dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.style.borderColor = 'var(--accent)'; dropZone.style.background = 'rgba(108,92,231,0.08)'; });
  dropZone.addEventListener('dragleave', () => { dropZone.style.borderColor = 'var(--border)'; dropZone.style.background = 'transparent'; });
  dropZone.addEventListener('drop', (e) => { e.preventDefault(); dropZone.style.borderColor = 'var(--border)'; dropZone.style.background = 'transparent'; if (e.dataTransfer.files.length > 0) uploadIpfsFile(e.dataTransfer.files[0]); });
  fileInput.addEventListener('change', () => { if (fileInput.files.length > 0) uploadIpfsFile(fileInput.files[0]); });
}

async function uploadIpfsFile(file) {
  const fillEl = $('ipfsUploadFill');
  $('ipfsUploadProgress').style.display = 'block'; fillEl.style.width = '30%';
  $('ipfsUploadStatus').textContent = `📤 Uploading ${file.name} (${formatBytes(file.size)})...`;
  hide($('ipfsUploadResult'));
  try {
    const form = new FormData(); form.append('file', file);
    const res = await fetch(API + '/ipfs/upload', { method: 'POST', body: form });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    fillEl.style.width = '100%'; $('ipfsUploadStatus').textContent = '✅ Upload complete!';
    show($('ipfsUploadResult'), `<div style="display:flex;flex-direction:column;gap:8px;">
      <div><span style="color:var(--text-muted);">📄 File:</span> <strong>${escapeHtml(data.filename)}</strong></div>
      <div><span style="color:var(--text-muted);">📦 CID:</span> <span class="mono" style="color:var(--accent);font-size:13px;">${data.cid}</span></div>
      <div><span style="color:var(--text-muted);">📏 Size:</span> ${formatBytes(data.size)}</div>
      <div><span style="color:var(--text-muted);">Cluster:</span> <span style="color:var(--green);font-size:12px;">✅ Allocated</span></div>
      <div style="margin-top:6px;">
        <button class="btn btn-sm" onclick="navigator.clipboard.writeText('${data.cid}');this.textContent='✅ Copied!'">📋 Copy CID</button>
        <button class="btn btn-sm" onclick="document.getElementById('ipfsCid').value='${data.cid}';window.lookupIpfs();">🔍 Preview</button>
      </div>
    </div>`);
    $('ipfsUploadResult').style.display = 'block';
    saveIpfsHistory(data);
    await loadClusterAllocations();
  } catch (e) {
    fillEl.style.width = '0%'; $('ipfsUploadStatus').textContent = '❌ Upload failed';
    show($('ipfsUploadResult'), '❌ ' + e.message);
  }
}

// ─── Lookup ───

export async function lookupIpfs() {
  const cid = $('ipfsCid').value.trim();
  if (!cid) return;
  hide($('ipfsImagePreview'));
  try {
    const data = await apiGet('/ipfs/info/' + cid);
    let html = `<div style="margin-bottom:12px;display:flex;gap:16px;flex-wrap:wrap;">
      <span style="font-size:12px;color:var(--text-muted);">📦 CID: <span class="mono" style="color:var(--accent);">${escapeHtml(cid)}</span></span>
      <span style="font-size:12px;color:var(--text-muted);">📏 Size: <strong>${formatBytes(data[data.length - 1].TotalSize)}</strong></span>
    </div>`;
    show($('ipfsResult'), html);
    $('ipfsPreviewImg').src = API + '/ipfs/' + cid;
    $('ipfsPreviewImg').onload = () => { $('ipfsImagePreview').style.display = 'block'; };
    $('ipfsPreviewImg').onerror = () => { hide($('ipfsImagePreview')); };
  } catch (e) { show($('ipfsResult'), '❌ ' + e.message); }
}

export async function downloadIpfs() {
  const cid = $('ipfsCid').value.trim();
  if (!cid) return;
  try {
    const res = await fetch(API + '/ipfs/' + cid);
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = cid;
    document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url);
    show($('ipfsResult'), `✅ Downloaded ${formatBytes(blob.size)}`);
  } catch (e) { show($('ipfsResult'), '❌ ' + e.message); }
}

// ─── History ───

function saveIpfsHistory(data) {
  const cid = typeof data.cid === 'object' ? (data.cid['/'] || JSON.stringify(data.cid)) : String(data.cid || '');
  let history = JSON.parse(localStorage.getItem('ipfs_history') || '[]');
  history.unshift({ cid, filename: data.filename || 'file', size: data.size || 0, time: Date.now() });
  if (history.length > 20) history = history.slice(0, 20);
  localStorage.setItem('ipfs_history', JSON.stringify(history));
  renderIpfsHistory();
}

function renderIpfsHistory() {
  const history = JSON.parse(localStorage.getItem('ipfs_history') || '[]');
  if (history.length === 0) { $('ipfsHistoryCard').style.display = 'none'; return; }
  $('ipfsHistoryCard').style.display = 'block';
  let html = '<table class="cassandra-table"><tr><th>File</th><th>CID</th><th>Size</th><th></th></tr>';
  history.forEach(h => {
    const cidStr = String(h.cid || '');
    html += `<tr>
      <td style="max-width:120px;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(h.filename)}</td>
      <td class="mono" style="max-width:120px;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(cidStr.slice(0,16))}…</td>
      <td>${formatBytes(h.size)}</td>
      <td><button class="btn btn-sm" onclick="document.getElementById('ipfsCid').value='${escapeHtml(cidStr)}';window.lookupIpfs();">🔍</button></td>
    </tr>`;
  });
  html += '</table>';
  show($('ipfsHistoryList'), html);
}

export function clearIpfsHistory() { localStorage.removeItem('ipfs_history'); renderIpfsHistory(); }

// Init on load
renderIpfsHistory();

// Expose for onclick
window.lookupIpfs = lookupIpfs;
window.downloadIpfs = downloadIpfs;
window.clearIpfsHistory = clearIpfsHistory;
window.refreshIpfsAll = refreshIpfsAll;
window.recoverCid = recoverCid;