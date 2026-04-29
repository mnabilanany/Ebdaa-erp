// إبداع ERP — Main JS (Enhanced + Dark Mode)
document.addEventListener('DOMContentLoaded', () => {

  // ── Theme Management ────────────────────────────────
  const themeToggle = document.getElementById('theme-toggle');
  const storedTheme = localStorage.getItem('ibdaa-theme') || 'light';
  document.documentElement.setAttribute('data-theme', storedTheme);
  
  if (themeToggle) {
    themeToggle.textContent = storedTheme === 'dark' ? '☀️' : '🌙';
    themeToggle.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme');
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('ibdaa-theme', next);
      themeToggle.textContent = next === 'dark' ? '☀️' : '🌙';
    });
  }

  // ── Flash Messages ────────────────────────────────
  document.querySelectorAll('.flash').forEach(el => {
    setTimeout(() => el.style.opacity = '0', 4500);
    setTimeout(() => el.remove(), 5000);
  });

  // ── Journal Entry Lines ────────────────────────────
  const jeBody = document.getElementById('je-lines-body');
  if (jeBody) {
    window.addJELine = function() {
      const postingAccounts = window.POSTING_ACCOUNTS || [];
      const idx = jeBody.children.length;
      const opts = postingAccounts.map(a =>
        `<option value="${a.id}">${a.code} - ${a.name}</option>`
      ).join('');
      const row = document.createElement('div');
      row.className = 'je-line-row';
      row.innerHTML = `
        <select name="account_id[]" required><option value="">-- اختر الحساب --</option>${opts}</select>
        <input type="text" name="line_desc[]" placeholder="وصف البند">
        <input type="number" name="debit[]"  step="0.01" min="0" value="0" oninput="updateTotals()">
        <input type="number" name="credit[]" step="0.01" min="0" value="0" oninput="updateTotals()">
        <button type="button" class="btn btn-danger btn-xs" onclick="removeJELine(this)">✕</button>
      `;
      jeBody.appendChild(row);
      updateTotals();
    };
    window.removeJELine = function(btn) {
      if (jeBody.children.length <= 2) return;
      btn.closest('.je-line-row').remove();
      updateTotals();
    };

    window.updateTotals = function() {
      let dr = 0, cr = 0;
      jeBody.querySelectorAll('input[name="debit[]"]').forEach(i => dr += parseFloat(i.value||0));
      jeBody.querySelectorAll('input[name="credit[]"]').forEach(i => cr += parseFloat(i.value||0));
      const fmt = n => n.toLocaleString('ar-EG',{minimumFractionDigits:2,maximumFractionDigits:2});
      const diff = Math.abs(dr - cr);
      const drEl   = document.getElementById('je-dr-total');
      const crEl   = document.getElementById('je-cr-total');
      const diffEl = document.getElementById('je-diff');
      if (drEl)   drEl.textContent   = fmt(dr);
      if (crEl)   crEl.textContent   = fmt(cr);
      if (diffEl) {
        diffEl.textContent = fmt(diff);
        diffEl.style.color = diff < 0.01 ? '#27AE60' : '#E74C3C';
      }
    };
  }

  // ── Delete Confirmation ──────────────────────────
  document.querySelectorAll('.confirm-delete').forEach(form => {
    form.addEventListener('submit', e => {
      if (!confirm('هل أنت متأكد من الحذف؟')) e.preventDefault();
    });
  });

  // ── Number Formatting ──────────────────────────────
  document.querySelectorAll('[data-currency]').forEach(el => {
    const n = parseFloat(el.dataset.currency);
    if (!isNaN(n)) el.textContent = n.toLocaleString('ar-EG',{minimumFractionDigits:2});
  });

  // ── Report Type Selector ──────────────────────────
  const rptBtns = document.querySelectorAll('[data-rpt]');
  rptBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const url = new URL(window.location);
      url.searchParams.set('type', btn.dataset.rpt);
      window.location = url;
    });
  });

  // ── Pay Installment Modal ──────────────────────────
  window.openPayModal = function(iid) {
    const m = document.getElementById('pay-modal');
    if (!m) return;
    document.getElementById('pay-inst-id').value = iid;
    m.classList.add('open');
  };
  window.closePayModal = function() {
    const m = document.getElementById('pay-modal');
    if (m) m.classList.remove('open');
  };

  // ── Reset Password Modal ───────────────────────────
  window.openResetModal = function(uid) {
    const m = document.getElementById('reset-modal');
    if (!m) return;
    document.getElementById('reset-uid').value = uid;
    m.classList.add('open');
  };
  window.closeResetModal = function() {
    const m = document.getElementById('reset-modal');
    if (m) m.classList.remove('open');
  };

  // ── Modal Close on Overlay ────────────────────────
  document.querySelectorAll('.modal-overlay').forEach(ov => {
    ov.addEventListener('click', e => {
      if (e.target === ov) ov.classList.remove('open');
    });
  });

  // ── Sidebar Collapse ───────────────────────────────
  const sidebarToggle = document.querySelector('.sidebar-toggle');
  if (sidebarToggle) {
    sidebarToggle.addEventListener('click', () => {
      document.getElementById('sidebar').classList.toggle('collapsed');
    });
  }

  // ── Print Button ──────────────────────────────────
  window.printPage = function() {
    window.print();
  };

  // ── Search Focus ──────────────────────────────────
  const searchInput = document.querySelector('.toolbar input[type="search"]');
  if (searchInput) {
    searchInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const form = searchInput.closest('form');
        if (form) form.submit();
      }
    });
  }
});
