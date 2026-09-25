// Shared screen state. The database remains the source of truth; this only holds
// the currently loaded records and the bill being prepared at the counter.
let products = [], services = [], customers = [], employees = [], sales = [], users = [], returns = [], credits = [], auditLogs = [], stockMovements = [], cashClosings = [], cart = [], returnSale = null, checkoutInProgress = false, customerPrices = new Map(); let adminToken = sessionStorage.getItem('ORBIX-admin') || ''; let userSession = JSON.parse(sessionStorage.getItem('ORBIX-user') || 'null'); let userRole = userSession?.role || ''; let currentUser = userSession?.display_name || userSession?.username || ''; let appInfo = { name: 'ORBIX Technologies POS', variant: 'pos' }; if (adminToken && !userRole) { sessionStorage.removeItem('ORBIX-admin'); adminToken = ''; } const lkr = n => 'LKR ' + Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2 });
// The native desktop bridge handles files because embedded Windows WebViews
// do not reliably support browser Blob downloads or pop-up print windows.
function desktopApi() { return window.pywebview?.api || null; }
function bytesToBase64(bytes) { let value = ''; const size = 0x8000; for (let offset = 0; offset < bytes.length; offset += size) value += String.fromCharCode(...bytes.subarray(offset, offset + size)); return btoa(value); }
function textToBase64(text) { return bytesToBase64(new TextEncoder().encode(text)); }
async function saveBlob(filename, blob) { const bridge = desktopApi(); if (bridge?.save_download) { const saved = await bridge.save_download(filename, bytesToBase64(new Uint8Array(await blob.arrayBuffer()))); alert(`Saved to Downloads: ${saved.path}`); return; } const link = document.createElement('a'), url = URL.createObjectURL(blob); link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000); }

