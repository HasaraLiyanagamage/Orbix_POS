/* Live payment-field behaviour. This script loads after app.js. */
(function initialisePaymentUi() {
  function money(value) {
    return `LKR ${Number(value || 0).toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }

  function currentBillTotal() {
    const totalText = document.querySelector('#total')?.textContent || '0';
    return Number(totalText.replace(/[^0-9.-]/g, '')) || 0;
  }

  function updateCashFieldVisibility(method) {
    const cashFields = document.querySelector('#cash-payment-fields');
    if (!cashFields) return;

    const isCardPayment = method === 'Card';
    cashFields.hidden = isCardPayment;
    cashFields.style.display = isCardPayment ? 'none' : 'block';

    const label = cashFields.querySelector('label');
    if (label) label.textContent = method === 'Credit' ? 'Amount received today' : 'Cash received';
  }

  function updatePaymentResult(method, received, total) {
    const change = method === 'Cash' ? Math.max(0, received - total) : 0;
    const balance = method === 'Credit' ? Math.max(0, total - received) : 0;
    const result = method === 'Credit' ? balance : change;
    const label = method === 'Credit' ? 'Credit balance' : 'Change';

    const amountElement = document.querySelector('#change-amount');
    if (amountElement) amountElement.textContent = money(result);

    const labelElement = amountElement?.parentElement?.querySelector('span');
    if (labelElement) labelElement.textContent = label;

    return { change, balance };
  }

  window.paymentDetails = function paymentDetails(total = currentBillTotal()) {
    const method = document.querySelector('#payment-method')?.value || 'Cash';
    const receivedInput = document.querySelector('#cash-received');
    const enteredAmount = Number(receivedInput?.value || 0);
    const received = method === 'Card' ? total : enteredAmount;

    updateCashFieldVisibility(method);
    const { change, balance } = updatePaymentResult(method, received, total);
    return { method, received, change, balance };
  };

  function refreshPaymentDetails() {
    window.paymentDetails(currentBillTotal());
  }

  document.querySelector('#payment-method')?.addEventListener('change', refreshPaymentDetails);
  document.querySelector('#cash-received')?.addEventListener('input', refreshPaymentDetails);
  document.querySelector('#cash-received')?.addEventListener('change', refreshPaymentDetails);
  refreshPaymentDetails();
}());
