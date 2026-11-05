/* ==========================================================================
   SmSt Finances — the app
   Every change goes through the API. The websocket keeps the numbers on
   screen honest while the shop is open.
   ====================/api/entries/====================================================== */

import { scrollLeftRight } from '/static/js/common/functions.prod.js';

(function () {
  'use strict';

  var API = '/smst_finances/api/';
  var root = document.querySelector('.finances');
  var currency = (root && root.dataset.currency) || 'Ksh';
  var shopId = (root && root.dataset.shop) || '';
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  var socket = null;
  var socketTimer = null;
  var socketTries = 0;
  var lastActionAt = 0;
  var started = false;
  var flowResizeHandler = null;

  var PALETTE = [
    '#318a55',
    '#77bd8f',
    '#1e5a36',
    '#4b9f6c',
    '#b6dcc4',
    '#276c42',
    '#0e2c1b',
    '#8fcba4',
  ];

  /* ------------------------------------------------------------- helpers */
  function csrfToken() {
    var meta = document.querySelector(
      'meta[name="csrftoken"], meta[name="csrf-token"]'
    );
    return meta ? meta.content : '';
  }

  function accessToken() {
    try {
      return window.localStorage.getItem('access') || '';
    } catch (error) {
      return '';
    }
  }

  function headers(extra) {
    var base = {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    };
    var token = accessToken();
    if (token) {
      base.Authorization = 'Bearer ' + token;
    }
    if (extra) {
      Object.keys(extra).forEach(function (key) {
        base[key] = extra[key];
      });
    }
    return base;
  }

  function request(path, options) {
    options = options || {};
    var url = path.indexOf('http') === 0 ? path : API + path;
    var settings = {
      method: options.method || 'GET',
      headers: headers(options.headers),
      credentials: 'same-origin',
    };
    if (options.body !== undefined) {
      settings.body = JSON.stringify(options.body);
    }
    return fetch(url, settings).then(function (response) {
      var type = response.headers.get('content-type') || '';
      var body =
        type.indexOf('application/json') !== -1
          ? response.json()
          : response.text();
      return body.then(function (data) {
        if (!response.ok) {
          var message =
            (data && (data.detail || data.error)) ||
            'That did not work. Please try again.';
          if (typeof message !== 'string') {
            message = Object.keys(data || {})
              .map(function (key) {
                var value = data[key];
                return (
                  key + ': ' + (Array.isArray(value) ? value.join(' ') : value)
                );
              })
              .join(' · ');
          }
          throw new Error(message || 'That did not work. Please try again.');
        }
        return data;
      });
    });
  }

  function rowsOf(data) {
    if (!data) {
      return [];
    }
    if (Array.isArray(data)) {
      return data;
    }
    if (Array.isArray(data.results)) {
      return data.results;
    }
    return [];
  }

  function withShop(query) {
    var parts = [];
    if (shopId) {
      parts.push('shop=' + encodeURIComponent(shopId));
    }
    Object.keys(query || {}).forEach(function (key) {
      var value = query[key];
      if (value !== undefined && value !== null && value !== '') {
        parts.push(encodeURIComponent(key) + '=' + encodeURIComponent(value));
      }
    });
    return parts.length ? '?' + parts.join('&') : '';
  }

  function one(selector, context) {
    return (context || document).querySelector(selector);
  }

  function all(selector, context) {
    return Array.prototype.slice.call(
      (context || document).querySelectorAll(selector)
    );
  }

  function num(value) {
    var parsed = parseFloat(
      String(value === undefined ? 0 : value).replace(/,/g, '')
    );
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function money(value) {
    return (
      currency +
      ' ' +
      num(value).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })
    );
  }

  function compact(value) {
    var number = num(value);
    var abs = Math.abs(number);
    if (abs >= 1000000) {
      return (number / 1000000).toFixed(1).replace(/\.0$/, '') + 'm';
    }
    if (abs >= 1000) {
      return (number / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
    }
    return String(Math.round(number * 100) / 100);
  }

  function iso(date) {
    var month = String(date.getMonth() + 1).padStart(2, '0');
    var day = String(date.getDate()).padStart(2, '0');
    return date.getFullYear() + '-' + month + '-' + day;
  }

  function daysAgo(count) {
    var date = new Date();
    date.setHours(12, 0, 0, 0);
    date.setDate(date.getDate() - count);
    return date;
  }

  /* ---------------------------------------------------------------- toast */
  var toastTimer = null;

  function say(message, isError) {
    var toast = one('[data-toast]');
    if (!toast) {
      return;
    }
    var text = one('[data-toast-text]', toast);
    if (text) {
      text.textContent = message;
    }
    toast.classList.toggle('is-error', Boolean(isError));
    toast.hidden = false;
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () {
      toast.hidden = true;
    }, 4200);
  }

  function busy(button, isBusy, busyLabel, idleLabel) {
    if (!button) {
      return;
    }
    button.classList.toggle('is-loading', isBusy);
    button.disabled = isBusy;
    var label = button.querySelector(
      '[data-entry-label], [data-option-label], [data-account-label], [data-budget-label], [data-chart-label]'
    );
    if (label) {
      label.textContent = isBusy ? busyLabel : idleLabel;
    }
  }

  function showError(form, message) {
    var slot =
      form &&
      form.querySelector(
        '[data-entry-error], [data-option-error], [data-account-error], [data-budget-error], [data-chart-error]'
      );
    if (!slot) {
      say(message, true);
      return;
    }
    slot.textContent = message;
    slot.hidden = false;
  }

  function clearError(form) {
    var slot =
      form &&
      form.querySelector(
        '[data-entry-error], [data-option-error], [data-account-error], [data-budget-error], [data-chart-error]'
      );
    if (slot) {
      slot.textContent = '';
      slot.hidden = true;
    }
  }

  function markAction() {
    lastActionAt = Date.now();
  }

  function reloadSoon(message) {
    if (message) {
      say(message);
    }
    window.setTimeout(refreshPage, 700);
  }

  function refreshPage() {
    if (window.htmx) {
      window.htmx.ajax('GET', window.location.href, {
        target: '#mainContent',
        select: '#mainContent',
        swap: 'outerHTML',
      });
    } else {
      window.location.reload();
    }
  }

  /* ------------------------------------------------------------- the rail */
  function initRail() {
    var toggle = one('[data-rail-toggle]');
    if (!root || !toggle) {
      return;
    }
    var stored = null;
    try {
      stored = window.localStorage.getItem('smst_finances_rail');
    } catch (error) {
      stored = null;
    }

    function apply(collapsed) {
      root.classList.toggle('is-rail-collapsed', collapsed);
      root.dataset.railCollapsed = collapsed ? 'true' : 'false';
      toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      var label = toggle.querySelector('.sr-only');
      if (label) {
        label.textContent = collapsed ? 'Expand the menu' : 'Collapse the menu';
      }
    }

    apply(stored === 'collapsed');

    toggle.addEventListener('click', function () {
      var collapsed = !root.classList.contains('is-rail-collapsed');
      apply(collapsed);
      try {
        window.localStorage.setItem(
          'smst_finances_rail',
          collapsed ? 'collapsed' : 'open'
        );
      } catch (error) {
        /* the choice lasts for this page only */
      }
    });
  }

  function initShopSwitch() {
    var select = one('[data-shop-switch]');
    if (select) {
      select.addEventListener('change', function () {
        var form = select.closest('form');
        if (form) {
          form.submit();
        }
      });
    }
  }

  function initReveal() {
    if (!root) {
      return;
    }
    var items = all('[data-reveal]');
    if (reduceMotion.matches || !('IntersectionObserver' in window)) {
      items.forEach(function (item) {
        item.classList.add('is-revealed');
      });
      return;
    }
    root.classList.add('is-reveal-ready');
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-revealed');
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.08, rootMargin: '0px 0px -40px 0px' }
    );
    items.forEach(function (item, index) {
      item.style.setProperty(
        '--reveal-delay',
        Math.min(index * 40, 240) + 'ms'
      );
      observer.observe(item);
    });
  }

  /* --------------------------------------------------------------- sheets */
  function openSheet(sheet) {
    if (!sheet) {
      return;
    }
    all('.sheet').forEach(function (other) {
      if (other !== sheet) {
        other.hidden = true;
      }
    });
    sheet.hidden = false;
    document.body.classList.add('is-sheet-open');
    var first = sheet.querySelector(
      'input:not([type="hidden"]), select, textarea'
    );
    if (first) {
      window.setTimeout(function () {
        first.focus();
      }, 80);
    }
  }

  function closeSheets() {
    all('.sheet').forEach(function (sheet) {
      sheet.hidden = true;
    });
    document.body.classList.remove('is-sheet-open');
  }

  function initSheets() {
    all('[data-close-sheet]').forEach(function (button) {
      button.addEventListener('click', closeSheets);
    });
    if (!started) {
      document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
          closeSheets();
        }
      });
    }
    all('[data-open-entry]').forEach(function (button) {
      button.addEventListener('click', function () {
        resetEntryForm();
        openSheet(one('[data-entry-sheet]'));
      });
    });
    all('[data-open-option]').forEach(function (button) {
      button.addEventListener('click', function () {
        resetOptionForm();
        openSheet(one('[data-option-sheet]'));
      });
    });
    all('[data-open-account]').forEach(function (button) {
      button.addEventListener('click', function () {
        resetAccountForm();
        openSheet(one('[data-account-sheet]'));
      });
    });
    all('[data-open-budget]').forEach(function (button) {
      button.addEventListener('click', function () {
        resetBudgetForm();
        openSheet(one('[data-budget-sheet]'));
      });
    });
  }

  /* ---------------------------------------------------------------- forms */
  function field(form, name) {
    return form ? form.querySelector('[name="' + name + '"]') : null;
  }

  function setField(form, name, value) {
    var control = field(form, name);
    if (control) {
      control.value = value === undefined || value === null ? '' : value;
    }
  }

  function checkbox(form, name, value) {
    var control = field(form, name);
    if (control) {
      control.checked = Boolean(value);
    }
  }

  function resetForm(form, sheet) {
    if (!form) {
      return;
    }
    form.reset();
    setField(form, 'id', '');
    clearError(form);
    var reset = sheet
      ? sheet.querySelector(
          '[data-reset-entry], [data-reset-option], [data-reset-account], [data-reset-budget]'
        )
      : null;
    if (reset) {
      reset.hidden = true;
    }
  }

  /* ------------------------------------------------------------ entries */
  function resetEntryForm() {
    var form = one('[data-entry-form]');
    if (!form) {
      return;
    }
    resetForm(form, one('[data-entry-sheet]'));
    setField(form, 'status', 'posted');
    setField(form, 'occurred_at', iso(new Date()));
    var title = one('[data-entry-title]');
    if (title) {
      title.textContent = 'Record an entry';
    }
    var label = one('[data-entry-label]');
    if (label) {
      label.textContent = 'Record it';
    }
  }

  function fillEntryForm(row) {
    var form = one('[data-entry-form]');
    if (!form || !row) {
      return;
    }
    resetEntryForm();
    setField(form, 'id', row.dataset.entryId);
    setField(form, 'kind', row.dataset.kind);
    setField(form, 'status', row.dataset.status);
    setField(form, 'amount', row.dataset.amount);
    setField(form, 'base_amount', row.dataset.base);
    setField(form, 'rate', row.dataset.rate);
    setField(form, 'description', row.dataset.description);
    setField(form, 'note', row.dataset.note);
    setField(form, 'option', row.dataset.option);
    setField(form, 'product', row.dataset.product);
    setField(form, 'movement', row.dataset.movement);
    setField(form, 'account', row.dataset.account);
    setField(form, 'payment_account', row.dataset.paymentAccount);
    setField(form, 'occurred_at', row.dataset.date);
    var title = one('[data-entry-title]');
    if (title) {
      title.textContent = 'Edit ' + (row.dataset.reference || 'the entry');
    }
    var label = one('[data-entry-label]');
    if (label) {
      label.textContent = 'Save the changes';
    }
    var reset = one('[data-reset-entry]');
    if (reset) {
      reset.hidden = false;
    }
    openSheet(one('[data-entry-sheet]'));
  }

  function entryPayload(form) {
    var payload = {
      shop: shopId,
      kind: field(form, 'kind').value,
      status: field(form, 'status').value,
      amount: field(form, 'amount').value || 0,
      base_amount: field(form, 'base_amount').value || null,
      rate: field(form, 'rate').value || null,
      description: field(form, 'description').value,
      note: field(form, 'note').value,
      option: field(form, 'option').value || null,
      product: field(form, 'product').value || null,
      movement: field(form, 'movement').value || null,
      account: field(form, 'account').value || null,
      payment_account: field(form, 'payment_account').value || null,
      occurred_at: new Date().toISOString(),
    };
    return payload;
  }

  function initEntryForm() {
    var form = one('[data-entry-form]');
    if (!form) {
      return;
    }

    var option = field(form, 'option');
    var base = field(form, 'base_amount');
    var amount = field(form, 'amount');
    var rate = field(form, 'rate');
    var account = field(form, 'account');
    var movement = field(form, 'movement');
    var product = field(form, 'product');

    function applyOption() {
      if (!option || !option.selectedOptions.length) {
        return;
      }
      var choice = option.selectedOptions[0];
      if (!choice.value) {
        return;
      }
      var rateValue = choice.dataset.rate || '';
      var rateType = choice.dataset.rateType || 'fixed';
      if (rate && !rate.value) {
        rate.value = rateValue;
      }
      if (account && !account.value && choice.dataset.account) {
        account.value = choice.dataset.account;
      }
      if (amount && base && base.value && !num(amount.value)) {
        if (rateType === 'percentage') {
          amount.value = ((num(base.value) * num(rateValue)) / 100).toFixed(2);
        } else {
          amount.value = num(rateValue).toFixed(2);
        }
      }
    }

    if (option) {
      option.addEventListener('change', applyOption);
    }
    if (base) {
      base.addEventListener('input', function () {
        if (amount && !num(amount.value)) {
          applyOption();
        }
      });
    }
    if (movement) {
      movement.addEventListener('change', function () {
        var choice = movement.selectedOptions[0];
        if (choice && choice.dataset.product && product) {
          product.value = choice.dataset.product;
        }
      });
    }

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      clearError(form);
      var id = field(form, 'id').value;
      var button = one('[data-entry-submit]');
      busy(button, true, 'Saving…', id ? 'Save the changes' : 'Record it');
      var path = id ? 'entries/' + id + '/' : 'entries/';
      request(path, {
        method: id ? 'PATCH' : 'POST',
        body: entryPayload(form),
      })
        .then(function () {
          markAction();
          closeSheets();
          reloadSoon(
            id
              ? gettext('The entry was changed and the books reposted.')
              : gettext('The entry was written into the book.')
          );
        })
        .catch(function (error) {
          showError(form, error.message);
          busy(button, false, '', id ? 'Save the changes' : 'Record it');
        });
    });

    var reset = one('[data-reset-entry]');
    if (reset) {
      reset.addEventListener('click', resetEntryForm);
    }
  }

  function initEntryRows() {
    all('[data-edit-entry]').forEach(function (button) {
      button.addEventListener('click', function () {
        fillEntryForm(
          one('[data-entry-row="' + button.dataset.editEntry + '"]')
        );
      });
    });

    all('[data-void-entry]').forEach(function (button) {
      button.addEventListener('click', function () {
        if (
          !window.confirm(
            'Void this entry? The lines stay in the book, marked as void.'
          )
        ) {
          return;
        }
        request('entries/' + button.dataset.voidEntry + '/void/', {
          method: 'POST',
        })
          .then(function () {
            markAction();
            reloadSoon(gettext('The entry was voided. Its history is kept.'));
          })
          .catch(function (error) {
            say(error.message, true);
          });
      });
    });

    all('[data-delete-entry]').forEach(function (button) {
      button.addEventListener('click', function () {
        if (
          !window.confirm(
            'Delete this draft? A posted entry should be voided instead.'
          )
        ) {
          return;
        }
        request('entries/' + button.dataset.deleteEntry + '/', {
          method: 'DELETE',
        })
          .then(function () {
            markAction();
            reloadSoon(gettext('The draft was deleted.'));
          })
          .catch(function (error) {
            say(error.message, true);
          });
      });
    });

    all('[data-toggle-lines]').forEach(function (button) {
      button.addEventListener('click', function () {
        var row = one(
          '[data-entry-lines="' + button.dataset.toggleLines + '"]'
        );
        if (!row) {
          return;
        }
        var open = row.hidden;
        row.hidden = !open;
        button.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
    });
  }

  /* ------------------------------------------------------------ options */
  function resetOptionForm() {
    var form = one('[data-option-form]');
    if (!form) {
      return;
    }
    resetForm(form, one('[data-option-sheet]'));
    setField(form, 'kind', 'tax');
    setField(form, 'applies_to', 'all');
    setField(form, 'rate_type', 'fixed');
    setField(form, 'rate', '0');
    checkbox(form, 'is_active', true);
    checkbox(form, 'is_default', false);
    var title = one('[data-option-title]');
    if (title) {
      title.textContent = 'Add a finance option';
    }
    var label = one('[data-option-label]');
    if (label) {
      label.textContent = 'Save the option';
    }
  }

  function fillOptionForm(row) {
    var form = one('[data-option-form]');
    if (!form || !row) {
      return;
    }
    resetOptionForm();
    setField(form, 'id', row.dataset.optionId);
    setField(form, 'name', row.dataset.name);
    setField(form, 'kind', row.dataset.kind);
    setField(form, 'rate_type', row.dataset.rateType);
    setField(form, 'rate', row.dataset.rate);
    setField(form, 'applies_to', row.dataset.appliesTo);
    setField(form, 'account', row.dataset.account);
    setField(form, 'description', row.dataset.description);
    checkbox(form, 'is_active', row.dataset.active === '1');
    checkbox(form, 'is_default', row.dataset.default === '1');
    var title = one('[data-option-title]');
    if (title) {
      title.textContent = 'Edit ' + row.dataset.name;
    }
    var label = one('[data-option-label]');
    if (label) {
      label.textContent = 'Save the changes';
    }
    var reset = one('[data-reset-option]');
    if (reset) {
      reset.hidden = false;
    }
    openSheet(one('[data-option-sheet]'));
    updateRateHint(form);
  }

  function updateRateHint(form) {
    var type = field(form, 'rate_type');
    var hint = form.querySelector('[data-option-rate-hint]');
    if (type && hint) {
      hint.textContent =
        type.value === 'percentage'
          ? 'A percentage of the sale or bill.'
          : 'An amount in ' + currency + '.';
    }
  }

  function initOptionForm() {
    var form = one('[data-option-form]');
    if (!form) {
      return;
    }
    var kind = field(form, 'rate_type');
    if (kind) {
      kind.addEventListener('change', function () {
        updateRateHint(form);
      });
    }
    all('[data-open-option]').forEach(function (button) {
      button.addEventListener('click', function () {
        updateRateHint(form);
      });
    });

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      clearError(form);
      var id = field(form, 'id').value;
      var button = one('[data-option-submit]');
      busy(
        button,
        true,
        'Saving…',
        id ? 'Save the changes' : 'Save the option'
      );
      request(id ? 'options/' + id + '/' : 'options/', {
        method: id ? 'PATCH' : 'POST',
        body: {
          shop: shopId,
          name: field(form, 'name').value,
          kind: field(form, 'kind').value,
          rate_type: field(form, 'rate_type').value,
          rate: field(form, 'rate').value || 0,
          applies_to: field(form, 'applies_to').value,
          account: field(form, 'account').value || null,
          description: field(form, 'description').value,
          is_active: checkboxValue(form, 'is_active'),
          is_default: checkboxValue(form, 'is_default'),
        },
      })
        .then(function () {
          markAction();
          closeSheets();
          reloadSoon(gettext('The finance option was saved.'));
        })
        .catch(function (error) {
          showError(form, error.message);
          busy(button, false, '', id ? 'Save the changes' : 'Save the option');
        });
    });

    var reset = one('[data-reset-option]');
    if (reset) {
      reset.addEventListener('click', resetOptionForm);
    }
  }

  function checkboxValue(form, name) {
    var control = field(form, name);
    return Boolean(control && control.checked);
  }

  /* ----------------------------------------------------------- accounts */
  function resetAccountForm() {
    var form = one('[data-account-form]');
    if (!form) {
      return;
    }
    resetForm(form, one('[data-account-sheet]'));
    setField(form, 'type', 'expense');
    checkbox(form, 'is_active', true);
    var code = field(form, 'code');
    if (code) {
      code.readOnly = false;
    }
    var title = one('[data-account-title]');
    if (title) {
      title.textContent = 'Add an account';
    }
    var label = one('[data-account-label]');
    if (label) {
      label.textContent = 'Save the account';
    }
  }

  function fillAccountForm(row) {
    var form = one('[data-account-form]');
    if (!form || !row) {
      return;
    }
    resetAccountForm();
    setField(form, 'id', row.dataset.accountId);
    setField(form, 'code', row.dataset.code);
    setField(form, 'name', row.dataset.name);
    setField(form, 'type', row.dataset.type);
    setField(form, 'description', row.dataset.description);
    checkbox(form, 'is_active', row.dataset.active === '1');
    var code = field(form, 'code');
    if (code) {
      code.readOnly = row.dataset.system === '1';
    }
    var title = one('[data-account-title]');
    if (title) {
      title.textContent = 'Edit ' + row.dataset.name;
    }
    var label = one('[data-account-label]');
    if (label) {
      label.textContent = 'Save the changes';
    }
    var reset = one('[data-reset-account]');
    if (reset) {
      reset.hidden = false;
    }
    openSheet(one('[data-account-sheet]'));
  }

  function initAccountForm() {
    var form = one('[data-account-form]');
    if (!form) {
      return;
    }
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      clearError(form);
      var id = field(form, 'id').value;
      var button = one('[data-account-submit]');
      busy(
        button,
        true,
        'Saving…',
        id ? 'Save the changes' : 'Save the account'
      );
      request(id ? 'accounts/' + id + '/' : 'accounts/', {
        method: id ? 'PATCH' : 'POST',
        body: {
          shop: shopId,
          code: field(form, 'code').value,
          name: field(form, 'name').value,
          type: field(form, 'type').value,
          description: field(form, 'description').value,
          is_active: checkboxValue(form, 'is_active'),
        },
      })
        .then(function () {
          markAction();
          closeSheets();
          reloadSoon(gettext('The chart of accounts was saved.'));
        })
        .catch(function (error) {
          showError(form, error.message);
          busy(button, false, '', id ? 'Save the changes' : 'Save the account');
        });
    });

    var reset = one('[data-reset-account]');
    if (reset) {
      reset.addEventListener('click', resetAccountForm);
    }
  }

  function initAccountRows() {
    all('[data-edit-account]').forEach(function (button) {
      button.addEventListener('click', function () {
        fillAccountForm(
          one('[data-account-row="' + button.dataset.editAccount + '"]')
        );
      });
    });
    all('[data-delete-account]').forEach(function (button) {
      button.addEventListener('click', function () {
        if (
          !window.confirm(
            'Delete this account? Accounts with entries cannot be deleted.'
          )
        ) {
          return;
        }
        request('accounts/' + button.dataset.deleteAccount + '/', {
          method: 'DELETE',
        })
          .then(function () {
            markAction();
            reloadSoon(gettext('The account was deleted.'));
          })
          .catch(function (error) {
            say(error.message, true);
          });
      });
    });
  }

  /* ------------------------------------------------------------ budgets */
  function resetBudgetForm() {
    var form = one('[data-budget-form]');
    if (!form) {
      return;
    }
    resetForm(form, one('[data-budget-sheet]'));
    setField(form, 'period', 'monthly');
    setField(form, 'starts_on', iso(new Date()));
    setField(form, 'ends_on', '');
    var title = one('[data-budget-title]');
    if (title) {
      title.textContent = 'Set a budget';
    }
    var label = one('[data-budget-label]');
    if (label) {
      label.textContent = 'Save the budget';
    }
  }

  function fillBudgetForm(card) {
    var form = one('[data-budget-form]');
    if (!form || !card) {
      return;
    }
    resetBudgetForm();
    setField(form, 'id', card.dataset.budgetId);
    setField(form, 'name', card.dataset.name);
    setField(form, 'amount', card.dataset.amount);
    setField(form, 'period', card.dataset.period);
    setField(form, 'account', card.dataset.account);
    setField(form, 'option', card.dataset.option);
    setField(form, 'starts_on', card.dataset.starts);
    setField(form, 'ends_on', card.dataset.ends);
    setField(form, 'notes', card.dataset.notes);
    var title = one('[data-budget-title]');
    if (title) {
      title.textContent = 'Edit ' + card.dataset.name;
    }
    var label = one('[data-budget-label]');
    if (label) {
      label.textContent = 'Save the changes';
    }
    var reset = one('[data-reset-budget]');
    if (reset) {
      reset.hidden = false;
    }
    openSheet(one('[data-budget-sheet]'));
  }

  function initBudgetForm() {
    var form = one('[data-budget-form]');
    if (!form) {
      return;
    }
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      clearError(form);
      var id = field(form, 'id').value;
      var button = one('[data-budget-submit]');
      busy(
        button,
        true,
        'Saving…',
        id ? 'Save the changes' : 'Save the budget'
      );
      request(id ? 'budgets/' + id + '/' : 'budgets/', {
        method: id ? 'PATCH' : 'POST',
        body: {
          shop: shopId,
          name: field(form, 'name').value,
          amount: field(form, 'amount').value || 0,
          period: field(form, 'period').value,
          account: field(form, 'account').value || null,
          option: field(form, 'option').value || null,
          starts_on: field(form, 'starts_on').value || null,
          ends_on: field(form, 'ends_on').value || null,
          notes: field(form, 'notes').value,
        },
      })
        .then(function () {
          markAction();
          closeSheets();
          reloadSoon(gettext('The budget was saved.'));
        })
        .catch(function (error) {
          showError(form, error.message);
          busy(button, false, '', id ? 'Save the changes' : 'Save the budget');
        });
    });

    var reset = one('[data-reset-budget]');
    if (reset) {
      reset.addEventListener('click', resetBudgetForm);
    }
  }

  function initBudgetRows() {
    all('[data-edit-budget]').forEach(function (button) {
      button.addEventListener('click', function () {
        fillBudgetForm(
          one('[data-budget-card="' + button.dataset.editBudget + '"]')
        );
      });
    });
    all('[data-delete-budget]').forEach(function (button) {
      button.addEventListener('click', function () {
        if (
          !window.confirm(
            'Delete this budget? The entries it measured stay in the book.'
          )
        ) {
          return;
        }
        request('budgets/' + button.dataset.deleteBudget + '/', {
          method: 'DELETE',
        })
          .then(function () {
            markAction();
            reloadSoon(gettext('The budget was deleted.'));
          })
          .catch(function (error) {
            say(error.message, true);
          });
      });
    });
  }

  /* --------------------------------------------------------------- charts */
  function svgNode(name, attrs) {
    var node = document.createElementNS('http://www.w3.org/2000/svg', name);
    Object.keys(attrs || {}).forEach(function (key) {
      node.setAttribute(key, attrs[key]);
    });
    return node;
  }

  function chartParts(canvas) {
    var host = canvas.closest('.chart');
    return {
      host: host,
      legend: host ? host.querySelector('[data-chart-legend]') : null,
      empty: host ? host.querySelector('[data-chart-empty]') : null,
    };
  }

  function ensureTooltip(host) {
    if (!host) {
      return null;
    }
    var tooltip = host.querySelector('[data-chart-tooltip]');
    if (!tooltip) {
      tooltip = document.createElement('div');
      tooltip.className = 'chart__tooltip';
      tooltip.setAttribute('data-chart-tooltip', '');
      tooltip.hidden = true;
      host.appendChild(tooltip);
    }
    return tooltip;
  }

  function showTooltip(host, x, y, html) {
    var tooltip = ensureTooltip(host);
    if (!tooltip) {
      return;
    }
    tooltip.innerHTML = html;
    tooltip.hidden = false;
    tooltip.classList.add('is-visible');
    var hostBox = host.getBoundingClientRect();
    var left = Math.min(Math.max(x - hostBox.left, 8), hostBox.width - 180);
    var top = Math.max(y - hostBox.top - 12, 8);
    tooltip.style.left = left + 'px';
    tooltip.style.top = top + 'px';
    tooltip.style.transform = 'translateY(-100%)';
  }

  function hideTooltip(host) {
    if (!host) {
      return;
    }
    var tooltip = host.querySelector('[data-chart-tooltip]');
    if (tooltip) {
      tooltip.hidden = true;
      tooltip.classList.remove('is-visible');
    }
  }

  function tooltipHtml(title, rows) {
    var html = '<p class="chart__tooltip-title">' + escapeHtml(title) + '</p>';
    rows.forEach(function (row) {
      html +=
        '<p class="chart__tooltip-row"><span>' +
        escapeHtml(row.name) +
        '</span><span>' +
        escapeHtml(row.value) +
        '</span></p>';
    });
    return html;
  }

  function escapeHtml(value) {
    return String(value === undefined || value === null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function emptyChart(canvas, isEmpty, message) {
    var parts = chartParts(canvas);
    if (parts.empty) {
      if (message) {
        parts.empty.textContent = message;
      }
      parts.empty.hidden = !isEmpty;
    }
    if (parts.legend) {
      parts.legend.innerHTML = isEmpty ? '' : parts.legend.innerHTML;
    }
    return parts;
  }

  function renderDonut(canvas, labels, values, formatter) {
    var parts = chartParts(canvas);
    canvas.innerHTML = '';
    var rows = labels
      .map(function (label, index) {
        return { label: label, value: Math.abs(num(values[index])) };
      })
      .filter(function (row) {
        return row.value > 0;
      });
    var total = rows.reduce(function (sum, row) {
      return sum + row.value;
    }, 0);
    if (!rows.length || total <= 0) {
      emptyChart(canvas, true, 'No positive figures to draw yet.');
      return;
    }
    emptyChart(canvas, false);

    var size = 230;
    var radius = 88;
    var stroke = 26;
    var center = size / 2;
    var circumference = 2 * Math.PI * radius;
    var offset = 0;

    var svg = svgNode('svg', {
      viewBox: '0 0 ' + size + ' ' + size,
      class: 'donut__svg',
      role: 'img',
      'aria-label': 'Share of the total',
    });

    rows.forEach(function (row, index) {
      var share = row.value / total;
      var circle = svgNode('circle', {
        cx: center,
        cy: center,
        r: radius,
        fill: 'none',
        stroke: PALETTE[index % PALETTE.length],
        'stroke-width': stroke,
        'stroke-dasharray': circumference * share + ' ' + circumference,
        'stroke-dashoffset': -offset,
        transform: 'rotate(-90 ' + center + ' ' + center + ')',
        'stroke-linecap': 'butt',
      });
      circle.style.transition = 'opacity 160ms ease';
      circle.addEventListener('pointerenter', function (event) {
        showTooltip(
          parts.host,
          event.clientX,
          event.clientY,
          tooltipHtml(row.label, [
            {
              name: 'Amount',
              value: formatter ? formatter(row.value) : compact(row.value),
            },
            { name: 'Share', value: (share * 100).toFixed(1) + '%' },
          ])
        );
      });
      circle.addEventListener('pointermove', function (event) {
        showTooltip(
          parts.host,
          event.clientX,
          event.clientY,
          tooltipHtml(row.label, [
            {
              name: 'Amount',
              value: formatter ? formatter(row.value) : compact(row.value),
            },
            { name: 'Share', value: (share * 100).toFixed(1) + '%' },
          ])
        );
      });
      circle.addEventListener('pointerleave', function () {
        hideTooltip(parts.host);
      });
      svg.appendChild(circle);
      offset += circumference * share;
    });

    var caption = svgNode('text', {
      x: center,
      y: center - 2,
      'text-anchor': 'middle',
      'font-family': 'Inconsolata, monospace',
      'font-size': '15',
      fill: '#0e2c1b',
      'font-weight': '600',
    });
    caption.textContent = formatter ? formatter(total) : compact(total);
    svg.appendChild(caption);

    var sub = svgNode('text', {
      x: center,
      y: center + 16,
      'text-anchor': 'middle',
      'font-family': 'Figtree, sans-serif',
      'font-size': '9',
      fill: '#948674',
      'letter-spacing': '1.4',
    });
    sub.textContent = 'TOTAL';
    svg.appendChild(sub);

    canvas.appendChild(svg);

    if (parts.legend) {
      parts.legend.innerHTML = rows
        .map(function (row, index) {
          return (
            '<span class="legend-btn"><span class="legend-btn__swatch" style="background:' +
            PALETTE[index % PALETTE.length] +
            '"></span>' +
            escapeHtml(row.label) +
            '</span>'
          );
        })
        .join('');
    }
  }

  function renderSeries(canvas, labels, series, type, options) {
    options = options || {};
    var parts = chartParts(canvas);
    canvas.innerHTML = '';
    hideTooltip(parts.host);

    var cleaned = [];
    labels.forEach(function (label, index) {
      var entry = { label: label, values: [] };
      var found = false;
      series.forEach(function (line) {
        var value = num(line.values[index]);
        entry.values.push(value);
        if (value !== 0) {
          found = true;
        }
      });
      if (found) {
        cleaned.push(entry);
      }
    });

    if (!cleaned.length) {
      emptyChart(canvas, true, options.empty || 'No data in this period yet.');
      if (parts.legend) {
        parts.legend.innerHTML = '';
      }
      return;
    }
    emptyChart(canvas, false);

    var allValues = [];
    cleaned.forEach(function (row) {
      row.values.forEach(function (value) {
        allValues.push(value);
      });
    });
    var max = Math.max.apply(null, allValues.concat([0]));
    var min = Math.min.apply(null, allValues.concat([0]));
    if (max === min) {
      max = max + 1;
    }
    var span = max - min;

    var width = Math.max(canvas.clientWidth || 680, 340);
    var height = 270;
    var pad = { top: 18, right: 14, bottom: 42, left: 58 };
    var plotW = width - pad.left - pad.right;
    var plotH = height - pad.top - pad.bottom;

    function xAt(index) {
      if (cleaned.length === 1) {
        return pad.left + plotW / 2;
      }
      return pad.left + (plotW * index) / (cleaned.length - 1);
    }

    function yAt(value) {
      return pad.top + plotH - ((value - min) / span) * plotH;
    }

    var svg = svgNode('svg', {
      viewBox: '0 0 ' + width + ' ' + height,
      role: 'img',
      'aria-label': options.title || 'Finance graph',
      preserveAspectRatio: 'none',
    });
    svg.style.width = '100%';
    svg.style.height = 'auto';

    var defs = svgNode('defs', {});
    var gradient = svgNode('linearGradient', {
      id: 'finances-area-' + Math.random().toString(36).slice(2),
      x1: '0',
      y1: '0',
      x2: '0',
      y2: '1',
    });
    gradient.appendChild(
      svgNode('stop', {
        offset: '0%',
        'stop-color': PALETTE[0],
        'stop-opacity': '0.28',
      })
    );
    gradient.appendChild(
      svgNode('stop', {
        offset: '100%',
        'stop-color': PALETTE[0],
        'stop-opacity': '0.02',
      })
    );
    defs.appendChild(gradient);
    svg.appendChild(defs);

    var gridCount = 4;
    for (var step = 0; step <= gridCount; step += 1) {
      var value = min + (span * step) / gridCount;
      var y = yAt(value);
      svg.appendChild(
        svgNode('line', {
          x1: pad.left,
          y1: y,
          x2: width - pad.right,
          y2: y,
          stroke: '#e5ddcf',
          'stroke-width': step === 0 ? 1.2 : 0.7,
          'stroke-dasharray': step === 0 ? '0' : '3 4',
        })
      );
      var tick = svgNode('text', {
        x: pad.left - 8,
        y: y + 3,
        'text-anchor': 'end',
        'font-family': 'Inconsolata, monospace',
        'font-size': '9',
        fill: '#948674',
      });
      tick.textContent = compact(value);
      svg.appendChild(tick);
    }

    if (min < 0) {
      svg.appendChild(
        svgNode('line', {
          x1: pad.left,
          y1: yAt(0),
          x2: width - pad.right,
          y2: yAt(0),
          stroke: '#b3a795',
          'stroke-width': 1,
        })
      );
    }

    function drawLine(line, index) {
      var color = line.color || PALETTE[index % PALETTE.length];
      var points = cleaned.map(function (row, pointIndex) {
        return xAt(pointIndex) + ',' + yAt(row.values[index]);
      });

      if (type === 'area' && series.length === 1) {
        var area =
          'M' +
          xAt(0) +
          ',' +
          yAt(min) +
          ' L' +
          points.join(' L') +
          ' L' +
          xAt(cleaned.length - 1) +
          ',' +
          yAt(min) +
          ' Z';
        svg.appendChild(
          svgNode('path', {
            d: area,
            fill: 'url(#' + gradient.getAttribute('id') + ')',
            stroke: 'none',
          })
        );
      }

      svg.appendChild(
        svgNode('polyline', {
          points: points.join(' '),
          fill: 'none',
          stroke: color,
          'stroke-width': 2.3,
          'stroke-linejoin': 'round',
          'stroke-linecap': 'round',
        })
      );

      cleaned.forEach(function (row, pointIndex) {
        var dot = svgNode('circle', {
          cx: xAt(pointIndex),
          cy: yAt(row.values[index]),
          r: 3,
          fill: '#fffdf9',
          stroke: color,
          'stroke-width': 2,
        });
        dot.addEventListener('pointerenter', function (event) {
          showTooltip(
            parts.host,
            event.clientX,
            event.clientY,
            tooltipHtml(
              row.label,
              series.map(function (item, itemIndex) {
                return {
                  name: item.name,
                  value: money(row.values[itemIndex]),
                };
              })
            )
          );
        });
        dot.addEventListener('pointerleave', function () {
          hideTooltip(parts.host);
        });
        svg.appendChild(dot);
      });
    }

    function drawBars() {
      var groupWidth = plotW / Math.max(cleaned.length, 1);
      var barWidth = Math.max(4, Math.min(34, groupWidth * 0.58));
      cleaned.forEach(function (row, index) {
        var value = row.values[0];
        var base = yAt(0);
        var top = yAt(value);
        var x = pad.left + groupWidth * index + (groupWidth - barWidth) / 2;
        var bar = svgNode('rect', {
          x: x,
          y: Math.min(base, top),
          width: barWidth,
          height: Math.max(Math.abs(base - top), 1),
          rx: 2.5,
          fill: value < 0 ? '#9c3b2e' : PALETTE[0],
        });
        bar.style.transition = 'opacity 160ms ease';
        bar.addEventListener('pointerenter', function (event) {
          bar.style.opacity = '0.78';
          showTooltip(
            parts.host,
            event.clientX,
            event.clientY,
            tooltipHtml(row.label, [
              { name: series[0].name, value: money(value) },
            ])
          );
        });
        bar.addEventListener('pointerleave', function () {
          bar.style.opacity = '1';
          hideTooltip(parts.host);
        });
        svg.appendChild(bar);
      });
    }

    if (type === 'bar' || type === 'donut') {
      drawBars();
    } else {
      series.forEach(drawLine);
    }

    var every = Math.max(1, Math.ceil(cleaned.length / 8));
    cleaned.forEach(function (row, index) {
      if (index % every !== 0 && index !== cleaned.length - 1) {
        return;
      }
      var label = svgNode('text', {
        x: xAt(index),
        y: height - 15,
        'text-anchor': 'middle',
        'font-family': 'Inconsolata, monospace',
        'font-size': '8.5',
        fill: '#948674',
      });
      var text = String(row.label);
      if (text.length > 12) {
        text = text.slice(0, 11) + '…';
      }
      label.textContent = text;
      svg.appendChild(label);
    });

    canvas.appendChild(svg);

    if (parts.legend) {
      parts.legend.innerHTML =
        series.length > 1 || options.legend
          ? series
              .map(function (line, index) {
                return (
                  '<span class="legend-btn"><span class="legend-btn__swatch" style="background:' +
                  (line.color || PALETTE[index % PALETTE.length]) +
                  '"></span>' +
                  escapeHtml(line.name) +
                  '</span>'
                );
              })
              .join('')
          : '';
    }
  }

  function drawChart(canvas, data, type, title) {
    if (!canvas) {
      return;
    }
    var labels = (data && data.labels) || [];
    var values = (data && data.values) || [];
    if (type === 'donut') {
      renderDonut(canvas, labels, values, money);
    } else {
      renderSeries(
        canvas,
        labels,
        [{ name: title || 'Amount', values: values, color: PALETTE[0] }],
        type,
        { title: title, legend: false }
      );
    }
    if (type === 'donut') {
      emptyChart(canvas, !labels.length);
    }
  }

  function previewPayload(extra) {
    return Object.assign(
      {
        shop: shopId,
      },
      extra || {}
    );
  }

  function previewChart(payload) {
    return request('charts/preview/', {
      method: 'POST',
      body: previewPayload(payload),
    });
  }

  /* ------------------------------------------------------------ dashboard */
  function initDashboard() {
    var flow = one('[data-finance-chart="flow"]');
    if (!flow && flowResizeHandler) {
      window.removeEventListener('resize', flowResizeHandler);
      flowResizeHandler = null;
    }
    if (flow) {
      var flowCanvas = one('[data-chart-canvas]', flow);
      var range = 30;
      function loadFlow() {
        var end = new Date();
        end.setHours(12, 0, 0, 0);
        var start = daysAgo(range - 1);
        Promise.all([
          previewChart({
            x_source: 'time',
            y_source: 'income',
            date_from: iso(start),
            date_to: iso(end),
          }),
          previewChart({
            x_source: 'time',
            y_source: 'expense',
            date_from: iso(start),
            date_to: iso(end),
          }),
        ])
          .then(function (results) {
            var income = results[0];
            var expense = results[1];
            renderSeries(
              flowCanvas,
              income.labels || [],
              [
                {
                  name: 'Money in',
                  values: income.values || [],
                  color: PALETTE[0],
                },
                {
                  name: 'Money out',
                  values: expense.values || [],
                  color: '#9c3b2e',
                },
              ],
              'line',
              {
                title: 'Money in and out',
                empty: 'No entries in this period yet.',
                legend: true,
              }
            );
          })
          .catch(function () {
            emptyChart(
              flowCanvas,
              true,
              'The graph could not be drawn. Try again.'
            );
          });
      }
      loadFlow();
      all('[data-flow-range] .segmented__btn', flow).forEach(function (button) {
        button.addEventListener('click', function () {
          range = parseInt(button.dataset.range, 10) || 30;
          all('[data-flow-range] .segmented__btn', flow).forEach(
            function (other) {
              other.classList.toggle('is-active', other === button);
            }
          );
          loadFlow();
        });
      });
      if (flowResizeHandler) {
        window.removeEventListener('resize', flowResizeHandler);
      }
      flowResizeHandler = debounce(loadFlow, 240);
      window.addEventListener('resize', flowResizeHandler);
    }

    var expenses = one('[data-finance-chart="expenses"]');
    if (expenses) {
      var donutCanvas = one('[data-chart-canvas]', expenses);
      var from = one('#dash-from');
      var to = one('#dash-to');
      previewChart({
        x_source: 'option',
        y_source: 'expense',
        date_from: from ? from.value : '',
        date_to: to ? to.value : '',
      })
        .then(function (data) {
          renderDonut(donutCanvas, data.labels || [], data.values || [], money);
          if (!data.labels || !data.labels.length) {
            emptyChart(
              donutCanvas,
              true,
              'Nothing has been spent in this period.'
            );
          }
        })
        .catch(function () {
          emptyChart(donutCanvas, true, 'The donut could not be drawn.');
        });
    }

    var budgetWidget = one('[data-budget-widget]');
    if (budgetWidget) {
      request('budgets/' + withShop({}))
        .then(function (data) {
          var budgets = rowsOf(data).slice(0, 4);
          if (!budgets.length) {
            budgetWidget.innerHTML =
              '<p class="card__note">No budgets yet. Set one and it will be measured against the book.</p>';
            return;
          }
          budgetWidget.innerHTML = budgets
            .map(function (budget) {
              var status = budget.status || {};
              var percent = Math.min(100, Math.max(0, num(status.percent)));
              var over = num(status.percent) > 100;
              return (
                '<div class="bar-row">' +
                '<span class="bar-row__label">' +
                escapeHtml(budget.name) +
                '<span class="bar-row__note">' +
                escapeHtml(money(status.spent || 0)) +
                ' of ' +
                escapeHtml(money(budget.amount)) +
                '</span></span>' +
                '<span class="bar-row__value">' +
                escapeHtml(String(status.percent || 0)) +
                '%</span>' +
                '<span class="bar-row__track"><span class="bar-row__fill" style="--bar:' +
                percent +
                '%;' +
                (over ? 'background:#9c3b2e;' : '') +
                '"></span></span>' +
                '</div>'
              );
            })
            .join('');
        })
        .catch(function () {
          budgetWidget.innerHTML =
            '<p class="card__note">' +
            gettext('The budgets could not be read.') +
            '</p>';
        });
    }
  }

  /* --------------------------------------------------------- graph builder */
  function linesOf(value) {
    return String(value || '')
      .split(/\r?\n/)
      .map(function (line) {
        return line.trim();
      })
      .filter(function (line) {
        return line !== '';
      });
  }

  function chartFormPayload(form) {
    var xValues = linesOf(field(form, 'x_values').value);
    var yValues = linesOf(field(form, 'y_values').value);
    if (yValues.length) {
      yValues = yValues.map(function (value) {
        return num(value);
      });
    }
    return {
      shop: shopId,
      title: field(form, 'title').value,
      chart_type: field(form, 'chart_type').value,
      x_source: field(form, 'x_source').value,
      y_source: field(form, 'y_source').value,
      x_values: xValues,
      y_values: yValues,
      filters: {},
      description: field(form, 'description').value,
      date_from: field(form, 'date_from').value,
      date_to: field(form, 'date_to').value,
    };
  }

  function typedValuesError(payload) {
    var hasX = payload.x_values.length > 0;
    var hasY = payload.y_values.length > 0;
    if (hasX !== hasY) {
      return 'Fill in both the X and the Y values, or leave both empty.';
    }
    if (hasX && payload.x_values.length !== payload.y_values.length) {
      return 'The typed X and Y values must be the same length.';
    }
    return '';
  }

  function renderPreview(payload) {
    var preview = one('[data-chart-preview]');
    if (!preview) {
      return;
    }
    var canvas = one('[data-chart-canvas]', preview);
    var title = one('[data-preview-title]');
    if (title) {
      title.textContent = payload.title || 'The graph so far';
    }
    var requestPayload = {
      x_source: payload.x_source,
      y_source: payload.y_source,
      x_values: payload.x_values,
      y_values: payload.y_values,
      date_from: payload.date_from,
      date_to: payload.date_to,
    };
    previewChart(requestPayload)
      .then(function (data) {
        drawChart(canvas, data, payload.chart_type, payload.title);
      })
      .catch(function (error) {
        emptyChart(canvas, true, error.message);
      });
  }

  function initChartBuilder() {
    var form = one('[data-chart-form]');
    if (!form) {
      return;
    }
    var previewButton = one('[data-chart-preview]');
    if (previewButton) {
      previewButton.addEventListener('click', function () {
        clearError(form);
        var payload = chartFormPayload(form);
        var typedError = typedValuesError(payload);
        if (typedError) {
          showError(form, typedError);
          return;
        }
        try {
          JSON.parse(JSON.stringify(payload));
        } catch (error) {
          showError(form, 'Those values could not be read.');
          return;
        }
        renderPreview(payload);
      });
    }

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      clearError(form);
      var payload = chartFormPayload(form);
      var typedError = typedValuesError(payload);
      if (typedError) {
        showError(form, typedError);
        return;
      }
      var button = one('[data-chart-save]');
      busy(button, true, 'Saving…', 'Save the graph');
      request('charts/', { method: 'POST', body: payload })
        .then(function () {
          markAction();
          reloadSoon('The graph was saved.');
        })
        .catch(function (error) {
          showError(form, error.message);
          busy(button, false, '', 'Save the graph');
        });
    });
  }

  function initSavedCharts() {
    var cards = all('[data-saved-chart]');
    if (!cards.length) {
      return;
    }
    request('charts/' + withShop({}))
      .then(function (data) {
        var charts = rowsOf(data);
        var byId = {};
        charts.forEach(function (chart) {
          byId[String(chart.id)] = chart;
        });
        cards.forEach(function (card) {
          var chart = byId[String(card.dataset.savedChart)];
          if (!chart) {
            return;
          }
          var canvas = one('[data-chart-canvas]', card);
          previewChart({
            x_source: chart.x_source,
            y_source: chart.y_source,
            x_values: chart.x_values || [],
            y_values: chart.y_values || [],
            date_from: one('#chart-from') ? one('#chart-from').value : '',
            date_to: one('#chart-to') ? one('#chart-to').value : '',
          })
            .then(function (result) {
              canvas.innerHTML = '';
              drawChart(canvas, result, chart.chart_type, chart.title);
            })
            .catch(function () {
              emptyChart(canvas, true, 'This graph could not be drawn.');
            });
        });
      })
      .catch(function () {
        cards.forEach(function (card) {
          emptyChart(
            one('[data-chart-canvas]', card),
            true,
            'The saved graphs could not be read.'
          );
        });
      });

    all('[data-delete-chart]').forEach(function (button) {
      button.addEventListener('click', function () {
        if (
          !window.confirm(
            'Delete this graph? The entries it was drawn from stay in the book.'
          )
        ) {
          return;
        }
        request('charts/' + button.dataset.deleteChart + '/', {
          method: 'DELETE',
        })
          .then(function () {
            markAction();
            reloadSoon('The graph was deleted.');
          })
          .catch(function (error) {
            say(error.message, true);
          });
      });
    });
  }

  /* --------------------------------------------------------------- reports */
  function reportDates() {
    var range = one('[data-report-range]');
    var from = range
      ? one('[name="date_from"]', range)
      : one('#statement-from');
    var to = range ? one('[name="date_to"]', range) : one('#statement-to');
    if (!from || !to) {
      var dashFrom = one('#dash-from');
      var dashTo = one('#dash-to');
      if (dashFrom && dashTo) {
        from = dashFrom;
        to = dashTo;
      }
    }
    return {
      date_from: from ? from.value : '',
      date_to: to ? to.value : '',
    };
  }

  function stateSlot(kind) {
    return one('[data-report-state="' + kind + '"]');
  }

  function setState(kind, message, isError) {
    var slot = stateSlot(kind);
    if (!slot) {
      return;
    }
    slot.hidden = false;
    slot.textContent = message;
    slot.classList.toggle('is-error', Boolean(isError));
  }

  function pollReport(id, attempt, onReady) {
    attempt = attempt || 0;
    if (attempt > 45) {
      say(
        'The report is taking longer than expected. It will appear in the history.',
        true
      );
      return;
    }
    window.setTimeout(
      function () {
        request('reports/' + id + '/')
          .then(function (report) {
            if (report.status === 'ready' && report.download_url) {
              if (typeof onReady === 'function') {
                onReady(report);
              }
              return;
            }
            if (report.status === 'failed') {
              say(
                report.error || gettext('The report could not be built.'),
                true
              );
              return;
            }
            pollReport(id, attempt + 1, onReady);
          })
          .catch(function () {
            pollReport(id, attempt + 1, onReady);
          });
      },
      attempt === 0 ? 900 : 1600
    );
  }

  function createReport(kind, format, onReady) {
    var dates = reportDates();
    return request('reports/', {
      method: 'POST',
      body: {
        shop: shopId,
        kind: kind,
        format: format,
        date_from: dates.date_from || null,
        date_to: dates.date_to || null,
      },
    }).then(function (report) {
      if (report.status === 'ready' && report.download_url) {
        if (typeof onReady === 'function') {
          onReady(report);
        }
        return report;
      }
      pollReport(report.id, 0, onReady);
      return report;
    });
  }

  function initReports() {
    all('[data-build-report]').forEach(function (button) {
      button.addEventListener('click', function () {
        var kind = button.dataset.buildReport;
        var format = button.dataset.format;
        setState(kind, 'Building the ' + format.toUpperCase() + '…');
        button.disabled = true;
        createReport(kind, format, function (report) {
          setState(kind, 'Ready. Your download has started.');
          button.disabled = false;
          window.location.href = report.download_url;
          say(gettext('The report is ready.'));
        })
          .catch(function (error) {
            setState(kind, error.message, true);
            button.disabled = false;
          })
          .then(function () {
            button.disabled = false;
          });
      });
    });

    all('[data-statement-download]').forEach(function (button) {
      button.addEventListener('click', function () {
        var kind = button.dataset.statementKind;
        button.disabled = true;
        say(gettext('Building the PDF…'));
        createReport(kind, 'pdf', function (report) {
          button.disabled = false;
          window.location.href = report.download_url;
        })
          .catch(function (error) {
            button.disabled = false;
            say(error.message, true);
          })
          .then(function () {
            button.disabled = false;
          });
      });
    });

    var print = one('[data-print]');
    if (print) {
      print.addEventListener('click', function () {
        window.print();
      });
    }

    all('[data-report-row]').forEach(function (row) {
      var status = row.dataset.reportStatus;
      if (status === 'pending' || status === 'running') {
        pollReport(row.dataset.reportRow, 0, function () {
          refreshPage();
        });
      }
    });
  }

  /* ------------------------------------------------------------- websocket */
  function connectSocket() {
    if (!root || !shopId) {
      return;
    }
    if (!('WebSocket' in window)) {
      return;
    }
    var scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    var url = scheme + '://' + window.location.host + '/ws/smst_finances/shop/';

    function open() {
      try {
        socket = new WebSocket(url);
      } catch (error) {
        schedule();
        return;
      }

      socket.addEventListener('open', function () {
        socketTries = 0;
        window.setInterval(function () {
          if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ action: 'ping' }));
          }
        }, 25000);
      });

      socket.addEventListener('message', function (event) {
        var message;
        try {
          message = JSON.parse(event.data);
        } catch (error) {
          return;
        }
        if (
          !message ||
          message.event === 'connected' ||
          message.event === 'pong'
        ) {
          return;
        }
        if (Date.now() - lastActionAt < 2500) {
          return;
        }
        if (message.data && message.data.summary) {
          updateSummary(message.data.summary);
        }
        if (message.event.indexOf('finance.entry') === 0) {
          say(gettext('The book changed in another tab.'));
        }
      });

      socket.addEventListener('close', function () {
        schedule();
      });

      socket.addEventListener('error', function () {
        if (socket) {
          socket.close();
        }
      });
    }

    function schedule() {
      window.clearTimeout(socketTimer);
      socketTries = Math.min(socketTries + 1, 6);
      var wait = Math.min(1000 * Math.pow(1.7, socketTries), 15000);
      socketTimer = window.setTimeout(open, wait);
    }

    open();
  }

  function updateSummary(summary) {
    var map = {
      income: 'income',
      expense: 'expense',
      net: 'net',
      cash: 'cash',
      tax_due: 'tax_due',
      count: 'count',
    };
    Object.keys(map).forEach(function (key) {
      var slot = one('[data-stat="' + map[key] + '"]');
      if (slot && summary[key] !== undefined) {
        slot.textContent =
          key === 'count' ? String(summary[key]) : money(summary[key]);
      }
    });
  }

  /* ---------------------------------------------------------------- utils */
  function debounce(fn, wait) {
    var timer = null;
    return function () {
      var args = arguments;
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        fn.apply(null, args);
      }, wait);
    };
  }

  /* ------------------------------------------------------------------ boot */
  function boot() {
    root = document.querySelector('.finances');
    currency = (root && root.dataset.currency) || 'Ksh';
    shopId = (root && root.dataset.shop) || '';
    initRail();
    initShopSwitch();
    initReveal();
    initSheets();
    initEntryForm();
    initEntryRows();
    initOptionForm();
    initOptionRows();
    initAccountForm();
    initAccountRows();
    initBudgetForm();
    initBudgetRows();
    initDashboard();
    initChartBuilder();
    initSavedCharts();
    initReports();
    if (!started) {
      started = true;
      connectSocket();
      window.addEventListener('finances:changed', function () {
        markAction();
      });
    }
  }

  function initOptionRows() {
    all('[data-edit-option]').forEach(function (button) {
      button.addEventListener('click', function () {
        fillOptionForm(
          one('[data-option-row="' + button.dataset.editOption + '"]')
        );
      });
    });
    all('[data-delete-option]').forEach(function (button) {
      button.addEventListener('click', function () {
        if (
          !window.confirm(
            'Delete this finance option? Existing entries keep the rate they were saved with.'
          )
        ) {
          return;
        }
        request('options/' + button.dataset.deleteOption + '/', {
          method: 'DELETE',
        })
          .then(function () {
            markAction();
            reloadSoon('The finance option was deleted.');
          })
          .catch(function (error) {
            say(error.message, true);
          });
      });
    });
  }

  document.addEventListener('htmx:afterSwap', function (event) {
    if (event.detail.target && event.detail.target.id === 'mainContent') {
      boot();
    }
  });
  document.addEventListener('htmx:historyRestore', boot);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  scrollLeftRight(
    '.finances__app__container',
    '.finances__nav',
    '.finances__nav-link'
  );
})();
