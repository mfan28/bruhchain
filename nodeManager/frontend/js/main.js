// ─── Main Entry Point ───
import { initTxForm } from './sections/transactions.js';
import { initIpfsUpload } from './sections/ipfs.js';
import { startAutoRefresh, refreshAll } from './sections/overview.js';

// ─── Navigation ───
document.querySelectorAll('.nav-item').forEach(btn => {
  btn.addEventListener('click', async () => {
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    btn.classList.add('active');
    const sectionId = 'section-' + btn.dataset.section;
    document.getElementById(sectionId).classList.add('active');

    // Lazy-load section data
    switch (btn.dataset.section) {
      case 'cassandra': {
        const { refreshCassandra } = await import('./sections/cassandra.js');
        refreshCassandra();
        break;
      }
      case 'blocks': {
        const { refreshBlocks } = await import('./sections/blocks.js');
        refreshBlocks();
        break;
      }
      case 'transactions': {
        const { refreshTransactions } = await import('./sections/transactions.js');
        refreshTransactions();
        break;
      }
      case 'accounts': {
        const { refreshAccounts } = await import('./sections/accounts.js');
        refreshAccounts();
        break;
      }
      case 'mining': {
        const { refreshMiningStats } = await import('./sections/mining.js');
        refreshMiningStats();
        break;
      }
      case 'ipfs': {
        const { refreshIpfsHistory } = await import('./sections/ipfs.js');
        refreshIpfsHistory();
        break;
      }
      case 'nodes': {
        const { refreshNodes } = await import('./sections/nodes.js');
        refreshNodes();
        break;
      }
    }
  });
});

// ─── Init ───
document.addEventListener('DOMContentLoaded', () => {
  initTxForm();
  initIpfsUpload();
  refreshAll();
  startAutoRefresh();
});