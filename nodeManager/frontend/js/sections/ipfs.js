import { $, show, hide, escapeHtml, formatBytes, apiGet, API } from '../helpers.js';

// ─── IPFS ───

export async function lookupIpfs() {
  const cid = $('ipfsCid').value.trim();
  if (!cid) return;
  hide($('ipfsImagePreview'));
  try {
    const data = await apiGet('/ipfs/info/' + cid);
    let html = `<div style="margin-bottom:12px;display:flex;gap:16px;flex-wrap:wrap;">
      <span style="font-size:12px;color:var(--text-muted);">📦 CID: <span class="mono" style="color:var(--accent);">${escapeHtml(cid)}</span></span>
      <span style="font-size:12px;color:var(--text-muted);">📏 Size: <strong>${formatBytes(data.size)}</strong></span>
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
      <div style="margin-top:6px;">
        <button class="btn btn-sm" onclick="navigator.clipboard.writeText('${data.cid}');this.textContent='✅ Copied!'">📋 Copy CID</button>
        <button class="btn btn-sm" onclick="document.getElementById('ipfsCid').value='${data.cid}';window.lookupIpfs();">🔍 Preview</button>
      </div>
    </div>`);
    $('ipfsUploadResult').style.display = 'block';
    saveIpfsHistory(data);
  } catch (e) {
    fillEl.style.width = '0%'; $('ipfsUploadStatus').textContent = '❌ Upload failed';
    show($('ipfsUploadResult'), '❌ ' + e.message);
  }
}

// History
function saveIpfsHistory(data) {
  let history = JSON.parse(localStorage.getItem('ipfs_history') || '[]');
  history.unshift({ cid: data.cid, filename: data.filename, size: data.size, time: Date.now() });
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
    html += `<tr>
      <td style="max-width:120px;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(h.filename)}</td>
      <td class="mono" style="max-width:120px;overflow:hidden;text-overflow:ellipsis;">${h.cid.slice(0,16)}…</td>
      <td>${formatBytes(h.size)}</td>
      <td><button class="btn btn-sm" onclick="document.getElementById('ipfsCid').value='${h.cid}';window.lookupIpfs();">🔍</button></td>
    </tr>`;
  });
  html += '</table>';
  show($('ipfsHistoryList'), html);
}

export function clearIpfsHistory() { localStorage.removeItem('ipfs_history'); renderIpfsHistory(); }

// Alias для lazy import из main.js
export const refreshIpfsHistory = renderIpfsHistory;

// Init on load
renderIpfsHistory();

// Expose for onclick
window.lookupIpfs = lookupIpfs;
window.downloadIpfs = downloadIpfs;
window.clearIpfsHistory = clearIpfsHistory;