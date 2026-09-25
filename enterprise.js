// Dashboard helpers for the regular PC-printer edition of ORBIX POS.

function dashboardMetric(label, value, detail = '', variant = '') {
  return `<article class="dashboard-metric ${variant}"><span class="metric-label">${label}</span><strong>${value}</strong><small>${detail}</small></article>`;
}

function renderStockAlerts(alerts) {
  const target = document.querySelector('#enterprise-alerts');
  const counter = document.querySelector('#stock-alert-count');
  if (!target) return;

  if (counter) counter.textContent = alerts.length ? `${alerts.length} item${alerts.length === 1 ? '' : 's'} need attention` : 'All stock levels are healthy';
  target.innerHTML = alerts.length
    ? alerts.map(product => {
      const outOfStock = Number(product.stock) === 0;
      return `<div class="dashboard-list-row"><div><b>${product.name}</b><span>Current inventory level</span></div><span class="stock-badge ${outOfStock ? 'out' : ''}">${outOfStock ? 'Out of stock' : `${product.stock} left`}</span></div>`;
    }).join('')
    : '<div class="dashboard-empty">No low-stock or out-of-stock products.<br>Your inventory is in a healthy state.</div>';
}

function renderBestSellers(items) {
  const target = document.querySelector('#enterprise-best-sellers');
  if (!target) return;

  target.innerHTML = items.length
    ? items.map((item, index) => `<div class="dashboard-list-row"><div><b>${index + 1}. ${item.product_name}</b><span>Recorded sale quantity</span></div><span>${item.quantity} unit${Number(item.quantity) === 1 ? '' : 's'}</span></div>`).join('')
    : '<div class="dashboard-empty">No product or service sales recorded yet.</div>';
}

function openPosSales() {
  document.querySelector('.nav[data-page="pos"]')?.click();
}

async function enterpriseDashboard() {
  const dashboard = document.querySelector('#enterprise-dashboard');
  if (!dashboard || userRole !== 'admin') return;

  dashboard.innerHTML = dashboardMetric('Loading dashboard', '…', 'Updating current business information');
  try {
    const response = await fetch('/api/dashboard', { headers: { 'X-Admin-Token': adminToken } });
    if (!response.ok) throw new Error('Dashboard data could not be loaded');
    const data = await response.json();
    dashboard.innerHTML = [
      dashboardMetric('Today’s net sales', lkr(data.daily_sales), `${data.daily_bills || 0} bill${Number(data.daily_bills) === 1 ? '' : 's'} created today`),
      dashboardMetric('Cash to balance', lkr(data.cash_to_balance), 'Cash expected in the counter drawer'),
      dashboardMetric('This month’s net sales', lkr(data.monthly_sales), 'Sales after recorded returns'),
      dashboardMetric('Outstanding credit', lkr(data.credit_outstanding), `${data.customer_count || 0} saved customer${Number(data.customer_count) === 1 ? '' : 's'}`, 'is-credit'),
    ].join('');
    renderStockAlerts(data.low_stock || []);
    renderBestSellers(data.best_selling || []);
  } catch (error) {
    dashboard.innerHTML = dashboardMetric('Dashboard unavailable', '—', 'Refresh the page or check the local server connection.', 'is-warning');
    renderStockAlerts(products.filter(product => product.stock <= 5));
    renderBestSellers([]);
  }
}

async function enterpriseBackup() {
  try {
    const response = await fetch('/api/backup', { headers: { 'X-Admin-Token': adminToken } });
    if (!response.ok) throw new Error('Backup could not be created');
    await saveBlob('orbix-technologies-backup.db', await response.blob());
  } catch (error) {
    alert(`Could not download database backup: ${error.message}`);
  }
}

document.querySelectorAll('.nav').forEach(button => {
  button.addEventListener('click', () => {
    if (button.dataset.page === 'dashboard') enterpriseDashboard();
  });
});
