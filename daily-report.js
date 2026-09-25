// Daily closing report rendering and file exports.
// Totals always come from the API so screen, CSV and PDF figures match.

function reportMoney(value) {
  return `LKR ${Number(value || 0).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function buildSummaryTable(rows, emptyMessage) {
  if (!rows.length) return `<p class="muted">${emptyMessage}</p>`;

  const tableRows = rows.map((row) => `
    <tr>
      <td>${row.name}</td>
      <td>${row.quantity}</td>
      <td>${reportMoney(row.amount)}</td>
    </tr>
  `).join('');

  return `
    <table>
      <thead><tr><th>Name</th><th>Qty</th><th>Amount</th></tr></thead>
      <tbody>${tableRows}</tbody>
    </table>
  `;
}

function buildCreditPaymentTable(rows) {
  if (!rows.length) {
    return '<p class="muted">No credit payments were collected on this day.</p>';
  }

  const tableRows = rows.map((row) => `
    <tr>
      <td>${row.paid_at}</td>
      <td><b>${row.invoice}</b></td>
      <td>${row.received_by}</td>
      <td>${row.method}</td>
      <td>${row.note || '—'}</td>
      <td>${reportMoney(row.amount)}</td>
    </tr>
  `).join('');

  return `
    <table>
      <thead><tr><th>Date</th><th>Invoice</th><th>Collected By</th><th>Method</th><th>Note</th><th>Amount</th></tr></thead>
      <tbody>${tableRows}</tbody>
    </table>
  `;
}

function dailyReportQuery(date) {
  const cashier = document.querySelector('#report-cashier')?.value || '';
  const params = new URLSearchParams({ date });

  // Counter users are scoped server-side. Admins can select a specific cashier.
  if (cashier) params.set('cashier', cashier);

  return params.toString();
}

function reportStatistic(label, value) {
  return `<div class="stat">${label}<strong>${value}</strong></div>`;
}

function renderDailyReport(report) {
  const statistics = [
    ['Cashier', report.cashier],
    ['Sales Before Discounts', reportMoney(report.sales_before_discount)],
    ['Total Discounts Given', `− ${reportMoney(report.discount_total)}`],
    ['Sales After Discounts', reportMoney(report.gross_total)],
    ['Net Sales', reportMoney(report.total)],
    ['Cash to Balance', reportMoney(report.cash_total)],
    ['Card Sales', reportMoney(report.card_total)],
    ['Credit Payments Collected', reportMoney(report.credit_received_total)],
    ['Credit Collections', report.credit_payment_count],
    ['Bills Created', report.bills],
    ['Returns Processed', report.return_count],
    ['Return Amount', `− ${reportMoney(report.return_total)}`],
    ['Services Completed', report.service_count],
    ['Service Income', reportMoney(report.service_total)],
    ['Products & Print Income', reportMoney(report.parts_total)],
  ];

  document.querySelector('#daily-report-stats').innerHTML = statistics
    .map(([label, value]) => reportStatistic(label, value))
    .join('');
  document.querySelector('#daily-credit-payments').innerHTML = buildCreditPaymentTable(report.credit_payments || []);
  document.querySelector('#daily-services').innerHTML = buildSummaryTable(report.services, 'No services were completed on this day.');
  document.querySelector('#daily-parts').innerHTML = buildSummaryTable(report.parts, 'No products or print items were sold on this day.');
  document.querySelector('#daily-returns').innerHTML = buildSummaryTable(report.returned_products, 'No products were returned on this day.');
}

async function loadDailyReport() {
  const dateInput = document.querySelector('#report-date');
  const date = dateInput.value || new Date().toISOString().slice(0, 10);

  try {
    const report = await api(`daily-report?${dailyReportQuery(date)}`);
    renderDailyReport(report);
  } catch (error) {
    alert(`Could not generate daily report: ${error.message}`);
  }
}

async function downloadDailyReport(format) {
  const dateInput = document.querySelector('#report-date');
  const date = dateInput.value || new Date().toISOString().slice(0, 10);

  try {
    const response = await fetch(`/api/daily-report.${format}?${dailyReportQuery(date)}`, {
      headers: { 'X-Admin-Token': adminToken },
    });
    if (!response.ok) throw new Error('Export could not be created');

    await saveBlob(`orbix-daily-report-${date}.${format}`, await response.blob());
  } catch (error) {
    alert(`Could not download ${format.toUpperCase()} report: ${error.message}`);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const dateInput = document.querySelector('#report-date');
  if (dateInput) dateInput.value = new Date().toISOString().slice(0, 10);
});
