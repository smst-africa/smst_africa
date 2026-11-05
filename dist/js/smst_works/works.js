/* ==========================================================================
   SmSt Works — the app
   Every change goes through the API. The websocket keeps the shop floor on the
   same page while it is open, and the timeline moves forward every second.
   ========================================================================== */
import { scrollLeftRight } from '/static/js/common/functions.prod.js';

(function () {
  'use strict';

  var API = '/smst_works/api/';
  var root = document.querySelector('.works');
  var shopId = (root && root.dataset.shop) || '';
  var currency = (root && root.dataset.currency) || 'Ksh';
  var permissions =
    root && root.dataset.permissions
      ? root.dataset.permissions.split(',').filter(Boolean)
      : [];
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  var socket = null;
  var socketTimer = null;
  var socketTries = 0;
  var lastActionAt = 0;
  var started = false;
  var timeline = null;
  var timelineHours = 24;
  var timelineData = null;

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
          throw new Error(messageOf(data));
        }
        return data;
      });
    });
  }

  function messageOf(data) {
    if (!data) {
      return 'That did not work. Please try again.';
    }
    var message = data.detail || data.error;
    if (typeof message === 'string' && message) {
      return message;
    }
    var keys = Object.keys(data);
    if (!keys.length) {
      return 'That did not work. Please try again.';
    }
    return keys
      .map(function (key) {
        var value = data[key];
        return key + ': ' + (Array.isArray(value) ? value.join(' ') : value);
      })
      .join(' · ');
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

  function field(form, name) {
    return form ? form.querySelector('[name="' + name + '"]') : null;
  }

  function setField(form, name, value) {
    var control = field(form, name);
    if (control) {
      control.value = value === undefined || value === null ? '' : value;
    }
  }

  function escapeHtml(value) {
    return String(value === undefined || value === null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function iso(date) {
    var month = String(date.getMonth() + 1).padStart(2, '0');
    var day = String(date.getDate()).padStart(2, '0');
    return date.getFullYear() + '-' + month + '-' + day;
  }

  function formatDuration(value) {
    var seconds = Math.max(0, Math.floor(Number(value) || 0));
    if (seconds < 60) {
      return seconds + 's';
    }
    var minutes = Math.floor(seconds / 60);
    var rest = seconds % 60;
    if (minutes < 60) {
      return minutes + 'm ' + String(rest).padStart(2, '0') + 's';
    }
    var hours = Math.floor(minutes / 60);
    minutes = minutes % 60;
    return hours + 'h ' + String(minutes).padStart(2, '0') + 'm';
  }

  function formatClock(date) {
    return (
      String(date.getHours()).padStart(2, '0') +
      ':' +
      String(date.getMinutes()).padStart(2, '0')
    );
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
    var label = button.querySelector('span');
    if (label && (busyLabel || idleLabel)) {
      label.textContent = isBusy ? busyLabel : idleLabel;
    }
  }

  function showError(form, message) {
    var slot = form ? form.querySelector('.form-error') : null;
    if (!slot) {
      say(message, true);
      return;
    }
    slot.textContent = message;
    slot.hidden = false;
  }

  function clearError(form) {
    var slot = form ? form.querySelector('.form-error') : null;
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
    window.setTimeout(refreshPage, 900);
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

  function resetForm(form) {
    if (!form) {
      return;
    }
    form.reset();
    setField(form, 'id', '');
    clearError(form);
  }

  /* ------------------------------------------------------------- the rail */
  function initRail() {
    var toggle = one('[data-rail-toggle]');
    if (!root || !toggle) {
      return;
    }
    var stored = null;
    try {
      stored = window.localStorage.getItem('smst_works_rail');
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
          'smst_works_rail',
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

  /* ------------------------------------------------------------ job form */
  function addJobLine(which) {
    var template = one('[data-job-line-template]');
    var container = one('[data-job-' + which + ']');
    if (!template || !container) {
      return;
    }
    container.appendChild(template.content.cloneNode(true));
  }

  function resetJobForm() {
    var form = one('[data-job-form]');
    if (!form) {
      return;
    }
    resetForm(form);
    one('[data-job-inputs]').innerHTML = '';
    one('[data-job-outputs]').innerHTML = '';
    addJobLine('inputs');
    addJobLine('outputs');
  }

  function collectJobLines(container) {
    if (!container) {
      return [];
    }
    return all('[data-job-line]', container)
      .map(function (row) {
        var product = one('select[name="product"]', row);
        var quantity = one('input[name="quantity"]', row);
        if (!product || !quantity || !product.value || !quantity.value) {
          return null;
        }
        return { product: product.value, quantity: quantity.value };
      })
      .filter(Boolean);
  }

  function initJobForm() {
    var form = one('[data-job-form]');
    if (!form) {
      return;
    }
    all('[data-add-input]').forEach(function (button) {
      button.addEventListener('click', function () {
        addJobLine('inputs');
      });
    });
    all('[data-add-output]').forEach(function (button) {
      button.addEventListener('click', function () {
        addJobLine('outputs');
      });
    });
    form.addEventListener('click', function (event) {
      var remove = event.target.closest('[data-remove-line]');
      if (remove) {
        var row = remove.closest('[data-job-line]');
        if (row) {
          row.remove();
        }
      }
    });
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      clearError(form);
      var title = field(form, 'title');
      if (!title || !title.value.trim()) {
        showError(form, 'Give the job a name.');
        return;
      }
      var payload = {
        shop: shopId,
        title: title.value.trim(),
        description: (field(form, 'description') || {}).value || '',
        inputs: collectJobLines(one('[data-job-inputs]')),
        outputs: collectJobLines(one('[data-job-outputs]')),
      };
      var button = one('[data-job-submit]');
      busy(button, true, 'Creating…', 'Create the job');
      request('jobs/', { method: 'POST', body: payload })
        .then(function () {
          markAction();
          closeSheets();
          reloadSoon(gettext('The job is on the floor.'));
        })
        .catch(function (error) {
          showError(form, error.message);
          busy(button, false, '', 'Create the job');
        });
    });
  }

  /* ---------------------------------------------------------- stock form */
  function defaultStockKind() {
    if (permissions.indexOf('stocks.add') !== -1) {
      return 'delivery';
    }
    if (permissions.indexOf('stocks.move') !== -1) {
      return 'sale';
    }
    return 'adjustment';
  }

  function resetStockForm() {
    var form = one('[data-stock-form]');
    if (!form) {
      return;
    }
    resetForm(form);
    setField(form, 'kind', defaultStockKind());
    setField(form, 'quantity', '');
  }

  function initStockForm() {
    var form = one('[data-stock-form]');
    if (!form) {
      return;
    }
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      clearError(form);
      var payload = {
        shop: shopId,
        product: (field(form, 'product') || {}).value || '',
        kind: (field(form, 'kind') || {}).value || 'adjustment',
        quantity: (field(form, 'quantity') || {}).value || '',
        note: (field(form, 'note') || {}).value || '',
      };
      var button = one('[data-stock-submit]');
      busy(button, true, 'Saving…', 'Record the movement');
      request('shop/movement/', { method: 'POST', body: payload })
        .then(function () {
          markAction();
          closeSheets();
          reloadSoon('The movement is written.');
        })
        .catch(function (error) {
          showError(form, error.message);
          busy(button, false, '', 'Record the movement');
        });
    });
  }

  /* ------------------------------------------------------- employee form */
  function rankNote(form) {
    var select = field(form, 'rank');
    var note = one('[data-employee-rank-note]', form);
    if (!select || !note) {
      return;
    }
    var option = select.selectedOptions && select.selectedOptions[0];
    var text = option && option.dataset ? option.dataset.permissions : '';
    note.textContent = text
      ? 'Allows: ' + text + '.'
      : 'No rank chosen; they can read the floor but change nothing.';
  }

  function resetEmployeeForm() {
    var form = one('[data-employee-form]');
    if (!form) {
      return;
    }
    resetForm(form);
    setField(form, 'status', 'hired');
    setField(form, 'hired_at', iso(new Date()));
    setField(form, 'rank', '');
    setField(form, 'notes', '');
    var title = one('[data-employee-title]');
    if (title) {
      title.textContent = 'Hire someone';
    }
    var label = one('[data-employee-label]');
    if (label) {
      label.textContent = 'Hire them';
    }
    var reset = one('[data-reset-employee]');
    if (reset) {
      reset.hidden = true;
    }
    rankNote(form);
  }

  function editEmployee(id) {
    var row = one('[data-employee-row="' + id + '"]');
    var form = one('[data-employee-form]');
    if (!row || !form) {
      return;
    }
    resetEmployeeForm();
    setField(form, 'id', id);
    setField(form, 'name', row.dataset.name);
    setField(form, 'phone', row.dataset.phone);
    setField(form, 'email', row.dataset.email);
    setField(form, 'role', row.dataset.role);
    setField(form, 'rank', row.dataset.rank);
    setField(form, 'status', row.dataset.status);
    setField(form, 'hired_at', row.dataset.hired);
    setField(form, 'notes', row.dataset.notes);
    var title = one('[data-employee-title]');
    if (title) {
      title.textContent = 'Edit ' + row.dataset.name;
    }
    var label = one('[data-employee-label]');
    if (label) {
      label.textContent = 'Save the changes';
    }
    var reset = one('[data-reset-employee]');
    if (reset) {
      reset.hidden = false;
    }
    rankNote(form);
    openSheet(one('[data-employee-sheet]'));
  }

  function initEmployeeForm() {
    var form = one('[data-employee-form]');
    if (!form) {
      return;
    }
    var select = field(form, 'rank');
    if (select) {
      select.addEventListener('change', function () {
        rankNote(form);
      });
    }

    $('[data-reset-employee]')[0].addEventListener('click', resetEmployeeForm);

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      clearError(form);
      var id = (field(form, 'id') || {}).value || '';
      var payload = {
        shop: shopId,
        name: ((field(form, 'name') || {}).value || '').trim(),
        phone: (field(form, 'phone') || {}).value || '',
        email: (field(form, 'email') || {}).value || '',
        role: (field(form, 'role') || {}).value || '',
        rank: (field(form, 'rank') || {}).value || null,
        status: (field(form, 'status') || {}).value || 'hired',
        hired_at: (field(form, 'hired_at') || {}).value || null,
        notes: (field(form, 'notes') || {}).value || '',
      };
      if (!payload.name) {
        showError(form, 'Give the employee a name.');
        return;
      }
      var button = one('[data-employee-submit]');
      busy(button, true, 'Saving…', id ? 'Save the changes' : 'Hire them');
      request(id ? 'employees/' + id + '/' : 'employees/', {
        method: id ? 'PATCH' : 'POST',
        body: payload,
      })
        .then(function () {
          markAction();
          closeSheets();
          reloadSoon(
            id
              ? gettext('The team member was changed.')
              : gettext('They are on the team.')
          );
        })
        .catch(function (error) {
          showError(form, error.message);
          busy(button, false, '', id ? 'Save the changes' : 'Hire them');
        });
    });
  }

  /* ----------------------------------------------------------- rank form */
  function resetRankForm() {
    var form = one('[data-rank-form]');
    if (!form) {
      return;
    }
    resetForm(form);
    all('input[name="permissions"]', form).forEach(function (box) {
      box.checked = false;
    });
    var title = one('[data-rank-title]');
    if (title) {
      title.textContent = 'New rank';
    }
    var label = one('[data-rank-label]');
    if (label) {
      label.textContent = 'Create the rank';
    }
    var reset = one('[data-reset-rank]');
    if (reset) {
      reset.hidden = true;
    }
  }

  function editRank(id) {
    var row = one('[data-rank-row="' + id + '"]');
    var form = one('[data-rank-form]');
    if (!row || !form) {
      return;
    }
    resetRankForm();
    setField(form, 'id', id);
    setField(form, 'name', row.dataset.name);
    setField(form, 'description', row.dataset.description);
    var keys = (row.dataset.permissions || '').split(',').filter(Boolean);
    all('input[name="permissions"]', form).forEach(function (box) {
      box.checked = keys.indexOf(box.value) !== -1;
    });
    var title = one('[data-rank-title]');
    if (title) {
      title.textContent = 'Edit ' + row.dataset.name;
    }
    var label = one('[data-rank-label]');
    if (label) {
      label.textContent = 'Save the changes';
    }
    var reset = one('[data-reset-rank]');
    if (reset) {
      reset.hidden = false;
    }
    openSheet(one('[data-rank-sheet]'));
  }

  function initRankForm() {
    var form = one('[data-rank-form]');
    if (!form) {
      return;
    }
    all('[data-reset-rank]').forEach(function (button) {
      button.addEventListener('click', resetRankForm);
    });
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      clearError(form);
      var id = (field(form, 'id') || {}).value || '';
      var payload = {
        shop: shopId,
        name: ((field(form, 'name') || {}).value || '').trim(),
        description: (field(form, 'description') || {}).value || '',
        permissions: all('input[name="permissions"]:checked', form).map(
          function (box) {
            return box.value;
          }
        ),
      };
      if (!payload.name) {
        showError(form, 'Give the rank a name.');
        return;
      }
      var button = one('[data-rank-submit]');
      busy(
        button,
        true,
        'Saving…',
        id ? 'Save the changes' : 'Create the rank'
      );
      request(id ? 'ranks/' + id + '/' : 'ranks/', {
        method: id ? 'PATCH' : 'POST',
        body: payload,
      })
        .then(function () {
          markAction();
          closeSheets();
          reloadSoon(
            id
              ? gettext('The rank was changed.')
              : gettext('The rank is ready.')
          );
        })
        .catch(function (error) {
          showError(form, error.message);
          busy(button, false, '', id ? 'Save the changes' : 'Create the rank');
        });
    });
  }

  /* ------------------------------------------------------- customer form */
  function resetCustomerForm() {
    var form = one('[data-customer-form]');
    if (!form) {
      return;
    }
    resetForm(form);
    var title = one('[data-customer-title]');
    if (title) {
      title.textContent = 'Register a customer';
    }
    var label = one('[data-customer-label]');
    if (label) {
      label.textContent = 'Register them';
    }
    var reset = one('[data-reset-customer]');
    if (reset) {
      reset.hidden = true;
    }
  }

  function editCustomer(id) {
    var row = one('[data-customer-row="' + id + '"]');
    var form = one('[data-customer-form]');
    if (!row || !form) {
      return;
    }
    resetCustomerForm();
    setField(form, 'id', id);
    setField(form, 'name', row.dataset.name);
    setField(form, 'phone', row.dataset.phone);
    setField(form, 'email', row.dataset.email);
    setField(form, 'notes', row.dataset.notes);
    var title = one('[data-customer-title]');
    if (title) {
      title.textContent = 'Edit ' + row.dataset.name;
    }
    var label = one('[data-customer-label]');
    if (label) {
      label.textContent = 'Save the changes';
    }
    var reset = one('[data-reset-customer]');
    if (reset) {
      reset.hidden = false;
    }
    openSheet(one('[data-customer-sheet]'));
  }

  function initCustomerForm() {
    var form = one('[data-customer-form]');
    if (!form) {
      return;
    }
    all('[data-reset-customer]').forEach(function (button) {
      button.addEventListener('click', resetCustomerForm);
    });
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      clearError(form);
      var id = (field(form, 'id') || {}).value || '';
      var payload = {
        shop: shopId,
        name: ((field(form, 'name') || {}).value || '').trim(),
        phone: (field(form, 'phone') || {}).value || '',
        email: (field(form, 'email') || {}).value || '',
        notes: (field(form, 'notes') || {}).value || '',
      };
      if (!payload.name) {
        showError(form, 'Give the customer a name.');
        return;
      }
      var button = one('[data-customer-submit]');
      busy(button, true, 'Saving…', id ? 'Save the changes' : 'Register them');
      request(id ? 'customers/' + id + '/' : 'customers/', {
        method: id ? 'PATCH' : 'POST',
        body: payload,
      })
        .then(function () {
          markAction();
          closeSheets();
          reloadSoon(
            id
              ? gettext('The customer was changed.')
              : gettext('They are on the list.')
          );
        })
        .catch(function (error) {
          showError(form, error.message);
          busy(button, false, '', id ? 'Save the changes' : 'Register them');
        });
    });
  }

  /* ----------------------------------------------------------- points form */
  function openPoints(id, name, points) {
    var form = one('[data-points-form]');
    if (!form) {
      return;
    }
    resetForm(form);
    setField(form, 'id', id);
    setField(form, 'points', '');
    setField(form, 'reason', '');
    var title = one('[data-points-title]');
    if (title) {
      title.textContent = 'Points for ' + (name || 'the customer');
    }
    var note = one('[data-points-note]');
    if (note) {
      note.textContent =
        (name || 'The customer') +
        ' holds ' +
        (points === undefined || points === null ? '0' : points) +
        ' points. Add some, or use a negative number to redeem.';
    }
    openSheet(one('[data-points-sheet]'));
  }

  function initPointsForm() {
    var form = one('[data-points-form]');
    if (!form) {
      return;
    }
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      clearError(form);
      var id = (field(form, 'id') || {}).value || '';
      var payload = {
        shop: shopId,
        points: (field(form, 'points') || {}).value || '',
        reason: (field(form, 'reason') || {}).value || '',
      };
      var button = one('[data-points-submit]');
      busy(button, true, 'Saving…', 'Save the points');
      request('customers/' + id + '/points/', { method: 'POST', body: payload })
        .then(function () {
          markAction();
          closeSheets();
          reloadSoon('The points are saved.');
        })
        .catch(function (error) {
          showError(form, error.message);
          busy(button, false, '', 'Save the points');
        });
    });
  }

  /* --------------------------------------------------------- supplier form */
  function supplierProductSelect(form) {
    return field(form, 'products');
  }

  function resetSupplierForm() {
    var form = one('[data-supplier-form]');
    if (!form) {
      return;
    }
    resetForm(form);
    var select = supplierProductSelect(form);
    if (select) {
      all('option', select).forEach(function (option) {
        option.selected = false;
      });
    }
    var title = one('[data-supplier-title]');
    if (title) {
      title.textContent = 'Add a supplier';
    }
    var label = one('[data-supplier-label]');
    if (label) {
      label.textContent = 'Save the supplier';
    }
    var reset = one('[data-reset-supplier]');
    if (reset) {
      reset.hidden = true;
    }
  }

  function editSupplier(id) {
    var row = one('[data-supplier-row="' + id + '"]');
    var form = one('[data-supplier-form]');
    if (!row || !form) {
      return;
    }
    resetSupplierForm();
    setField(form, 'id', id);
    setField(form, 'name', row.dataset.name);
    setField(form, 'contact_name', row.dataset.contactName);
    setField(form, 'phone', row.dataset.phone);
    setField(form, 'email', row.dataset.email);
    setField(form, 'address', row.dataset.address);
    setField(form, 'notes', row.dataset.notes);
    var select = supplierProductSelect(form);
    if (select) {
      var ids = (row.dataset.products || '').split(',').filter(Boolean);
      all('option', select).forEach(function (option) {
        option.selected = ids.indexOf(option.value) !== -1;
      });
    }
    var title = one('[data-supplier-title]');
    if (title) {
      title.textContent = 'Edit ' + row.dataset.name;
    }
    var label = one('[data-supplier-label]');
    if (label) {
      label.textContent = 'Save the changes';
    }
    var reset = one('[data-reset-supplier]');
    if (reset) {
      reset.hidden = false;
    }
    openSheet(one('[data-supplier-sheet]'));
  }

  function initSupplierForm() {
    var form = one('[data-supplier-form]');
    if (!form) {
      return;
    }
    all('[data-reset-supplier]').forEach(function (button) {
      button.addEventListener('click', resetSupplierForm);
    });
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      clearError(form);
      var id = (field(form, 'id') || {}).value || '';
      var select = supplierProductSelect(form);
      var products = select
        ? all('option', select)
            .filter(function (option) {
              return option.selected;
            })
            .map(function (option) {
              return option.value;
            })
        : [];
      var payload = {
        shop: shopId,
        name: ((field(form, 'name') || {}).value || '').trim(),
        contact_name: (field(form, 'contact_name') || {}).value || '',
        phone: (field(form, 'phone') || {}).value || '',
        email: (field(form, 'email') || {}).value || '',
        address: (field(form, 'address') || {}).value || '',
        notes: (field(form, 'notes') || {}).value || '',
        products: products,
      };
      if (!payload.name) {
        showError(form, 'Give the supplier a name.');
        return;
      }
      var button = one('[data-supplier-submit]');
      busy(
        button,
        true,
        'Saving…',
        id ? 'Save the changes' : 'Save the supplier'
      );
      request(id ? 'suppliers/' + id + '/' : 'suppliers/', {
        method: id ? 'PATCH' : 'POST',
        body: payload,
      })
        .then(function () {
          markAction();
          closeSheets();
          reloadSoon(
            id
              ? gettext('The supplier was changed.')
              : gettext('The supplier is saved.')
          );
        })
        .catch(function (error) {
          showError(form, error.message);
          busy(
            button,
            false,
            '',
            id ? 'Save the changes' : 'Save the supplier'
          );
        });
    });
  }

  /* ----------------------------------------------------------- guide form */
  function resetGuideForm() {
    var form = one('[data-guide-form]');
    if (!form) {
      return;
    }
    resetForm(form);
    setField(form, 'position', '0');
    var published = field(form, 'is_published');
    if (published) {
      published.checked = true;
    }
    var title = one('[data-guide-title]');
    if (title) {
      title.textContent = 'Write a guide';
    }
    var label = one('[data-guide-label]');
    if (label) {
      label.textContent = 'Save the guide';
    }
    var reset = one('[data-reset-guide]');
    if (reset) {
      reset.hidden = true;
    }
  }

  function editGuide(id) {
    var row = one('[data-guide-row="' + id + '"]');
    var form = one('[data-guide-form]');
    if (!row || !form) {
      return;
    }
    resetGuideForm();
    setField(form, 'id', id);
    setField(form, 'title', row.dataset.title);
    setField(form, 'category', row.dataset.category);
    setField(form, 'body', row.dataset.body);
    setField(form, 'position', row.dataset.position || '0');
    var published = field(form, 'is_published');
    if (published) {
      published.checked = row.dataset.isPublished === '1';
    }
    var title = one('[data-guide-title]');
    if (title) {
      title.textContent = 'Edit ' + row.dataset.title;
    }
    var label = one('[data-guide-label]');
    if (label) {
      label.textContent = 'Save the changes';
    }
    var reset = one('[data-reset-guide]');
    if (reset) {
      reset.hidden = false;
    }
    openSheet(one('[data-guide-sheet]'));
  }

  function initGuideForm() {
    var form = one('[data-guide-form]');
    if (!form) {
      return;
    }
    all('[data-reset-guide]').forEach(function (button) {
      button.addEventListener('click', resetGuideForm);
    });
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      clearError(form);
      var id = (field(form, 'id') || {}).value || '';
      var payload = {
        shop: shopId,
        title: ((field(form, 'title') || {}).value || '').trim(),
        category: (field(form, 'category') || {}).value || '',
        body: (field(form, 'body') || {}).value || '',
        position: (field(form, 'position') || {}).value || '0',
        is_published: Boolean(
          field(form, 'is_published') && field(form, 'is_published').checked
        ),
      };
      if (!payload.title) {
        showError(form, 'Give the guide a title.');
        return;
      }
      if (!payload.body.trim()) {
        showError(form, 'Write the guide, even one line.');
        return;
      }
      var button = one('[data-guide-submit]');
      busy(button, true, 'Saving…', id ? 'Save the changes' : 'Save the guide');
      request(id ? 'guides/' + id + '/' : 'guides/', {
        method: id ? 'PATCH' : 'POST',
        body: payload,
      })
        .then(function () {
          markAction();
          closeSheets();
          reloadSoon(
            id
              ? gettext('The guide was changed.')
              : gettext('The guide is on the board.')
          );
        })
        .catch(function (error) {
          showError(form, error.message);
          busy(button, false, '', id ? 'Save the changes' : 'Save the guide');
        });
    });
  }

  /* -------------------------------------------------------- job actions */
  function actOnJob(id, action, success) {
    if (!id) {
      return;
    }
    markAction();
    var body =
      action === 'finish'
        ? { success: Boolean(success), shop: shopId }
        : { shop: shopId };
    request('jobs/' + id + '/' + action + '/', { method: 'POST', body: body })
      .then(function () {
        reloadSoon(
          action === 'start'
            ? 'The job is running.'
            : success
              ? 'The job succeeded and the stock moved.'
              : 'The job failed; the stock was left alone.'
        );
      })
      .catch(function (error) {
        say(error.message, true);
      });
  }

  function initRows() {
    all('[data-fire-employee]').forEach(function (button) {
      button.addEventListener('click', function () {
        const id = $(this).data('fire-employee');
        request(id ? 'employees/' + id + '/' : 'employees/', {
          method: 'PATCH',
          body: { id: id, status: 'left' },
        })
          .then(function () {
            markAction();
            closeSheets();
            reloadSoon(gettext('The team member was fired.'));
          })
          .catch(function (error) {
            showError($('body')[0], error.message);
            busy(this, false, '', id ? 'Save the changes' : 'Hire them');
          });
      });
    });
    all('[data-edit-employee]').forEach(function (button) {
      button.addEventListener('click', function () {
        editEmployee($(button).data('edit-employee'));
      });
    });

    all('[data-edit-rank]').forEach(function (button) {
      button.addEventListener('click', function () {
        editRank(button.dataset.editRank);
      });
    });
    all('[data-edit-customer]').forEach(function (button) {
      button.addEventListener('click', function () {
        editCustomer(button.dataset.editCustomer);
      });
    });
    all('[data-add-points]').forEach(function (button) {
      button.addEventListener('click', function () {
        openPoints(
          button.dataset.addPoints,
          button.dataset.customerName,
          button.dataset.customerPointsValue
        );
      });
    });
    all('[data-edit-supplier]').forEach(function (button) {
      button.addEventListener('click', function () {
        editSupplier(button.dataset.editSupplier);
      });
    });
    all('[data-edit-guide]').forEach(function (button) {
      button.addEventListener('click', function () {
        editGuide(button.dataset.editGuide);
      });
    });
    all('[data-job-start]').forEach(function (button) {
      button.addEventListener('click', function () {
        actOnJob(button.dataset.jobStart, 'start');
      });
    });
    all('[data-job-finish]').forEach(function (button) {
      button.addEventListener('click', function () {
        actOnJob(
          button.dataset.jobFinish,
          'finish',
          button.dataset.success === 'true'
        );
      });
    });
  }

  /* ------------------------------------------------------------- the clock */
  function tickClock() {
    var now = new Date();
    var text =
      String(now.getHours()).padStart(2, '0') +
      ':' +
      String(now.getMinutes()).padStart(2, '0') +
      ':' +
      String(now.getSeconds()).padStart(2, '0');
    all('[data-live-clock]').forEach(function (node) {
      node.textContent = text;
    });
  }

  /* ----------------------------------------------------------- timeline */
  function countLines(job) {
    var inputs = (job.inputs || []).length;
    var outputs = (job.outputs || []).length;
    return inputs + ' in · ' + outputs + ' out';
  }

  function timelineItems() {
    var jobs = (timelineData && timelineData.jobs) || [];
    var hours = timelineHours || 24;
    var now = Date.now();
    var span = hours * 3600 * 1000;
    var windowStart = now - span;
    var windowEnd = now + span * 0.03;
    var items = [];

    jobs.forEach(function (job) {
      var created = Date.parse(job.created_at || '');
      var started = Date.parse(job.started_at || '');
      var finished = Date.parse(job.finished_at || '');
      var start;
      var end;
      var cls;
      var label;
      var meta;

      if (job.status === 'pending') {
        start = created;
        end = now;
        cls = 'is-pending';
        label = 'waiting ' + formatDuration((now - start) / 1000);
        meta = 'waiting · ' + countLines(job);
      } else if (job.status === 'running') {
        start = started || created;
        end = now;
        cls = 'is-running';
        label = 'running ' + formatDuration((now - start) / 1000);
        meta = 'running · ' + countLines(job);
      } else {
        start = started || created;
        end = finished || now;
        cls = job.status === 'succeeded' ? 'is-succeeded' : 'is-failed';
        label = job.status_label || job.status;
        meta = formatDuration((end - start) / 1000) + ' · ' + countLines(job);
      }

      if (!Number.isFinite(start)) {
        return;
      }
      if (!Number.isFinite(end)) {
        end = now;
      }
      if (end < windowStart || start > windowEnd) {
        return;
      }

      var left = Math.max(
        0,
        ((start - windowStart) / (windowEnd - windowStart)) * 100
      );
      var right = Math.min(
        100,
        ((end - windowStart) / (windowEnd - windowStart)) * 100
      );
      if (right < left) {
        right = left;
      }

      items.push({
        start: start,
        title: job.title || 'Job',
        cls: cls,
        label: label,
        meta: meta,
        left: left.toFixed(3),
        width: Math.max(right - left, 0.5).toFixed(3),
        tip:
          (job.title || 'Job') +
          ' · ' +
          (job.status_label || job.status) +
          ' · ' +
          meta,
      });
    });

    items.sort(function (a, b) {
      return a.start - b.start;
    });
    return items;
  }

  function renderTimeline() {
    if (!timeline || !timelineData) {
      return;
    }
    var hours = timelineHours || 24;
    var now = Date.now();
    var span = hours * 3600 * 1000;
    var windowStart = now - span;
    var windowEnd = now + span * 0.03;

    timeline.style.setProperty(
      '--now',
      (((now - windowStart) / (windowEnd - windowStart)) * 100).toFixed(3) + '%'
    );

    var ruler = one('[data-timeline-ruler]');
    if (ruler) {
      var ticks = '';
      for (var i = 0; i <= 6; i += 1) {
        var at = windowStart + (windowEnd - windowStart) * (i / 6);
        ticks +=
          '<span class="timeline__tick" style="left:' +
          ((i / 6) * 100).toFixed(3) +
          '%">' +
          formatClock(new Date(at)) +
          '</span>';
      }
      ruler.innerHTML = ticks;
    }

    var lanes = one('[data-timeline-lanes]');
    var empty = one('[data-timeline-empty]');
    if (!lanes) {
      return;
    }

    var items = timelineItems();
    if (!items.length) {
      lanes.innerHTML = '';
      if (empty) {
        empty.hidden = false;
      }
      return;
    }
    if (empty) {
      empty.hidden = true;
    }
    lanes.innerHTML = items
      .map(function (item) {
        return (
          '<div class="timeline__lane">' +
          '<div class="timeline__label"><strong>' +
          escapeHtml(item.title) +
          '</strong><span>' +
          escapeHtml(item.meta) +
          '</span></div>' +
          '<div class="timeline__track"><span class="timeline__bar ' +
          item.cls +
          '" style="left:' +
          item.left +
          '%;width:' +
          item.width +
          '%" title="' +
          escapeHtml(item.tip) +
          '">' +
          escapeHtml(item.label) +
          '</span></div>' +
          '</div>'
        );
      })
      .join('');
  }

  function loadTimeline() {
    if (!timeline) {
      return;
    }
    request('timeline/' + withShop({ hours: timelineHours }))
      .then(function (data) {
        timelineData = data;
        renderTimeline();
        updateSummary(data.summary);
      })
      .catch(function () {
        /* the timeline keeps the last good frame */
      });
  }

  function updateSummary(summary) {
    if (!summary) {
      return;
    }
    ['employees', 'running', 'pending', 'succeeded', 'failed'].forEach(
      function (key) {
        var node = one('[data-stat="' + key + '"]');
        if (node && summary[key] !== undefined) {
          node.textContent = summary[key];
        }
      }
    );
    var points = one('[data-stat="points"]');
    if (points && summary.points !== undefined) {
      points.textContent = Number(summary.points).toLocaleString();
    }
  }

  function initTimeline() {
    timeline = one('[data-timeline]');
    if (!timeline) {
      return;
    }
    timelineHours = Number(timeline.dataset.hours) || 24;
    all('[data-timeline-range]').forEach(function (button) {
      button.addEventListener('click', function () {
        timelineHours = Number(button.dataset.timelineRange) || 24;
        all('[data-timeline-range]').forEach(function (other) {
          other.classList.toggle('is-active', other === button);
        });
        loadTimeline();
      });
    });
    loadTimeline();
  }

  /* ---------------------------------------------------------- websocket */
  function connectSocket() {
    if (!('WebSocket' in window) || !root) {
      return;
    }
    var proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    try {
      socket = new WebSocket(
        proto + '://' + window.location.host + '/ws/smst_works/shop/'
      );
    } catch (error) {
      scheduleReconnect();
      return;
    }
    socket.addEventListener('open', function () {
      socketTries = 0;
    });
    socket.addEventListener('message', function (event) {
      var message;
      try {
        message = JSON.parse(event.data);
      } catch (error) {
        return;
      }
      var name = message.event || '';
      if (name === 'connected' || !name) {
        return;
      }
      if (name.indexOf('works.job.') === 0) {
        if (timeline) {
          loadTimeline();
        }
        if (message.data && message.data.summary) {
          updateSummary(message.data.summary);
        }
      }
    });
    socket.addEventListener('close', scheduleReconnect);
    socket.addEventListener('error', function () {
      try {
        socket.close();
      } catch (error) {
        /* the close handler reconnects */
      }
    });
  }

  function scheduleReconnect() {
    window.clearTimeout(socketTimer);
    socketTries += 1;
    var delay = Math.min(15000, 1200 * socketTries);
    socketTimer = window.setTimeout(connectSocket, delay);
  }

  /* ---------------------------------------------------------------- init */
  function init() {
    root = document.querySelector('.works');
    shopId = (root && root.dataset.shop) || '';
    currency = (root && root.dataset.currency) || 'Ksh';
    permissions =
      root && root.dataset.permissions
        ? root.dataset.permissions.split(',').filter(Boolean)
        : [];
    tickClock();
    if (!started) {
      started = true;
      window.setInterval(function () {
        tickClock();
        renderTimeline();
      }, 1000);
      window.setInterval(loadTimeline, 60000);
      connectSocket();
      document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
          closeSheets();
        }
      });
    }
    initRail();
    initShopSwitch();
    initReveal();
    initJobForm();
    initStockForm();
    initEmployeeForm();
    initRankForm();
    initCustomerForm();
    initPointsForm();
    initSupplierForm();
    initGuideForm();
    initRows();
    initTimeline();

    all('[data-open-job]').forEach(function (button) {
      button.addEventListener('click', function () {
        resetJobForm();
        openSheet(one('[data-job-sheet]'));
      });
    });
    all('[data-open-stock]').forEach(function (button) {
      button.addEventListener('click', function () {
        resetStockForm();
        openSheet(one('[data-stock-sheet]'));
      });
    });
    all('[data-open-employee]').forEach(function (button) {
      button.addEventListener('click', function () {
        resetEmployeeForm();
        openSheet(one('[data-employee-sheet]'));
      });
    });
    all('[data-open-rank]').forEach(function (button) {
      button.addEventListener('click', function () {
        resetRankForm();
        openSheet(one('[data-rank-sheet]'));
      });
    });
    all('[data-open-customer]').forEach(function (button) {
      button.addEventListener('click', function () {
        resetCustomerForm();
        openSheet(one('[data-customer-sheet]'));
      });
    });
    all('[data-open-supplier]').forEach(function (button) {
      button.addEventListener('click', function () {
        resetSupplierForm();
        openSheet(one('[data-supplier-sheet]'));
      });
    });
    all('[data-open-guide]').forEach(function (button) {
      button.addEventListener('click', function () {
        resetGuideForm();
        openSheet(one('[data-guide-sheet]'));
      });
    });
    all('[data-close-sheet]').forEach(function (button) {
      button.addEventListener('click', closeSheets);
    });
  }

  document.addEventListener('htmx:afterSwap', function (event) {
    if (event.detail.target && event.detail.target.id === 'mainContent') {
      init();
    }
  });
  document.addEventListener('htmx:historyRestore', init);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  scrollLeftRight('.works__app__container', '.works__nav', 'works__nav-link');
})();
