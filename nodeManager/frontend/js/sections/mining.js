import { $, show, hide, setEl, jsonHighlight, apiGet, apiPost, sleep, sha256 } from '../helpers.js';

// ─── Mining ───

let miningActive = false;
let miningTimer = null;

export async function refreshMiningStats() {
  try {
    const stats = await apiGet('/mine/stats');
    setEl('miningDifficulty', stats.difficulty);
    setEl('miningTotalBlocks', stats.total_blocks);
    $('difficultySlider').value = stats.difficulty;
    $('difficultyValue').textContent = stats.difficulty;
  } catch { /* ignore */ }
}

export async function setDifficulty() {
  const diff = parseInt($('difficultySlider').value);
  try {
    const res = await apiPost('/mine/difficulty', { difficulty: diff });
    show($('difficultyResult'), `✅ Difficulty set to ${res.difficulty}`);
    setTimeout(() => hide($('difficultyResult')), 3000);
  } catch (e) { show($('difficultyResult'), '❌ ' + e.message); }
}

export async function startMining() {
  const minerAddr = $('minerAddress').value.trim();
  if (!minerAddr) { show($('miningResult'), '❌ Enter a miner address'); return; }
  if (miningActive) {
    miningActive = false; $('mineBtn').textContent = '⛏️ START MINING';
    $('mineBtn').style.background = 'var(--accent)'; clearInterval(miningTimer);
    show($('miningStatus'), '⏸️ Mining stopped'); $('miningProgress').style.display = 'none'; return;
  }
  miningActive = true;
  $('mineBtn').textContent = '⏹ STOP MINING'; $('mineBtn').style.background = 'var(--red)';
  $('miningProgress').style.display = 'block'; $('progressFill').style.width = '0%';
  show($('miningStatus'), '📡 Fetching mining task...'); hide($('miningResult'));
  await mineBlock(minerAddr);
}

async function mineBlock(minerAddr) {
  try {
    const task = await apiGet('/mine/task');
    if (!task.transactions || task.transactions.length === 0) {
      show($('miningStatus'), '⏳ No transactions. Waiting...');
      setTimeout(() => { if (miningActive) mineBlock(minerAddr); }, 3000); return;
    }
    show($('miningStatus'), `🧮 Mining ${task.transactions.length} tx(s) (difficulty: ${task.difficulty})...`);
    setEl('miningTxCount', task.transactions.length);
    const target = '0'.repeat(task.difficulty);
    let nonce = 0, hash = '', hashCount = 0;
    const startTime = Date.now();
    clearInterval(miningTimer);
    miningTimer = setInterval(() => {
      if (!miningActive) return;
      const elapsed = (Date.now() - startTime) / 1000;
      const hps = elapsed > 0 ? Math.floor(hashCount / elapsed) : 0;
      $('hashrateText').textContent = `${hps.toLocaleString()} hashes/s`;
      $('nonceText').textContent = `Nonce: ${nonce.toLocaleString()}`;
      setEl('miningHashrate', `${hps.toLocaleString()} H/s`);
    }, 200);
    while (miningActive) {
      for (let i = 0; i < 10000; i++) {
        const d = task.previous_hash + task.merkle_root + task.timestamp + task.difficulty + nonce + minerAddr;
        hash = await sha256(d);
        if (hash.startsWith(target)) {
          clearInterval(miningTimer);
          $('progressFill').style.width = '100%';
          show($('miningStatus'), `🎯 Found nonce: ${nonce}`);
          await submitBlock(task.task_id, nonce, minerAddr, task.timestamp); return;
        }
        nonce++;
      }
      hashCount += 10000;
      $('progressFill').style.width = `${Math.min(95, (nonce % 500000) / 5000)}%`;
      await sleep(0);
    }
    clearInterval(miningTimer);
  } catch (e) {
    miningActive = false; $('mineBtn').textContent = '⛏️ START MINING';
    $('mineBtn').style.background = 'var(--accent)'; clearInterval(miningTimer);
    $('miningProgress').style.display = 'none'; show($('miningResult'), '❌ ' + e.message);
  }
}

async function submitBlock(taskId, nonce, minerAddr, timestamp) {
  try {
    const res = await apiPost('/mine/submit', { task_id: taskId, nonce, miner_address: minerAddr, timestamp });
    show($('miningResult'), '✅ Block mined!<br>' + jsonHighlight(res));
    miningActive = false; $('mineBtn').textContent = '⛏️ START MINING'; $('mineBtn').style.background = 'var(--accent)';
    const { refreshAll } = await import('./overview.js');
    refreshAll(); refreshMiningStats();
    setTimeout(() => {
      if (!miningActive) { $('mineBtn').textContent = '⏹ STOP MINING'; $('mineBtn').style.background = 'var(--red)'; miningActive = true; mineBlock(minerAddr); }
    }, 1000);
  } catch (e) { show($('miningResult'), '❌ Submit failed: ' + e.message); miningActive = false; $('mineBtn').textContent = '⛏️ START MINING'; $('mineBtn').style.background = 'var(--accent)'; }
}

// Expose for onclick
window.refreshMiningStats = refreshMiningStats;
window.setDifficulty = setDifficulty;
window.startMining = startMining;