// All API calls include the current local-session token. An expired session is
// cleared immediately so protected screens are not shown by mistake.
async function api(path, method = 'GET', body) { const r = await fetch('/api/' + path, { method, headers: { 'Content-Type': 'application/json', 'X-Admin-Token': adminToken }, body: body ? JSON.stringify(body) : undefined }); const d = await r.json().catch(() => ({ error: 'The local server returned an invalid response. Restart python server.py and try again.' })); if (!r.ok) { if (r.status === 403 && d.error === 'Login required' && path !== 'login') { clearLocalSession(); location.reload(); } throw Error(d.error || 'Request failed'); } return d }
async function loadAppInfo() { try { appInfo = await api('app-info'); } catch (_) { /* The POS name remains as a safe fallback during local development. */ } document.title = appInfo.name; const brand = document.querySelector('#brand-name'); const subtitle = document.querySelector('#brand-subtitle'); if (brand) brand.textContent = appInfo.name; if (subtitle) subtitle.textContent = `${appInfo.variant === 'it' ? 'IT Management' : 'POS & Service Management'} · 0707080855`; }
// Login and role handling ------------------------------------------------------
function loginBox() { const d = document.createElement('div'); d.id = 'login-overlay'; d.style = 'position:fixed;inset:0;display:grid;place-items:center;z-index:99'; d.innerHTML = `<form id="login-form" class="login-card"><div class="login-brand"><img src="assets/Orbix.png" alt="ORBIX Technologies"><div><strong>${appInfo.name}</strong><span>Smart Technology. Powerful Solutions.</span></div></div><h2>Welcome back</h2><p>Sign in with your assigned account to access the system.</p><label>USERNAME<input required name="username" autocomplete="username" minlength="3" maxlength="40" placeholder="Enter your username"></label><label>PASSWORD<input required name="password" type="password" autocomplete="current-password" minlength="8" placeholder="Enter your password"></label><button class="primary wide">Sign in securely</button><div class="login-note">Secure local business management system</div></form>`; document.body.append(d); d.querySelector('form').onsubmit = async e => { e.preventDefault(); try { const v = await api('login', 'POST', Object.fromEntries(new FormData(e.target))); adminToken = v.token; userSession = { username: v.username, display_name: v.display_name, role: v.role }; userRole = v.role; currentUser = v.display_name || v.username; sessionStorage.setItem('ORBIX-admin', adminToken); sessionStorage.setItem('ORBIX-user', JSON.stringify(userSession)); d.remove(); load() } catch (x) { alert(x.message) } } }
function clearLocalSession() { sessionStorage.removeItem('ORBIX-admin'); sessionStorage.removeItem('ORBIX-user'); adminToken = ''; userSession = null; userRole = ''; currentUser = ''; cart = []; }
async function logout() { try { await api('logout', 'POST', {}); } catch (_) { /* Local session removal is sufficient if the server was stopped. */ } clearLocalSession(); location.reload(); }
function loggedInName() { return currentUser || 'Counter Operator'; }
// All management forms share these actions so staff can abandon or clear a form
// without having to refresh the POS screen.
function closeModal() {
  const modal = document.querySelector('#modal');
  const form = document.querySelector('#form');
  form.reset();
  form.onsubmit = null;
  modal.classList.remove('show');
}
function clearModalForm() {
  const form = document.querySelector('#form');
  form.querySelectorAll('input, textarea').forEach(field => {
    if (!['hidden', 'button', 'submit'].includes(field.type)) field.value = '';
  });
  form.querySelectorAll('select').forEach(field => { field.selectedIndex = 0; });
  form.querySelector('input:not([type="hidden"]), select, textarea')?.focus();
}
// A single capture-phase guard protects every modal form, including forms added
// later. Server validation remains the final authority for saved records.
document.addEventListener('submit', event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  form.querySelectorAll('input[type="text"], input:not([type]), textarea').forEach(field => { field.value = field.value.trim(); });
  if (!form.checkValidity()) {
    event.preventDefault();
    event.stopImmediatePropagation();
    form.reportValidity();
  }
}, true);
function modalActions(saveLabel) {
  return `<div class="form-actions"><button type="button" class="secondary" onclick="clearModalForm()">Clear</button><button type="button" class="secondary" onclick="closeModal()">Close</button><button class="primary">${saveLabel}</button></div>`;
}
function showModal(title) {
  document.querySelector('#modal-title').textContent = title;
  document.querySelector('#modal').classList.add('show');
}
function applyRoleAccess() { const isAdmin = userRole === 'admin'; document.querySelectorAll('.admin-only').forEach(button => button.style.display = isAdmin ? '' : 'none'); const picker = document.querySelector('#cashier-picker'); const counterCashier = document.querySelector('#counter-cashier'); if (picker) picker.style.display = isAdmin ? '' : 'none'; if (counterCashier) counterCashier.style.display = isAdmin ? 'none' : ''; if (!isAdmin) { document.querySelectorAll('.page').forEach(page => page.classList.remove('active')); document.querySelector('#pos')?.classList.add('active'); document.querySelectorAll('.nav').forEach(button => button.classList.toggle('active', button.dataset.page === 'pos')); } }
async function load() { try { const paths = userRole === 'admin' ? ['products', 'services', 'customers', 'employees', 'sales', 'users', 'returns', 'credits', 'audit-logs', 'stock-movements', 'cash-closings', 'system-status'] : ['products', 'services', 'customers', 'employees', 'sales', 'returns', 'credits', 'cash-closings']; const data = await Promise.all(paths.map(path => api(path))); [products, services, customers, employees, sales] = data; if (userRole === 'admin') { users=data[5]; returns=data[6]; credits=data[7]; auditLogs=data[8]; stockMovements=data[9]; cashClosings=data[10]; window.orbixSystemStatus=data[11]; } else { users=[]; returns=data[5]; credits=data[6]; cashClosings=data[7]; auditLogs=[]; stockMovements=[]; } applyRoleAccess(); render() } catch (e) { alert('Run python3 server.py first.\n' + e.message) } }
// Render functions keep POS cards and management tables in sync after each save.
function matchingCustomers(searchText = '') {
  const search = searchText.trim().toLowerCase();
  return customers.filter(customer => !search || `${customer.name} ${customer.phone || ''}`.toLowerCase().includes(search));
}
function renderCustomerOptions(searchText = '', selectedId = '') {
  const select = document.querySelector('#customer');
  if (!select) return;
  const matches = matchingCustomers(searchText);
  select.innerHTML = '<option value="" disabled>Select or add customer</option>' + matches
    .map(customer => `<option value="${customer.id}">${customer.name}${customer.phone ? ` — ${customer.phone}` : ''}</option>`)
    .join('');
  select.value = matches.some(customer => String(customer.id) === String(selectedId)) ? selectedId : '';
}
function selectedCustomer() {
  return customers.find(customer => String(customer.id) === String(document.querySelector('#customer')?.value));
}
function priceKey(item) {
  return `${item.type === 'service' ? 'service' : 'product'}:${item.service_id || item.id}`;
}
function itemPrice(item) {
  return Number(customerPrices.get(priceKey(item)) ?? item.standard_price ?? item.price);
}
async function applyCustomerPricing() {
  const customer = selectedCustomer();
  const note = document.querySelector('#customer-price-tier');
  customerPrices = new Map();
  if (customer) {
    try {
      const prices = await api(`customers/${customer.id}/prices`);
      customerPrices = new Map(prices.map(price => [`${price.item_type}:${price.item_id}`, Number(price.price)]));
    } catch (error) { console.warn('Customer prices could not be loaded', error); }
  }
  if (note) note.textContent = customer ? (customerPrices.size ? `${customerPrices.size} customer-specific price${customerPrices.size === 1 ? '' : 's'} applied` : 'Standard retail prices') : 'Select customer to apply the correct price';
  if (customer) cart.forEach(item => { item.price = itemPrice(item); });
  productsView(); cartView();
}
function filterCustomers() {
  const search = document.querySelector('#customer-search')?.value || '';
  const suggestions = document.querySelector('#customer-suggestions');
  const query = search.trim();
  if (!suggestions) return;

  // Waiting for two characters avoids showing a long, ambiguous customer list.
  if (query.length < 2) {
    suggestions.innerHTML = '';
    suggestions.classList.remove('show');
    return;
  }

  const matches = matchingCustomers(query).slice(0, 8);
  suggestions.innerHTML = matches.length
    ? matches.map(customer => `<button type="button" class="customer-suggestion" onclick="selectCustomerSuggestion(${customer.id})"><strong>${customer.name}</strong><small>${customer.phone || 'No phone number'}${customer.vehicle ? ` · ${customer.vehicle}` : ''}</small></button>`).join('')
    : '<div class="muted" style="padding:11px 12px">No matching customers found.</div>';
  suggestions.classList.add('show');
}
function selectCustomerSuggestion(customerId) {
  const customer = customers.find(item => String(item.id) === String(customerId));
  if (!customer) return;
  renderCustomerOptions('', customer.id);
  const search = document.querySelector('#customer-search');
  const suggestions = document.querySelector('#customer-suggestions');
  if (search) search.value = '';
  if (suggestions) {
    suggestions.innerHTML = '';
    suggestions.classList.remove('show');
  }
  applyCustomerPricing();
}
function clearCustomerSearch() {
  const search = document.querySelector('#customer-search');
  const suggestions = document.querySelector('#customer-suggestions');
  if (search) search.value = '';
  if (suggestions) {
    suggestions.innerHTML = '';
    suggestions.classList.remove('show');
  }
  const selectedId = document.querySelector('#customer')?.value || '';
  renderCustomerOptions('', selectedId);
  applyCustomerPricing();
}
function selectCustomerFromSearch(event) {
  if (event.key !== 'Enter') return;
  event.preventDefault();
  const search = event.currentTarget.value;
  const matches = matchingCustomers(search);
  if (!matches.length) return alert('No customer matches that name or phone number. Use Add Customer to create one.');
  const exact = matches.find(customer => customer.name.toLowerCase() === search.trim().toLowerCase() || String(customer.phone || '') === search.trim());
  const selected = exact || matches[0];
  selectCustomerSuggestion(selected.id);
}
function render() { renderCustomerOptions(); const cashier = document.querySelector('#cashier'); if (cashier) cashier.innerHTML = employees.map(x => `<option value="${x.id}">${x.name} (${x.role})</option>`).join(''); const reportCashier = document.querySelector('#report-cashier'); const closingCashier = document.querySelector('#closing-cashier'); const names = [...new Set([...users.filter(user => user.role === 'counter').map(user => user.display_name), ...sales.map(sale => sale.employee_name).filter(Boolean)])].sort((a, b) => a.localeCompare(b)); if (reportCashier && userRole === 'admin') { const selected = reportCashier.value; reportCashier.innerHTML = '<option value="">All Cashiers</option>' + names.map(name => `<option value="${name}">${name}</option>`).join(''); reportCashier.value = names.includes(selected) ? selected : ''; } if (closingCashier && userRole === 'admin') closingCashier.innerHTML = '<option value="">Select cashier</option>' + names.map(name => `<option value="${name}">${name}</option>`).join(''); productsView(); servicesView(); customersView(); employeesView(); usersView(); salesView(); returnsView(); creditsView(); cashClosingsView(); operationsView(); cartView(); applyCustomerPricing(); const name = loggedInName(), n = document.querySelector('#employee-name'), activeCashier = document.querySelector('#active-cashier'); if (n) n.textContent = name; if (activeCashier) activeCashier.textContent = name; const closingDate=document.querySelector('#closing-date'); if (closingDate && !closingDate.value) closingDate.value=new Date().toISOString().slice(0,10); }
function clearInventoryFilters() {
  const search = document.querySelector('#inventory-search');
  const category = document.querySelector('#inventory-category');
  const sort = document.querySelector('#inventory-sort');
  if (search) search.value = '';
  if (category) category.value = '';
  if (sort) sort.value = 'name';
  productsView();
}
function productsView() {
  const q = (document.querySelector('#scan')?.value || '').toLowerCase();
  const list = products.filter(p => (p.name + p.sku).toLowerCase().includes(q));
  const serviceList = services.filter(s => (s.name + s.code).toLowerCase().includes(q));
  const cards = list.map(p => `<article class="card" onclick="add(${p.id})"><span class="muted">PRODUCT · ${p.category}</span><h3>${p.name}</h3><span class="muted">${p.sku} · Warranty: ${p.warranty || '90 Days'}</span><p><b class="price">${lkr(p.price)}</b> · ${p.stock} in stock</p></article>`).join('') + serviceList.map(s => `<article class="card" onclick="addService(${s.id})"><span class="muted">SERVICE · ${s.duration || 'Standard'}</span><h3>${s.name}</h3><span class="muted">${s.code}</span><p><b class="price">${lkr(s.price)}</b> · No stock deduction</p></article>`).join('');
  document.querySelector('#product-list').innerHTML = cards || '<p>No matching product or service.</p>';

  const searchField = document.querySelector('#inventory-search');
  const categoryField = document.querySelector('#inventory-category');
  const sortField = document.querySelector('#inventory-sort');
  const search = (searchField?.value || '').trim().toLowerCase();
  const selectedCategory = categoryField?.value || '';
  const categories = [...new Set(products.map(product => (product.category || 'Uncategorized').trim() || 'Uncategorized'))]
    .sort((a, b) => a.localeCompare(b));

  // Keep the filter list in sync whenever a product category is added, edited or deleted.
  if (categoryField) {
    categoryField.innerHTML = '<option value="">All categories</option>' + categories
      .map(category => `<option value="${category}">${category}</option>`).join('');
    categoryField.value = categories.includes(selectedCategory) ? selectedCategory : '';
  }

  const filteredProducts = products.filter(product => {
    const category = (product.category || 'Uncategorized').trim() || 'Uncategorized';
    const searchable = `${product.name} ${product.sku} ${category}`.toLowerCase();
    return (!search || searchable.includes(search)) && (!selectedCategory || category === selectedCategory);
  });
  const sort = sortField?.value || 'name';
  filteredProducts.sort((a, b) => {
    if (sort === 'stock-low') return Number(a.stock) - Number(b.stock) || a.name.localeCompare(b.name);
    if (sort === 'stock-high') return Number(b.stock) - Number(a.stock) || a.name.localeCompare(b.name);
    if (sort === 'category') return (a.category || 'Uncategorized').localeCompare(b.category || 'Uncategorized') || a.name.localeCompare(b.name);
    return a.name.localeCompare(b.name);
  });

  const table = document.querySelector('#products-table');
  if (table) table.innerHTML = filteredProducts.map(p => `<tr><td>${p.name}</td><td>${p.sku}</td><td>${p.category || 'Uncategorized'}</td><td>${p.warranty || '90 Days'}</td><td>${lkr(p.price)}</td><td>${p.stock}</td><td><button onclick="openForm('product',${p.id})">Edit</button> <button onclick="removeRow('products',${p.id})">Delete</button></td></tr>`).join('') || '<tr><td colspan="7" class="muted">No products match the selected search or category.</td></tr>';
  const stats = document.querySelector('#product-stats');
  if (stats) stats.innerHTML = `<div class="stat">Products<strong>${filteredProducts.length}</strong></div><div class="stat">Units<strong>${filteredProducts.reduce((total, product) => total + Number(product.stock || 0), 0)}</strong></div><div class="stat">Low stock<strong>${filteredProducts.filter(product => Number(product.stock) < 6).length}</strong></div>`;
}
function servicesView() { const t = document.querySelector('#services-table'); if (t) t.innerHTML = services.map(s => `<tr><td><b>${s.name}</b></td><td>${s.code}</td><td>${s.duration || '—'}</td><td>${lkr(s.price)}</td><td><button onclick="openForm('service',${s.id})">Edit</button> <button onclick="removeRow('services',${s.id})">Delete</button></td></tr>`).join('') }
function customersView() { const t = document.querySelector('#customers-table'); if (t) t.innerHTML = customers.map(x => `<tr><td>${x.name}</td><td>${x.phone || '—'}</td><td>${x.vehicle || '—'}</td><td>${x.email || '—'}</td><td><button onclick="openForm('customer',${x.id})">Edit</button> <button onclick="removeRow('customers',${x.id})">Delete</button></td></tr>`).join('') }
function employeesView() { const t = document.querySelector('#employees-table'); if (t) t.innerHTML = employees.map(x => `<tr><td>${x.name}</td><td>${x.role}</td><td>${x.phone || '—'}</td><td>Active</td><td><button onclick="openForm('employee',${x.id})">Edit</button> <button onclick="removeRow('employees',${x.id})">Delete</button></td></tr>`).join('') }
function usersView() { const t = document.querySelector('#users-table'); if (t) t.innerHTML = users.map(user => `<tr><td>${user.display_name}</td><td>${user.username}</td><td>${user.role === 'admin' ? 'Admin' : 'Counter'}</td><td><button onclick="openUserForm(${user.id})">Edit / Reset Password</button> <button onclick="removeUser(${user.id})">Delete</button></td></tr>`).join('') || '<tr><td colspan="4">No user accounts found.</td></tr>'; }
// User accounts are separate from employee records so every cashier can have an
// individual sign-in while sales are traceable to the person at the counter.
function openUserForm(id) { const user = id ? users.find(item => item.id === id) : {}; const f = document.querySelector('#form'); document.querySelector('#modal-title').textContent = id ? 'Edit User Account' : 'Add User Account'; f.innerHTML = `<label>Full name<input required name="display_name" value="${String(user.display_name || '').replaceAll('"', '&quot;')}"></label><label>Username<input required name="username" pattern="[A-Za-z0-9._-]{3,40}" title="3-40 letters, numbers, dots, hyphens or underscores" value="${String(user.username || '').replaceAll('"', '&quot;')}"></label><label>Privilege<select name="role"><option value="counter" ${user.role === 'counter' ? 'selected' : ''}>Counter - POS sales only</option><option value="admin" ${user.role === 'admin' ? 'selected' : ''}>Admin - full access</option></select></label><label>${id ? 'New password (leave blank to keep current password)' : 'Password'}<input ${id ? '' : 'required'} name="password" type="password" minlength="8"><small class="muted">Use at least 8 characters.</small></label><button class="primary">Save Account</button>`; f.onsubmit = async event => { event.preventDefault(); try { await api('users' + (id ? '/' + id : ''), id ? 'PUT' : 'POST', Object.fromEntries(new FormData(f))); document.querySelector('#modal').classList.remove('show'); load(); } catch (error) { alert(error.message); } }; document.querySelector('#modal').classList.add('show'); }
async function removeUser(id) { if (!confirm('Delete this user account? The user will no longer be able to log in.')) return; try { await api('users/' + id, 'DELETE'); load(); } catch (error) { alert(error.message); } }
function matchingSales(searchText = '') {
  const search = searchText.trim().toLowerCase();
  return sales.filter(sale => !search || [
    sale.invoice,
    sale.sold_at,
    sale.customer_name,
    sale.employee_name,
    sale.method,
    sale.total,
  ].join(' ').toLowerCase().includes(search));
}
function filterSales() {
  salesView(document.querySelector('#sales-search')?.value || '');
}
function clearSalesSearch() {
  const input = document.querySelector('#sales-search');
  if (input) input.value = '';
  salesView();
}
function salesView(searchText = '') {
  const matching = matchingSales(searchText);
  const total = matching.reduce((sum, sale) => sum + Number(sale.total || 0), 0);
  const table = document.querySelector('#sales-table');
  if (table) {
    table.innerHTML = matching.map(sale => `<tr><td><button class="invoice-link" onclick="viewInvoice('${sale.invoice}')" title="View invoice">${sale.invoice}</button>${sale.status === 'Voided' ? '<div class="status-void">Voided</div>' : ''}</td><td>${sale.sold_at}</td><td>${sale.customer_name}</td><td>${sale.employee_name || '—'}</td><td>${sale.method}</td><td>${lkr(sale.total)}${userRole === 'admin' && sale.status !== 'Voided' ? `<br><button class="secondary" style="margin-top:6px;padding:5px 8px" onclick="voidInvoice('${sale.invoice}')">Void</button>` : ''}</td></tr>`).join('')
      || '<tr><td colspan="6" class="muted">No invoices match this search.</td></tr>';
  }
  const stats = document.querySelector('#sales-stats');
  if (stats) stats.innerHTML = `<div class="stat">Sales<strong>${lkr(total)}</strong></div><div class="stat">Transactions<strong>${matching.length}</strong></div><div class="stat">Average<strong>${lkr(matching.length ? total / matching.length : 0)}</strong></div>`;
  const count = document.querySelector('#sales-search-count');
  if (count) count.textContent = searchText.trim() ? `${matching.length} matching invoice${matching.length === 1 ? '' : 's'}` : `${sales.length} invoice${sales.length === 1 ? '' : 's'} recorded`;
}
// Re-create a saved invoice from its immutable sale-items record. This avoids
// using current product prices or stock values when an older bill is viewed.
async function viewInvoice(invoice) {
  try {
    const data = await api(`sales/${encodeURIComponent(invoice)}/items`);
    const savedCart = cart;
    cart = data.items.map(item => ({ id:item.product_id || `sale-item-${item.id}`, name:item.product_name, price:Number(item.unit_price), qty:Number(item.quantity), type:item.item_type || 'product', warranty:item.warranty || '90 Days', line_discount:Number(item.line_discount || 0) }));
    const customer = customers.find(item => item.name === data.sale.customer_name) || { name:data.sale.customer_name || 'Walk-in Customer' };
    const payment = { method:data.sale.method || 'Cash', received:Number(data.sale.payment_received || data.sale.total), change:Number(data.sale.payment_change || 0), balance:data.sale.method === 'Credit' ? Math.max(0, Number(data.sale.total) - Number(data.sale.payment_received || 0)) : 0 };
    printInvoice(data.sale, Number(data.sale.subtotal), Number(data.sale.discount), customer, payment, { name:data.sale.employee_name }, 'Total discounts', false);
    cart = savedCart;
  } catch (error) { alert(`Could not open invoice: ${error.message}`); }
}
function returnsView() { const table = document.querySelector('#returns-table'); if (table) table.innerHTML = returns.map(item => `<tr><td><b>${item.return_no}</b></td><td>${item.invoice}</td><td>${item.customer_name || 'Walk-in Customer'}</td><td>${item.processed_by}</td><td>${item.returned_at}</td><td>${item.item_count}</td><td>${lkr(item.refund_total)}</td></tr>`).join('') || '<tr><td colspan="7" class="muted">No product returns have been processed.</td></tr>'; }
// Outstanding credit is calculated on the server from the original bill and all
// later collections. The client only displays the remaining balance.
function creditsView() { const table = document.querySelector('#credits-table'); if (table) table.innerHTML = credits.map(item => `<tr><td><b>${item.invoice}</b></td><td>${item.customer_name || 'Walk-in Customer'}</td><td>${item.sold_at}</td><td>${lkr(item.total)}</td><td>${lkr(Number(item.payment_received) + Number(item.credit_paid))}</td><td><b class="low">${lkr(item.credit_balance)}</b></td><td><button class="primary" onclick="openCreditPayment('${item.invoice}',${item.credit_balance})">Collect</button></td></tr>`).join('') || '<tr><td colspan="7" class="muted">No outstanding credit balances.</td></tr>'; }
function openCreditPayment(invoice, balance) { const f = document.querySelector('#form'); document.querySelector('#modal-title').textContent = 'Collect Credit Payment'; f.innerHTML = `<p class="scan-note"><b>Invoice:</b> ${invoice}<br><b>Outstanding balance:</b> ${lkr(balance)}</p><label>Amount received<input required name="amount" type="number" min="0.01" max="${balance}" step="0.01" value="${balance}"></label><label>Payment method<select name="method"><option value="Cash">Cash</option><option value="Card">Card</option></select></label><label>Note<input name="note" placeholder="Optional"></label><button class="primary">Save Payment</button>`; f.onsubmit = async event => { event.preventDefault(); try { const result = await api('credits/payments', 'POST', { invoice, ...Object.fromEntries(new FormData(f)) }); document.querySelector('#modal').classList.remove('show'); alert(`Payment saved. Remaining balance: ${lkr(result.remaining_balance)}`); load(); } catch (error) { alert(error.message); } }; document.querySelector('#modal').classList.add('show'); }
async function findReturnInvoice() { const input = document.querySelector('#return-invoice'), invoice = input?.value.trim(); if (!invoice) return alert('Enter the invoice number first.'); try { const data = await api(`sales/${encodeURIComponent(invoice)}/items`); returnSale = data.sale; const details = document.querySelector('#return-sale-details'); details.innerHTML = `<b>Invoice:</b> ${data.sale.invoice} &nbsp; <b>Customer:</b> ${data.sale.customer_name || 'Walk-in Customer'} &nbsp; <b>Sale Total:</b> ${lkr(data.sale.total)}`; const returnable = data.items.filter(item => item.product_id && item.remaining_quantity > 0); document.querySelector('#return-items').innerHTML = returnable.length ? `<table><thead><tr><th>Product</th><th>Sold</th><th>Already Returned</th><th>Available to Return</th><th>Return Qty</th></tr></thead><tbody>${returnable.map(item => `<tr><td>${item.product_name}</td><td>${item.quantity}</td><td>${item.returned_quantity}</td><td>${item.remaining_quantity}</td><td><input data-return-id="${item.id}" type="number" min="0" max="${item.remaining_quantity}" value="0" style="width:80px;padding:7px"></td></tr>`).join('')}</tbody></table>` : '<p class="muted">This invoice has no returnable products. Services cannot be returned as stock.</p>'; document.querySelector('#return-actions').style.display = returnable.length ? 'block' : 'none'; } catch (error) { returnSale = null; document.querySelector('#return-items').innerHTML = ''; document.querySelector('#return-actions').style.display = 'none'; alert(error.message); } }
async function processReturn() { if (!returnSale) return alert('Find an invoice before processing a return.'); const items = [...document.querySelectorAll('[data-return-id]')].map(input => ({ sale_item_id: Number(input.dataset.returnId), quantity: Number(input.value || 0) })).filter(item => item.quantity > 0); if (!items.length) return alert('Enter a return quantity for at least one product.'); try { const result = await api('returns', 'POST', { invoice: returnSale.invoice, items, reason: document.querySelector('#return-reason')?.value || '' }); const outcome = result.status === 'Pending' ? 'Submitted for admin approval. Stock will be restored after approval.' : 'Approved and stock restored.'; alert(`Return ${result.return_no} ${outcome} Refund amount: ${lkr(result.refund_total)}`); returnSale = null; document.querySelector('#return-invoice').value = ''; document.querySelector('#return-sale-details').textContent = 'Enter the invoice number from the customer\'s bill.'; document.querySelector('#return-items').innerHTML = ''; document.querySelector('#return-actions').style.display = 'none'; await load(); } catch (error) { alert(error.message); } }
function csvValue(value) { const text = String(value ?? ''); return `"${(/^[=+\-@]/.test(text) ? "'" : '') + text.replaceAll('"', '""')}"`; }
// CSV exports quote every cell and neutralise spreadsheet formulas in user data.
async function exportSales() {
  if (!sales.length) return alert('There are no sales to export yet.');
  const header = ['Invoice', 'Date & Time', 'Customer', 'Cashier', 'Payment Method', 'Subtotal (LKR)', 'Discount (LKR)', 'Total (LKR)', 'Cash Received (LKR)', 'Change (LKR)'];
  const rows = sales.map(sale => [sale.invoice, sale.sold_at, sale.customer_name, sale.employee_name || '', sale.method, Number(sale.subtotal || 0).toFixed(2), Number(sale.discount || 0).toFixed(2), Number(sale.total || 0).toFixed(2), Number(sale.payment_received || 0).toFixed(2), Number(sale.payment_change || 0).toFixed(2)]);
  const content = '\uFEFF' + [header, ...rows].map(row => row.map(csvValue).join(',')).join('\r\n');
  const file = new Blob([content], { type: 'text/csv;charset=utf-8' });
  try { await saveBlob(`orbix-sales-report-${new Date().toISOString().slice(0, 10)}.csv`, file); } catch (error) { alert(`Could not export CSV: ${error.message}`); }
}
function add(id) { const p = products.find(x => x.id === id), i = cart.find(x => x.id === id); if (!p.stock) return alert('Product is out of stock'); if (i) { if (i.qty >= p.stock) return alert('Insufficient stock'); i.qty++ } else cart.push({ ...p, standard_price:Number(p.price), price:itemPrice(p), qty: 1, line_discount_type: 'percent', line_discount_value: 0 }); document.querySelector('#scan').value = ''; productsView(); cartView() }
// Cart values update immediately for the cashier; the server recalculates the
// same totals before saving so browser-side values cannot become the final bill.
function addService(id) { const s = services.find(x => x.id === id), key = `service-${id}`, i = cart.find(x => x.id === key); if (i) i.qty++; else cart.push({ ...s, id: key, service_id: id, type: 'service', standard_price:Number(s.price), price:itemPrice(s), qty: 1, line_discount_type: 'percent', line_discount_value: 0 }); document.querySelector('#scan').value = ''; productsView(); cartView() }
function itemQtyLimit(item) {
  // Services do not consume stock. A practical cap prevents accidental entries
  // such as an extra zero while still allowing large design or print orders.
  if (item.type === 'service' || item.service_id) return 999;
  const product = products.find(productItem => String(productItem.id) === String(item.id));
  return Math.max(0, Number(product?.stock ?? item.stock ?? 0));
}
function setQty(id, value) {
  const item = cart.find(cartItem => String(cartItem.id) === String(id));
  if (!item) return;

  const requested = Number(value);
  if (!Number.isInteger(requested) || requested < 1) {
    alert('Quantity must be a whole number of at least 1.');
    cartView();
    return;
  }

  const limit = itemQtyLimit(item);
  if (requested > limit) {
    alert(item.type === 'service' || item.service_id
      ? 'A service quantity cannot exceed 999.'
      : `Only ${limit} unit(s) of ${item.name} are available in stock.`);
    cartView();
    return;
  }

  item.qty = requested;
  cartView();
}
function qty(id, change) {
  // Product IDs are numeric, while services use IDs such as "service-4".
  // Compare their string values so both types can be changed safely.
  const item = cart.find(cartItem => String(cartItem.id) === String(id));
  if (!item) return;
  const nextQuantity = Number(item.qty) + Number(change);
  if (nextQuantity < 1) {
    cart = cart.filter(cartItem => String(cartItem.id) !== String(id));
    cartView();
    return;
  }
  setQty(id, nextQuantity);
}
function clearCart() { cart = []; cartView() }
function paymentDetails(total) { const method = document.querySelector('#payment-method')?.value || 'Cash'; const receivedInput = document.querySelector('#cash-received'); const received = method === 'Card' ? total : Number(receivedInput?.value || 0); const change = method === 'Cash' ? Math.max(0, received - total) : 0; const balance = method === 'Credit' ? Math.max(0, total - received) : 0; const cashFields = document.querySelector('#cash-payment-fields'); if (cashFields) cashFields.style.display = method === 'Card' ? 'none' : 'block'; const cashLabel = cashFields?.querySelector('label'); if (cashLabel) cashLabel.textContent = method === 'Credit' ? 'Amount received today' : 'Cash received'; const changeField = document.querySelector('#change-amount'); if (changeField) changeField.textContent = method === 'Credit' ? lkr(balance) : lkr(change); const changeLabel = changeField?.parentElement?.querySelector('span'); if (changeLabel) changeLabel.textContent = method === 'Credit' ? 'Credit balance' : 'Change'; return { method, received, change, balance }; }
function lineDiscountDetails(item) {
  const lineTotal = Number(item.price || 0) * Number(item.qty || 0);
  const type = item.line_discount_type === 'amount' ? 'amount' : 'percent';
  const rawValue = Number(item.line_discount_value || 0);
  const value = Number.isFinite(rawValue) ? Math.max(0, rawValue) : 0;
  const amount = Math.min(lineTotal, type === 'percent' ? lineTotal * Math.min(value, 100) / 100 : value);
  return { amount, type, value };
}
function setLineDiscount(id, field, value) {
  const item = cart.find(cartItem => String(cartItem.id) === String(id));
  if (!item) return;
  if (field === 'type') item.line_discount_type = value === 'amount' ? 'amount' : 'percent';
  else item.line_discount_value = value;
  cartView();
}
function discountDetails(subtotal) { const type = document.querySelector('#discount-type')?.value || 'percent'; const rawValue = Number(document.querySelector('#discount-value')?.value || 0); const value = Number.isFinite(rawValue) ? Math.max(0, rawValue) : 0; const amount = Math.min(subtotal, type === 'percent' ? subtotal * Math.min(value, 100) / 100 : value); return { amount, label: type === 'percent' ? `Bill discount (${value}%)` : 'Bill discount (LKR)' }; }
function cartView() {
  const subtotal = cart.reduce((total, item) => total + item.price * item.qty, 0);
  const itemDiscount = cart.reduce((total, item) => total + lineDiscountDetails(item).amount, 0);
  const discountInfo = discountDetails(subtotal - itemDiscount);
  const billDiscount = discountInfo.amount;
  const total = subtotal - itemDiscount - billDiscount;
  const cartElement = document.querySelector('#cart');

  cartElement.innerHTML = cart.length
    ? cart.map((item, index) => { const line = lineDiscountDetails(item), quantityLimit = itemQtyLimit(item); return `<div class="cart-line"><b><span class="item-number">${index + 1}</span>${item.name}</b><span>${lkr(item.price * item.qty - line.amount)}</span><div class="qty"><button type="button" aria-label="Decrease ${item.name} quantity" onclick='qty(${JSON.stringify(item.id)}, -1)'>−</button><input type="number" min="1" max="${quantityLimit}" step="1" value="${item.qty}" aria-label="Quantity for ${item.name}" onchange='setQty(${JSON.stringify(item.id)}, this.value)' onkeydown='if(event.key === "Enter") this.blur()'><button type="button" aria-label="Increase ${item.name} quantity" onclick='qty(${JSON.stringify(item.id)}, 1)'>+</button></div><div class="line-discount"><label>Item discount</label><select onchange='setLineDiscount(${JSON.stringify(item.id)}, "type", this.value)'><option value="percent" ${line.type === 'percent' ? 'selected' : ''}>%</option><option value="amount" ${line.type === 'amount' ? 'selected' : ''}>LKR</option></select><input type="number" min="0" step="0.01" value="${line.value}" aria-label="${item.name} item discount" oninput='setLineDiscount(${JSON.stringify(item.id)}, "value", this.value)'></div></div>`; }).join('')
    : '<p class="muted">No products on this bill.</p>';

  document.querySelector('#subtotal').textContent = lkr(subtotal);
  const itemDiscountField = document.querySelector('#item-discount');
  if (itemDiscountField) itemDiscountField.textContent = '− ' + lkr(itemDiscount);
  const discountField = document.querySelector('#discount') || document.querySelector('#tax');
  if (discountField) {
    discountField.textContent = '− ' + lkr(billDiscount);
    const label = document.querySelector('#discount-label') || discountField.parentElement.querySelector('span');
    if (label) label.textContent = discountInfo.label;
  }
  document.querySelector('#total').textContent = lkr(total);
  paymentDetails(total);
}
async function checkout() {
  if (checkoutInProgress) return;
  if (!cart.length) return alert('Add products first');

  const subtotal = cart.reduce((total, item) => total + item.price * item.qty, 0);
  const itemDiscount = cart.reduce((total, item) => total + lineDiscountDetails(item).amount, 0);
  const discountInfo = discountDetails(subtotal - itemDiscount);
  const discount = discountInfo.amount;
  const total = subtotal - itemDiscount - discount;
  const customerId = document.querySelector('#customer')?.value;
  const customer = customers.find(item => item.id == customerId);
  const cashier = userRole === 'admin'
    ? employees.find(item => item.id == document.querySelector('#cashier')?.value)
    : { name: loggedInName() };
  const payment = paymentDetails(total);

  if (!customer) return alert('Select an existing customer or add a new customer before creating a bill.');
  if (payment.method === 'Cash' && payment.received < total) return alert('Cash received must be equal to or greater than the total.');
  if (payment.method === 'Credit' && (payment.received < 0 || payment.received >= total)) return alert('For credit sales, enter an amount less than the total.');

  const button = document.querySelector('#checkout-button');
  checkoutInProgress = true;
  if (button) { button.disabled = true; button.textContent = 'Saving bill…'; }
  // The native Windows bridge opens invoices after the sale is saved. Browsers
  // still use a temporary popup so the same source works in localhost mode.
  window.orbixInvoiceWindow = desktopApi()?.print_invoice ? null : window.open('', '_blank', 'width=920,height=1100');

  try {
    const sale = await api('sales', 'POST', {
      items: cart,
      customer_id: customer.id,
      customer_name: customer.name,
      employee_name: cashier?.name || employees[0]?.name || '',
      method: payment.method,
      subtotal,
      discount,
      tax: 0,
      total,
      payment_received: payment.received,
      payment_change: payment.change,
    });
    const confirmedPayment = {
      method: payment.method,
      received: sale.payment_received,
      change: sale.payment_change,
      balance: payment.method === 'Credit' ? Math.max(0, sale.total - sale.payment_received) : 0,
    };
    printInvoice(sale, sale.subtotal, sale.discount, customer, confirmedPayment, cashier, 'Total discounts');
    cart = [];
    await load();
  } catch (error) {
    window.orbixInvoiceWindow?.close();
    window.orbixInvoiceWindow = null;
    alert(error.message);
  } finally {
    checkoutInProgress = false;
    if (button) { button.disabled = false; button.textContent = 'Confirm Payment & Print Receipt'; }
  }
}
// Invoices are designed for the connected PC printer in A4 or A5 size. They
// use server-confirmed values returned by checkout, not browser-only figures.
function printInvoice(s, subtotal, discount, c, payment = { method: 'Cash', received: subtotal - discount, change: 0 }, cashier = null, discountLabel = 'Discount', autoPrint = true) {
  const printSize = document.querySelector('#print-size')?.value || 'a4', a5 = printSize === 'a5';
  const total = subtotal - discount, cashierName = cashier?.name || s.employee_name || 'Counter Operator', invoiceDate = s.sold_at || new Date().toLocaleString(), qr = `${location.origin}/api/qr?value=${encodeURIComponent(`ORBIX|${s.invoice}`)}`;
  const rows = cart.map((item, index) => { const lineDiscount = Number(item.line_discount || item.line_discount_amount || lineDiscountDetails(item).amount || 0); return `<tr><td class="center">${index + 1}</td><td>${item.name}${lineDiscount ? `<br><small>Item discount: - ${lkr(lineDiscount)}</small>` : ''}</td><td>${item.type === 'service' ? '-' : (item.warranty || '90 Days')}</td><td class="center">${item.qty}</td><td class="right">${Number(item.price * item.qty - lineDiscount).toFixed(2)}</td></tr>`; }).join('');
  const paymentRows = payment.method === 'Cash' ? `<div class="amount-row"><span>Cash Received</span><b>${lkr(payment.received)}</b></div><div class="amount-row"><span>Change</span><b>${lkr(payment.change)}</b></div>` : payment.method === 'Credit' ? `<div class="amount-row"><span>Amount Received</span><b>${lkr(payment.received)}</b></div><div class="amount-row"><span>Credit Balance</span><b>${lkr(payment.balance)}</b></div>` : `<div class="amount-row"><span>Card Payment</span><b>${lkr(total)}</b></div>`;
  // The supplied logo has generous transparent padding. Cover mode crops only
  // that padding in the invoice header, keeping the printed mark readable.
  const page = `@page{size:${a5 ? 'A5' : 'A4'} portrait;margin:${a5 ? '9mm' : '12mm'}}body{font:${a5 ? '10px' : '12px'} Arial,sans-serif}.invoice{width:100%;max-width:${a5 ? '130mm' : '190mm'};margin:auto}.head{display:flex;align-items:center;border-bottom:2px solid #174b8f;padding-bottom:${a5 ? '8px' : '12px'}}.logo{width:${a5 ? '76mm' : '116mm'};height:${a5 ? '24mm' : '34mm'};object-fit:cover;object-position:center}.contact{margin-left:auto;text-align:right;line-height:1.65;color:#334155;font-size:${a5 ? '8px' : '10px'}}.title{font-size:${a5 ? '13px' : '16px'};letter-spacing:${a5 ? '1px' : '2px'};padding:${a5 ? '6px' : '8px'};margin:${a5 ? '9px' : '13px'} 0}.details{display:grid;grid-template-columns:1fr ${a5 ? '76px' : '105px'};gap:${a5 ? '8px' : '12px'};align-items:start}.info{padding:${a5 ? '7px' : '10px'};line-height:1.7}.customer{padding:${a5 ? '7px' : '10px'};margin-top:${a5 ? '7px' : '10px'}}.qr{width:${a5 ? '68px' : '94px'};height:${a5 ? '68px' : '94px'}}table{margin-top:${a5 ? '10px' : '15px'}}th,td{padding:${a5 ? '6px' : '9px'}}.totals{width:${a5 ? '240px' : '300px'};margin:${a5 ? '10px' : '14px'} 0 0 auto}.amount-row{padding:${a5 ? '5px' : '6px'}}.net{font-size:${a5 ? '13px' : '16px'}}.terms{margin-top:${a5 ? '16px' : '24px'};padding-top:10px;font-size:${a5 ? '8px' : '10px'};line-height:1.7}.thanks{margin-top:${a5 ? '16px' : '22px'};font-size:${a5 ? '11px' : '14px'}}.powered{font-size:${a5 ? '8px' : '9px'};margin-top:8px}`;
  const head = '<tr><th class="center" style="width:7%">No.</th><th style="width:41%">Item</th><th style="width:20%">Warranty</th><th class="center" style="width:10%">Qty</th><th class="right" style="width:22%">Amount (LKR)</th></tr>';
  const bridge = desktopApi();
  const w = bridge?.print_invoice ? {
    document: {
      write(html) { bridge.print_invoice(`${s.invoice}.html`, textToBase64(html)).catch(error => alert(`Could not open invoice: ${error.message}`)); },
      close() {},
    },
  } : window.orbixInvoiceWindow || window.open('', '_blank', 'width=920,height=1100'); window.orbixInvoiceWindow = null;
  if (!w) return alert('Could not open the invoice window.');
  const previewAction = autoPrint ? '' : '<div class="preview-actions"><button onclick="print()">Print Invoice</button></div>';
  w.document.write(`<!doctype html><html><head><title>${s.invoice} - ${appInfo.name}</title><style>*{box-sizing:border-box}body{margin:0;color:#152238}.preview-actions{max-width:980px;margin:16px auto 0;text-align:right}.preview-actions button{padding:9px 14px;border:0;border-radius:6px;background:#1d4f91;color:#fff;font:600 14px Arial;cursor:pointer}.title{background:#174b8f;color:#fff;text-align:center;font-weight:bold}.info,.customer{border:1px dashed #64748b}.center{text-align:center}.right{text-align:right}table{width:100%;border-collapse:collapse}th{background:#e7edf6;color:#102f5b;text-align:left;border-bottom:2px solid #174b8f}td{border-bottom:1px solid #cbd5e1;vertical-align:top}.amount-row{display:flex;justify-content:space-between;border-bottom:1px solid #cbd5e1}.net{font-weight:bold;background:#e7edf6;border-top:2px solid #174b8f;border-bottom:2px solid #174b8f}.terms{border-top:1px dashed #475569}.thanks{text-align:center;font-weight:bold}.powered{text-align:center;color:#64748b}@media print{.preview-actions{display:none}body{print-color-adjust:exact;-webkit-print-color-adjust:exact}}${page}</style></head><body>${previewAction}<div class="invoice"><div class="head"><img class="logo" src="${location.origin}/assets/Orbix.png" alt="ORBIX Technologies"><div class="contact">No. 08, Naiwala Jct., Veyangoda<br>Tel / WhatsApp: 0707080855<br>orbixtechnologies24x7@gmail.com</div></div><div class="title">RETAIL INVOICE</div><div class="details"><div><div class="info"><b>Invoice No:</b> ${s.invoice}<br><b>Date:</b> ${invoiceDate}<br><b>Cashier:</b> ${cashierName}<br><b>Payment:</b> ${payment.method}</div><div class="customer"><b>CUSTOMER DETAILS</b><br>${c?.name || 'Walk-in Customer'}${c?.phone ? ` · ${c.phone}` : ''}${c?.vehicle ? `<br><b>Device / Job:</b> ${c.vehicle}` : ''}</div></div><img class="qr" src="${qr}" alt="Invoice QR"></div><table><thead>${head}</thead><tbody>${rows}</tbody></table><div class="totals"><div class="amount-row"><span>Sub Total</span><b>${lkr(subtotal)}</b></div><div class="amount-row"><span>${discountLabel}</span><b>- ${lkr(discount)}</b></div><div class="amount-row net"><span>NET TOTAL</span><b>${lkr(total)}</b></div>${paymentRows}</div><div class="terms"><b>WARRANTY CONDITIONS</b><br>1. Warranty covers manufacturer defects only.<br>2. Warranty is void for physical or liquid damage, power surges, seal tampering and misuse.<br>3. Original invoice must be presented for all warranty claims.</div><div class="thanks">*** Thank You, Come Again! ***</div><div class="powered">System Powered by ${appInfo.name} · 0707080855</div></div><script>onload=()=>${autoPrint ? 'print()' : 'void 0'}<\/script></body></html>`); w.document.close();
}
function openForm(type, id) {
  const data = { product: products, service: services, customer: customers, employee: employees }[type];
  const record = id ? data.find(item => item.id === id) : {};
  const spec = { product: [['name', 'Product'], ['sku', 'SKU / Barcode'], ['category', 'Category'], ['warranty', 'Warranty (e.g. 90 Days)'], ['price', 'Price', 'number'], ['stock', 'Stock', 'number']], service: [['name', 'Service name'], ['code', 'Service code'], ['duration', 'Estimated duration'], ['price', 'Price', 'number']], customer: [['name', 'Name'], ['phone', 'Phone'], ['vehicle', 'Device / Job Reference'], ['email', 'Email']], employee: [['name', 'Name'], ['role', 'Role'], ['phone', 'Phone']] }[type];
  const form = document.querySelector('#form');
  const existingRoles = [...new Set(employees.map(employee => String(employee.role || '').trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  document.querySelector('#modal-title').textContent = (id ? 'Edit ' : 'Add ') + type;
  form.innerHTML = spec.map(field => {
    const value = String(record[field[0]] || (field[0] === 'warranty' ? '90 Days' : '')).replaceAll('"', '&quot;');
    const roleList = type === 'employee' && field[0] === 'role'
      ? ` list="employee-role-suggestions" autocomplete="off" placeholder="Type at least 2 letters"`
      : '';
    return `<label>${field[1]}<input required name="${field[0]}" type="${field[2] || 'text'}" value="${value}"${roleList}></label>`;
  }).join('') + (type === 'employee' ? `<datalist id="employee-role-suggestions">${existingRoles.map(role => `<option value="${role.replaceAll('"', '&quot;')}">`).join('')}</datalist><p class="scan-note">Type two letters to choose an existing role, or enter a new role carefully.</p>` : '') + modalActions('Save');
  form.onsubmit = async event => { event.preventDefault(); try { await api(type + 's' + (id ? '/' + id : ''), id ? 'PUT' : 'POST', Object.fromEntries(new FormData(form))); closeModal(); load(); } catch (error) { alert(error.message); } };
  document.querySelector('#modal').classList.add('show');
}
function openQuickCustomerForm() { const f = document.querySelector('#form'); document.querySelector('#modal-title').textContent = 'Add Customer to Bill'; f.innerHTML = '<label>Customer name<input required name="name" autofocus></label><label>Phone number<input name="phone" inputmode="tel"></label><label>Device / Job reference<input name="vehicle" placeholder="Optional"></label><label>Email<input name="email" type="email" placeholder="Optional"></label><button class="primary">Save & Select Customer</button>'; f.onsubmit = async event => { event.preventDefault(); try { const customer = await api('customers', 'POST', Object.fromEntries(new FormData(f))); customers.push(customer); render(); document.querySelector('#customer').value = customer.id; document.querySelector('#modal').classList.remove('show'); } catch (error) { alert(error.message); } }; document.querySelector('#modal').classList.add('show'); }

// Modal form implementations --------------------------------------------------
// Keep every Add/Edit screen consistent: users can clear entries, close safely,
// or save without leaving an unfinished form behind.
function openUserForm(id) {
  const user = id ? users.find(item => item.id === id) : {};
  const form = document.querySelector('#form');
  showModal(id ? 'Edit User Account' : 'Add User Account');
  form.innerHTML = `
    <label>Full name<input required name="display_name" maxlength="120" value="${String(user.display_name || '').replaceAll('"', '&quot;')}"></label>
    <label>Username<input required name="username" pattern="[A-Za-z0-9._-]{3,40}" title="3-40 letters, numbers, dots, hyphens or underscores" value="${String(user.username || '').replaceAll('"', '&quot;')}"></label>
    <label>Privilege<select name="role"><option value="counter" ${user.role === 'counter' ? 'selected' : ''}>Counter - POS sales only</option><option value="admin" ${user.role === 'admin' ? 'selected' : ''}>Admin - full access</option></select></label>
    <label>${id ? 'New password (leave blank to keep current password)' : 'Password'}<input ${id ? '' : 'required'} name="password" type="password" minlength="8"><small class="muted">Use at least 8 characters.</small></label>
    ${modalActions('Save Account')}`;
  form.onsubmit = async event => {
    event.preventDefault();
    try {
      await api(`users${id ? `/${id}` : ''}`, id ? 'PUT' : 'POST', Object.fromEntries(new FormData(form)));
      closeModal();
      load();
    } catch (error) { alert(error.message); }
  };
}

function openCreditPayment(invoice, balance) {
  const form = document.querySelector('#form');
  showModal('Collect Credit Payment');
  form.innerHTML = `
    <p class="scan-note"><b>Invoice:</b> ${invoice}<br><b>Outstanding balance:</b> ${lkr(balance)}</p>
    <label>Amount received<input required name="amount" type="number" min="0.01" max="${balance}" step="0.01" value="${balance}"></label>
    <label>Payment method<select name="method"><option value="Cash">Cash</option><option value="Card">Card</option></select></label>
    <label>Note<input name="note" placeholder="Optional"></label>
    ${modalActions('Save Payment')}`;
  form.onsubmit = async event => {
    event.preventDefault();
    try {
      const result = await api('credits/payments', 'POST', { invoice, ...Object.fromEntries(new FormData(form)) });
      closeModal();
      alert(`Payment saved. Remaining balance: ${lkr(result.remaining_balance)}`);
      load();
    } catch (error) { alert(error.message); }
  };
}

function openForm(type, id) {
  const records = { product: products, service: services, customer: customers, employee: employees }[type];
  const record = id ? records.find(item => item.id === id) : {};
  const fields = {
    product: [['name', 'Product'], ['sku', 'SKU / Barcode'], ['category', 'Category'], ['warranty', 'Warranty (e.g. 90 Days)'], ['price', 'Price', 'number'], ['stock', 'Stock', 'number']],
    service: [['name', 'Service name'], ['code', 'Service code'], ['duration', 'Estimated duration'], ['price', 'Price', 'number']],
    customer: [['name', 'Name'], ['phone', 'Phone'], ['vehicle', 'Device / Job Reference'], ['email', 'Email']],
    employee: [['name', 'Name'], ['role', 'Role'], ['phone', 'Phone']],
  }[type];
  const form = document.querySelector('#form');
  // Reuse the exact category spelling already saved in the catalogue. Native
  // datalist suggestions appear as the cashier starts typing the category.
  const categoryOptions = type === 'product'
    ? [...new Set(products.map(item => String(item.category || '').trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b))
    : [];
  const categoryList = categoryOptions.length
    ? `<datalist id="product-category-options">${categoryOptions.map(category => `<option value="${category.replaceAll('"', '&quot;')}"></option>`).join('')}</datalist>`
    : '<datalist id="product-category-options"></datalist>';
  showModal(`${id ? 'Edit' : 'Add'} ${type}`);
  const roleOptions = type === 'employee'
    ? [...new Set(employees.map(item => String(item.role || '').trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b))
    : [];
  const roleList = type === 'employee' ? `<datalist id="employee-role-options">${roleOptions.map(role => `<option value="${role.replaceAll('"', '&quot;')}"></option>`).join('')}</datalist>` : '';
  form.innerHTML = fields.map(([name, label, inputType]) => {
    const fallback = name === 'warranty' ? '90 Days' : '';
    const value = String(record[name] || fallback).replaceAll('"', '&quot;');
    const list = type === 'product' && name === 'category' ? ' list="product-category-options" autocomplete="off"' : type === 'employee' && name === 'role' ? ' list="employee-role-options" autocomplete="off" placeholder="Type at least 2 letters"' : '';
    const validation = name === 'price' ? ' min="0.01" max="100000000" step="0.01"' : name === 'stock' ? ' min="0" max="1000000" step="1"' : name === 'email' ? ' maxlength="120"' : name === 'phone' ? ' pattern="[0-9+()\\- ]{7,30}" title="Use 7-30 digits or + ( ) -"' : name === 'sku' || name === 'code' ? ' pattern="[A-Za-z0-9._/-]{2,60}" title="Use 2-60 letters, numbers, dots, hyphens, underscores or slashes"' : ' maxlength="120"';
    const typeValue = name === 'email' ? 'email' : name === 'phone' ? 'tel' : (inputType || 'text');
    const required = ['phone', 'vehicle', 'email', 'duration'].includes(name) ? '' : ' required';
    return `<label>${label}<input${required} name="${name}" type="${typeValue}" value="${value}"${list}${validation}></label>`;
  }).join('') + (type === 'product' ? categoryList : '') + roleList + modalActions('Save');
  form.onsubmit = async event => {
    event.preventDefault();
    try {
      await api(`${type}s${id ? `/${id}` : ''}`, id ? 'PUT' : 'POST', Object.fromEntries(new FormData(form)));
      closeModal();
      load();
    } catch (error) { alert(error.message); }
  };
}

function openQuickCustomerForm() {
  const form = document.querySelector('#form');
  showModal('Add Customer to Bill');
  form.innerHTML = `
    <label>Customer name<input required name="name" autofocus></label>
    <label>Phone number<input name="phone" type="tel" inputmode="tel" pattern="[0-9+()\- ]{7,30}" title="Use 7-30 digits or + ( ) -"></label>
    <label>Device / Job reference<input name="vehicle" placeholder="Optional"></label>
    <label>Email<input name="email" type="email" maxlength="120" placeholder="Optional"></label>
    ${modalActions('Save & Select Customer')}`;
  form.onsubmit = async event => {
    event.preventDefault();
    try {
      const customer = await api('customers', 'POST', Object.fromEntries(new FormData(form)));
      customers.push(customer);
      render();
      document.querySelector('#customer').value = customer.id;
      applyCustomerPricing();
      closeModal();
    } catch (error) { alert(error.message); }
  };
}
// Cards always show the price that applies to the currently selected customer.
function productsView() {
  const q = (document.querySelector('#scan')?.value || '').toLowerCase();
  const productList = products.filter(p => (p.name + p.sku).toLowerCase().includes(q));
  const serviceList = services.filter(s => (s.name + s.code).toLowerCase().includes(q));
  const cards = productList.map(p => `<article class="card" onclick="add(${p.id})"><span class="muted">PRODUCT · ${p.category}</span><h3>${p.name}</h3><span class="muted">${p.sku} · Warranty: ${p.warranty || '90 Days'}</span><p><b class="price">${lkr(itemPrice(p))}</b> · ${p.stock} in stock</p></article>`).join('') + serviceList.map(s => `<article class="card" onclick="addService(${s.id})"><span class="muted">SERVICE · ${s.duration || 'Standard'}</span><h3>${s.name}</h3><span class="muted">${s.code}</span><p><b class="price">${lkr(itemPrice(s))}</b> · No stock deduction</p></article>`).join('');
  document.querySelector('#product-list').innerHTML = cards || '<p>No matching product or service.</p>';

  const searchField = document.querySelector('#inventory-search');
  const categoryField = document.querySelector('#inventory-category');
  const sortField = document.querySelector('#inventory-sort');
  const search = (searchField?.value || '').trim().toLowerCase();
  const selectedCategory = categoryField?.value || '';
  const categories = [...new Set(products.map(product => (product.category || 'Uncategorized').trim() || 'Uncategorized'))]
    .sort((a, b) => a.localeCompare(b));

  // Keep this menu correct after staff add, edit or delete a product category.
  if (categoryField) {
    categoryField.innerHTML = '<option value="">All categories</option>' + categories
      .map(category => `<option value="${category}">${category}</option>`).join('');
    categoryField.value = categories.includes(selectedCategory) ? selectedCategory : '';
  }

  const filteredProducts = products.filter(product => {
    const category = (product.category || 'Uncategorized').trim() || 'Uncategorized';
    const searchable = `${product.name} ${product.sku} ${category}`.toLowerCase();
    return (!search || searchable.includes(search)) && (!selectedCategory || category === selectedCategory);
  });
  const sort = sortField?.value || 'name';
  filteredProducts.sort((a, b) => {
    if (sort === 'stock-low') return Number(a.stock) - Number(b.stock) || a.name.localeCompare(b.name);
    if (sort === 'stock-high') return Number(b.stock) - Number(a.stock) || a.name.localeCompare(b.name);
    if (sort === 'category') return (a.category || 'Uncategorized').localeCompare(b.category || 'Uncategorized') || a.name.localeCompare(b.name);
    return a.name.localeCompare(b.name);
  });

  const table = document.querySelector('#products-table');
  if (table) table.innerHTML = filteredProducts.map(p => `<tr><td>${p.name}</td><td>${p.sku}</td><td>${p.category || 'Uncategorized'}</td><td>${p.warranty || '90 Days'}</td><td>${lkr(p.price)}</td><td>${p.stock}</td><td><button onclick="openForm('product',${p.id})">Edit</button> <button onclick="removeRow('products',${p.id})">Delete</button></td></tr>`).join('') || '<tr><td colspan="7" class="muted">No products match the selected search or category.</td></tr>';
  const stats = document.querySelector('#product-stats');
  if (stats) stats.innerHTML = `<div class="stat">Products<strong>${filteredProducts.length}</strong></div><div class="stat">Units<strong>${filteredProducts.reduce((total, product) => total + Number(product.stock || 0), 0)}</strong></div><div class="stat">Low stock<strong>${filteredProducts.filter(product => Number(product.stock) < 6).length}</strong></div>`;
}
function servicesView() {
  const table = document.querySelector('#services-table');
  if (table) table.innerHTML = services.map(s => `<tr><td><b>${s.name}</b></td><td>${s.code}</td><td>${s.duration || '—'}</td><td>${lkr(s.price)}</td><td><button onclick="openForm('service',${s.id})">Edit</button> <button onclick="removeRow('services',${s.id})">Delete</button></td></tr>`).join('');
}
function customersView() {
  const table = document.querySelector('#customers-table');
  if (table) table.innerHTML = customers.map(c => `<tr><td>${c.name}</td><td>${c.phone || '—'}</td><td>${c.vehicle || '—'}</td><td>${c.email || '—'}</td><td><button class="primary" onclick="openCustomerPrices(${c.id})">Set Prices</button> <button onclick="openForm('customer',${c.id})">Edit</button> <button onclick="removeRow('customers',${c.id})">Delete</button></td></tr>`).join('') || '<tr><td colspan="5" class="muted">No customers saved yet.</td></tr>';
}
// Customer-specific prices replace the retail price only for this customer's bills.
async function openCustomerPrices(customerId) {
  const customer = customers.find(item => item.id === customerId);
  if (!customer) return;
  try {
    const saved = await api(`customers/${customerId}/prices`);
    const savedMap = new Map(saved.map(item => [`${item.item_type}:${item.item_id}`, item.price]));
    const rows = [
      ...products.map(item => ({ ...item, item_type: 'product', item_id: item.id, code: item.sku })),
      ...services.map(item => ({ ...item, item_type: 'service', item_id: item.id, code: item.code })),
    ];
    const form = document.querySelector('#form');
    showModal(`Set Prices — ${customer.name}`);
    form.innerHTML = `<p class="scan-note">Leave a field empty to use the normal retail price. Saved amounts apply only to ${customer.name}.</p><div class="customer-price-list">${rows.map(item => { const key = `${item.item_type}:${item.item_id}`; const price = savedMap.get(key); return `<label><span><b>${item.name}</b><small>${item.item_type === 'product' ? 'Product' : 'Service'} · ${item.code} · Normal: ${lkr(item.price)}</small></span><input data-customer-price type="number" min="0" step="0.01" placeholder="Normal price" value="${price ?? ''}" data-item-type="${item.item_type}" data-item-id="${item.item_id}"></label>`; }).join('')}</div>${modalActions('Save Customer Prices')}`;
    form.onsubmit = async event => {
      event.preventDefault();
      const prices = [...form.querySelectorAll('[data-customer-price]')].filter(input => input.value.trim() !== '').map(input => ({ item_type: input.dataset.itemType, item_id: Number(input.dataset.itemId), price: Number(input.value) }));
      try {
        await api(`customers/${customerId}/prices`, 'POST', { prices });
        closeModal();
        if (String(selectedCustomer()?.id) === String(customerId)) await applyCustomerPricing();
        alert('Customer prices saved.');
      } catch (error) { alert(error.message); }
    };
  } catch (error) { alert(error.message); }
}
async function removeRow(type, id) { if (!confirm('Delete this record?')) return; try { await api(type + '/' + id, 'DELETE'); load() } catch (e) { alert(e.message) } }
// Clicking the shaded area or pressing Escape closes the current form as well.
document.querySelector('#modal').addEventListener('click', event => {
  if (event.target.id === 'modal') closeModal();
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && document.querySelector('#modal').classList.contains('show')) closeModal();
});
document.querySelectorAll('.nav').forEach(b => b.onclick = () => { document.querySelectorAll('.nav').forEach(x => x.classList.remove('active')); b.classList.add('active'); document.querySelectorAll('.page').forEach(x => x.classList.remove('active')); document.querySelector('#' + b.dataset.page).classList.add('active') }); document.querySelector('#scan').oninput = productsView; document.querySelector('#scan').onkeydown = e => { if (e.key === 'Enter') { const code = e.target.value.toLowerCase(); const p = products.find(x => x.sku.toLowerCase() === code); const service = services.find(x => x.code.toLowerCase() === code); const customer = customers.find(x => String(x.phone || '').toLowerCase() === code || `customer-${x.id}`.toLowerCase() === code); if (p) add(p.id); else if (service) addService(service.id); else if (customer) { document.querySelector('#customer').value = customer.id; alert(`Customer selected: ${customer.name}`); e.target.value = ''; applyCustomerPricing(); } else alert('No matching product, service or customer QR card found.'); e.preventDefault() } }; loadAppInfo().finally(() => { if (adminToken) load(); else loginBox(); });

// Management lists share a small client-side filter layer. The database remains
// unchanged; this only helps staff find the required saved record quickly.
function managementSearch(rows, section, fields) {
  const query = (document.querySelector(`#${section}-search`)?.value || '').trim().toLowerCase();
  return rows.filter(row => !query || fields.some(field => String(row[field] ?? '').toLowerCase().includes(query)));
}
function managementSort(section, fallback) {
  return document.querySelector(`#${section}-sort`)?.value || fallback;
}
function compareText(left, right) {
  return String(left ?? '').localeCompare(String(right ?? ''), undefined, { sensitivity: 'base' });
}
function showManagementCount(section, visible, total, label) {
  const target = document.querySelector(`#${section}-filter-count`);
  if (target) target.textContent = visible === total ? `${total} ${label}` : `${visible} of ${total} ${label}`;
}
function clearManagementFilters(section) {
  const search = document.querySelector(`#${section}-search`);
  const sort = document.querySelector(`#${section}-sort`);
  if (search) search.value = '';
  if (sort) sort.selectedIndex = 0;
  ({ services: servicesView, customers: customersView, employees: employeesView, users: usersView, credits: creditsView, returns: returnsView }[section])?.();
}
function servicesView() {
  const visible = managementSearch(services, 'services', ['name', 'code', 'duration']);
  const sort = managementSort('services', 'name');
  visible.sort((a, b) => {
    if (sort === 'code') return compareText(a.code, b.code);
    if (sort === 'price-low') return Number(a.price) - Number(b.price) || compareText(a.name, b.name);
    if (sort === 'price-high') return Number(b.price) - Number(a.price) || compareText(a.name, b.name);
    return compareText(a.name, b.name);
  });
  const table = document.querySelector('#services-table');
  if (table) table.innerHTML = visible.map(service => `<tr><td><b>${service.name}</b></td><td>${service.code}</td><td>${service.duration || '—'}</td><td>${lkr(service.price)}</td><td><button onclick="openForm('service',${service.id})">Edit</button> <button onclick="removeRow('services',${service.id})">Delete</button></td></tr>`).join('') || '<tr><td colspan="5" class="muted">No services match this search.</td></tr>';
  showManagementCount('services', visible.length, services.length, 'services');
}
function customersView() {
  const visible = managementSearch(customers, 'customers', ['name', 'phone', 'vehicle', 'email']);
  const sort = managementSort('customers', 'name');
  visible.sort((a, b) => {
    if (sort === 'name-desc') return compareText(b.name, a.name);
    if (sort === 'phone') return compareText(a.phone, b.phone) || compareText(a.name, b.name);
    if (sort === 'recent') return Number(b.id) - Number(a.id);
    return compareText(a.name, b.name);
  });
  const table = document.querySelector('#customers-table');
  if (table) table.innerHTML = visible.map(customer => `<tr><td>${customer.name}</td><td>${customer.phone || '—'}</td><td>${customer.vehicle || '—'}</td><td>${customer.email || '—'}</td><td><button class="primary" onclick="openCustomerPrices(${customer.id})">Set Prices</button> <button onclick="openForm('customer',${customer.id})">Edit</button> <button onclick="removeRow('customers',${customer.id})">Delete</button></td></tr>`).join('') || '<tr><td colspan="5" class="muted">No customers match this search.</td></tr>';
  showManagementCount('customers', visible.length, customers.length, 'customers');
}
function employeesView() {
  const visible = managementSearch(employees, 'employees', ['name', 'role', 'phone']);
  const sort = managementSort('employees', 'name');
  visible.sort((a, b) => sort === 'role' ? compareText(a.role, b.role) || compareText(a.name, b.name) : sort === 'phone' ? compareText(a.phone, b.phone) || compareText(a.name, b.name) : compareText(a.name, b.name));
  const table = document.querySelector('#employees-table');
  if (table) table.innerHTML = visible.map(employee => `<tr><td>${employee.name}</td><td>${employee.role}</td><td>${employee.phone || '—'}</td><td>Active</td><td><button onclick="openForm('employee',${employee.id})">Edit</button> <button onclick="removeRow('employees',${employee.id})">Delete</button></td></tr>`).join('') || '<tr><td colspan="5" class="muted">No employees match this search.</td></tr>';
  showManagementCount('employees', visible.length, employees.length, 'employees');
}
function usersView() {
  const visible = managementSearch(users, 'users', ['display_name', 'username', 'role']);
  const sort = managementSort('users', 'name');
  visible.sort((a, b) => sort === 'username' ? compareText(a.username, b.username) : sort === 'role' ? compareText(a.role, b.role) || compareText(a.display_name, b.display_name) : compareText(a.display_name, b.display_name));
  const table = document.querySelector('#users-table');
  if (table) table.innerHTML = visible.map(user => `<tr><td>${user.display_name}</td><td>${user.username}</td><td>${user.role === 'admin' ? 'Admin' : 'Counter'}</td><td><button onclick="openUserForm(${user.id})">Edit / Reset Password</button> <button onclick="removeUser(${user.id})">Delete</button></td></tr>`).join('') || '<tr><td colspan="4" class="muted">No user accounts match this search.</td></tr>';
  showManagementCount('users', visible.length, users.length, 'accounts');
}
function creditsView() {
  const visible = managementSearch(credits, 'credits', ['invoice', 'customer_name', 'sold_at']);
  const sort = managementSort('credits', 'date-new');
  visible.sort((a, b) => {
    if (sort === 'date-old') return compareText(a.sold_at, b.sold_at);
    if (sort === 'customer') return compareText(a.customer_name, b.customer_name);
    if (sort === 'balance-high') return Number(b.credit_balance) - Number(a.credit_balance);
    if (sort === 'balance-low') return Number(a.credit_balance) - Number(b.credit_balance);
    return compareText(b.sold_at, a.sold_at);
  });
  const table = document.querySelector('#credits-table');
  if (table) table.innerHTML = visible.map(item => `<tr><td><b>${item.invoice}</b></td><td>${item.customer_name || 'Walk-in Customer'}</td><td>${item.sold_at}</td><td>${lkr(item.total)}</td><td>${lkr(Number(item.payment_received) + Number(item.credit_paid))}</td><td><b class="low">${lkr(item.credit_balance)}</b></td><td><button class="primary" onclick="openCreditPayment('${item.invoice}',${item.credit_balance})">Collect</button></td></tr>`).join('') || '<tr><td colspan="7" class="muted">No credit payments match this search.</td></tr>';
  showManagementCount('credits', visible.length, credits.length, 'credit bills');
}
function returnsView() {
  const visible = managementSearch(returns, 'returns', ['return_no', 'invoice', 'customer_name', 'processed_by', 'returned_at']);
  const table = document.querySelector('#returns-table');
  if (table) table.innerHTML = visible.map(item => `<tr><td><b>${item.return_no}</b></td><td>${item.invoice}</td><td>${item.customer_name || 'Walk-in Customer'}</td><td>${item.processed_by}</td><td>${item.returned_at}</td><td>${item.item_count}</td><td>${lkr(item.refund_total)}</td><td class="${item.status === 'Pending' ? 'status-pending' : 'status-good'}">${item.status || 'Approved'}</td></tr>`).join('') || '<tr><td colspan="8" class="muted">No returns match this search.</td></tr>';
  showManagementCount('returns', visible.length, returns.length, 'returns');
}

// Operations controls are deliberately server-backed so closing, stock and approval
// records remain available after the desktop app is restarted.
function cashClosingsView() {
  const table = document.querySelector('#cash-closings-table');
  if (!table) return;
  table.innerHTML = cashClosings.map(item => `<tr><td>${item.closing_date}</td><td>${item.cashier_name}</td><td>${lkr(item.expected_cash)}</td><td>${lkr(item.counted_cash)}</td><td class="${Number(item.difference) === 0 ? 'status-good' : 'status-pending'}">${Number(item.difference) >= 0 ? '+' : ''}${lkr(item.difference)}</td><td>${item.closed_by}</td></tr>`).join('') || '<tr><td colspan="6" class="muted">No day-end closings have been recorded.</td></tr>';
}
function operationsView() {
  if (userRole !== 'admin') return;
  const pending = returns.filter(item => item.status === 'Pending');
  const pendingTable = document.querySelector('#pending-returns-table');
  if (pendingTable) pendingTable.innerHTML = pending.map(item => `<tr><td>${item.return_no}</td><td>${item.invoice}</td><td>${item.customer_name || 'Walk-in Customer'}</td><td>${item.processed_by}</td><td>${lkr(item.refund_total)}</td><td><button class="primary" onclick="approveReturn(${item.id}, '${item.return_no}')">Approve & Restore Stock</button></td></tr>`).join('') || '<tr><td colspan="6" class="muted">No pending returns.</td></tr>';
  const stockTable = document.querySelector('#stock-movements-table');
  if (stockTable) stockTable.innerHTML = stockMovements.map(item => `<tr><td>${item.recorded_at}</td><td>${item.product_name}</td><td class="${Number(item.quantity_change) < 0 ? 'low' : 'status-good'}">${Number(item.quantity_change) > 0 ? '+' : ''}${item.quantity_change}</td><td>${item.stock_after}</td><td>${item.movement_type}</td><td>${item.recorded_by}</td><td>${item.reason || '—'}</td></tr>`).join('') || '<tr><td colspan="7" class="muted">No stock movements recorded.</td></tr>';
  const auditTable = document.querySelector('#audit-logs-table');
  if (auditTable) auditTable.innerHTML = auditLogs.map(item => `<tr><td>${item.logged_at}</td><td>${item.actor}</td><td>${item.action}</td><td>${item.entity_type} ${item.entity_id || ''}</td><td>${item.details || '—'}</td></tr>`).join('') || '<tr><td colspan="5" class="muted">No audit activity recorded yet.</td></tr>';
  const status = window.orbixSystemStatus;
  const statusView = document.querySelector('#system-status');
  if (statusView) statusView.innerHTML = status ? `<div class="stat">Database integrity<strong class="${status.integrity === 'ok' ? 'status-good' : 'low'}">${status.integrity === 'ok' ? 'OK' : status.integrity}</strong></div><div class="stat">Automatic backup<strong>${status.latest_backup || 'Creating…'}</strong></div>` : '';
}
function openStockAdjustment() {
  const form = document.querySelector('#form');
  showModal('Stock Adjustment');
  form.innerHTML = `<label>Product<select required name="product_id">${products.map(product => `<option value="${product.id}">${product.name} — ${product.stock} in stock</option>`).join('')}</select></label><label>Type<select name="movement_type"><option>Stock In</option><option>Adjustment</option><option>Damaged</option></select></label><label>Quantity change<input required name="quantity_change" type="number" step="1" placeholder="Use - for stock out"></label><label>Reason<input required name="reason" placeholder="Supplier delivery, count correction, damaged item..."></label>${modalActions('Save Stock Movement')}`;
  form.onsubmit = async event => { event.preventDefault(); try { await api('stock-movements','POST',Object.fromEntries(new FormData(form))); closeModal(); await load(); } catch (error) { alert(error.message); } };
}
async function closeCounter() {
  const date = document.querySelector('#closing-date')?.value;
  const counted = document.querySelector('#counted-cash')?.value;
  const cashier = userRole === 'admin' ? document.querySelector('#closing-cashier')?.value : loggedInName();
  if (!date || !cashier) return alert('Select a date and cashier before closing.');
  if (counted === '') return alert('Enter the counted cash amount.');
  try {
    const preview = await api(`daily-report?date=${encodeURIComponent(date)}&cashier=${encodeURIComponent(cashier)}`);
    const result = await api('cash-closings','POST',{date,cashier,counted_cash:counted,note:document.querySelector('#closing-note')?.value || ''});
    document.querySelector('#closing-preview').textContent = `Expected: ${lkr(preview.cash_total)} · Counted: ${lkr(counted)} · Difference: ${result.difference >= 0 ? '+' : ''}${lkr(result.difference)}`;
    alert('Day-end closing saved.'); await load();
  } catch (error) { alert(error.message); }
}
async function approveReturn(id, returnNo) {
  if (!confirm(`Approve ${returnNo}? Stock will be restored and the refund will enter reports.`)) return;
  try { await api(`returns/${id}/approve`, 'POST', {}); await load(); } catch (error) { alert(error.message); }
}
async function voidInvoice(invoice) {
  const reason = prompt(`Reason for voiding ${invoice}:`);
  if (!reason) return;
  try { await api(`sales/${encodeURIComponent(invoice)}/void`, 'POST', { reason }); alert('Invoice voided. Product stock was restored.'); await load(); } catch (error) { alert(error.message); }
}
function openRestoreBackup() {
  const form = document.querySelector('#form');
  showModal('Restore Database Backup');
  form.innerHTML = `<p class="scan-note"><b>Warning:</b> Restoring replaces the current live database. Download a backup first if required.</p><label>ORBIX backup file<input required type="file" name="backup" accept=".db,application/octet-stream"></label>${modalActions('Restore Backup')}`;
  form.onsubmit = async event => { event.preventDefault(); const file=form.elements.backup.files[0]; if (!file) return; if (!confirm('Replace the current database with this backup?')) return; try { const bytes = new Uint8Array(await file.arrayBuffer()); await api('backup/restore','POST',{database:bytesToBase64(bytes)}); clearLocalSession(); closeModal(); alert('Backup restored. Sign in again.'); location.reload(); } catch (error) { alert(error.message); } };
}
