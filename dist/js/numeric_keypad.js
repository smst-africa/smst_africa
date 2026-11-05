/* Custom numeric keypad.
   Every number field opens this panel on focus. The fields get
   inputmode="none" so phones show no native keyboard; typing, the keypad and
   the multiplier keys all drive the same input events the apps already use. */

(function () {
  'use strict';

  var SELECTOR = 'input[type="number"]';

  var panel = null;
  var labelEl = null;
  var valueEl = null;
  var dotButton = null;
  var nextButton = null;
  var target = null;
  var nextTarget = null;
  var draft = '';
  var startValue = '';
  var typed = false;
  var keyed = false;
  var decimals = 2;
  var updating = false;

  function tidy(text) {
    return text.replace(/^0+(?=\d)/, '');
  }

  function inputText(text) {
    if (text === '') {
      return '';
    }
    if (text.charAt(0) === '.') {
      text = '0' + text;
    }
    if (text.charAt(text.length - 1) === '.') {
      text = text.slice(0, -1);
    }
    return text;
  }

  function shown(text) {
    if (!text) {
      return '0';
    }
    var sign = '';
    if (text.charAt(0) === '-') {
      sign = '-';
      text = text.slice(1);
    }
    var parts = text.split('.');
    var whole = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return sign + (whole || '0') + (parts.length > 1 ? '.' + parts[1] : '');
  }

  function decimalsFor(input) {
    var step = input.getAttribute('step');
    if (step === 'any') {
      return 6;
    }
    if (!step) {
      return 0;
    }
    var point = step.indexOf('.');
    return point === -1 ? 0 : Math.min(6, step.length - point - 1);
  }

  function labelFor(input) {
    if (input.id) {
      var label = document.querySelector('label[for="' + input.id + '"]');
      if (label) {
        return label.textContent.trim();
      }
    }
    return input.getAttribute('aria-label') || input.placeholder || 'Amount';
  }

  function appFor(input) {
    var scope = input.closest('.finances, .works, .stocks');
    if (!scope) {
      return 'stocks';
    }
    if (scope.classList.contains('finances')) {
      return 'finances';
    }
    return scope.classList.contains('works') ? 'works' : 'stocks';
  }

  /* Some mobile browsers ignore inputmode="none". A readonly field never
     raises their keyboard, so lock it on touch and unlock it again on blur. */
  function lock(input) {
    if (!input || input.readOnly) {
      return;
    }
    input.setAttribute('data-keypad-readonly', '1');
    input.readOnly = true;
  }

  function unlock(input) {
    if (!input || input.getAttribute('data-keypad-readonly') !== '1') {
      return;
    }
    input.removeAttribute('data-keypad-readonly');
    input.readOnly = false;
  }

  function lockTouched(event) {
    var node = event.target;
    if (!node.closest) {
      return;
    }
    var input = node.closest(SELECTOR);
    if (!input) {
      // Tapping the label focuses its field, so lock that field too.
      var label = node.closest('label');
      input = label && label.control;
    }
    if (input && input.matches(SELECTOR)) {
      lock(input);
    }
  }

  function fieldsFor(input) {
    var root = input.form || document;
    var found = root.querySelectorAll(SELECTOR);
    var live = [];
    for (var i = 0; i < found.length; i += 1) {
      var field = found[i];
      if (
        !field.disabled &&
        (!field.readOnly ||
          field.getAttribute('data-keypad-readonly') === '1') &&
        field.getClientRects().length
      ) {
        live.push(field);
      }
    }
    return live;
  }

  function build() {
    panel = document.createElement('div');
    panel.className = 'keypad';
    panel.dataset.open = 'false';
    panel.setAttribute('aria-hidden', 'true');
    panel.setAttribute('role', 'group');
    panel.setAttribute('aria-label', 'Numeric keypad');
    panel.innerHTML =
      '<div class="keypad__head">' +
      '<span class="keypad__label"></span>' +
      '<span class="keypad__value">0</span>' +
      '</div>' +
      '<div class="keypad__keys">' +
      '<button type="button" data-key="7">7</button>' +
      '<button type="button" data-key="8">8</button>' +
      '<button type="button" data-key="9">9</button>' +
      '<button type="button" data-key="4">4</button>' +
      '<button type="button" data-key="5">5</button>' +
      '<button type="button" data-key="6">6</button>' +
      '<button type="button" data-key="1">1</button>' +
      '<button type="button" data-key="2">2</button>' +
      '<button type="button" data-key="3">3</button>' +
      '<button type="button" data-key="dot">.</button>' +
      '<button type="button" data-key="0">0</button>' +
      '<button type="button" class="keypad__key--muted" data-key="back" aria-label="Delete last digit">Del</button>' +
      '</div>' +
      '<div class="keypad__tools">' +
      '<button type="button" data-key="mul:10">×10</button>' +
      '<button type="button" data-key="mul:100">×100</button>' +
      '<button type="button" data-key="mul:1000">×1,000</button>' +
      '<button type="button" data-key="mul:10000">×10,000</button>' +
      '</div>' +
      '<div class="keypad__foot">' +
      '<button type="button" class="keypad__key--muted" data-key="clear">Clear</button>' +
      '<button type="button" data-key="00">00</button>' +
      '<button type="button" class="keypad__next" data-key="next">Next</button>' +
      '<button type="button" class="keypad__done" data-key="done">Done</button>' +
      '</div>';
    document.body.appendChild(panel);

    labelEl = panel.querySelector('.keypad__label');
    valueEl = panel.querySelector('.keypad__value');
    dotButton = panel.querySelector('[data-key="dot"]');
    nextButton = panel.querySelector('[data-key="next"]');

    // Keep the typed field focused while the keypad is tapped.
    panel.addEventListener('mousedown', function (event) {
      if (event.target.closest('button')) {
        event.preventDefault();
      }
    });
    panel.addEventListener('click', function (event) {
      var button = event.target.closest('button[data-key]');
      if (!button || button.disabled) {
        return;
      }
      press(button.dataset.key);
    });
  }

  function close() {
    panel.dataset.open = 'false';
    panel.setAttribute('aria-hidden', 'true');
  }

  function refresh() {
    if (!target) {
      return;
    }
    valueEl.textContent = shown(draft);
    dotButton.disabled = decimals === 0;
    nextButton.disabled = !nextTarget;

    var value = inputText(draft);
    if (target.value !== value) {
      updating = true;
      target.value = value;
      try {
        target.dispatchEvent(new Event('input', { bubbles: true }));
      } finally {
        updating = false;
      }
    }
  }

  function scrollerFor(element) {
    var node = element.parentElement;
    while (
      node &&
      node !== document.body &&
      node !== document.documentElement
    ) {
      var overflow = window.getComputedStyle(node).overflowY;
      if (overflow === 'auto' || overflow === 'scroll') {
        return node;
      }
      node = node.parentElement;
    }
    return document.scrollingElement || document.documentElement;
  }

  function reveal() {
    window.requestAnimationFrame(function () {
      if (!target || panel.dataset.open !== 'true') {
        return;
      }
      var rect = target.getBoundingClientRect();
      var limit = panel.getBoundingClientRect().top - 14;
      var delta = 0;
      if (rect.bottom > limit) {
        delta = rect.bottom - limit;
      } else if (rect.top < 12) {
        delta = rect.top - 12;
      }
      if (!delta) {
        return;
      }
      var scroller = scrollerFor(target);
      if (
        scroller === document.scrollingElement ||
        scroller === document.documentElement
      ) {
        window.scrollBy(0, delta);
      } else {
        scroller.scrollTop += delta;
      }
    });
  }

  function open(input) {
    if (target === input && panel.dataset.open === 'true') {
      return;
    }
    if (target && target !== input) {
      commit();
      unlock(target);
    }
    target = input;
    startValue = input.value;
    typed = false;
    keyed = false;
    draft = tidy(input.value);
    decimals = decimalsFor(input);

    var fields = fieldsFor(input);
    var at = fields.indexOf(input);
    nextTarget = at === -1 ? null : fields[at + 1] || null;

    panel.className = 'keypad keypad--' + appFor(input);
    panel.dataset.open = 'true';
    panel.setAttribute('aria-hidden', 'false');
    labelEl.textContent = labelFor(input);
    refresh();
    reveal();
  }

  function commit() {
    if (!target) {
      return;
    }
    var input = target;
    var value = inputText(draft);
    if (input.value !== value) {
      updating = true;
      input.value = value;
      try {
        input.dispatchEvent(new Event('input', { bubbles: true }));
      } finally {
        updating = false;
      }
    }
    // Only keypad edits need a change event; physical typing fires its own on blur.
    if (keyed && !typed && input.value !== startValue) {
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }

  function finish(blur) {
    if (!target) {
      close();
      return;
    }
    var input = target;
    commit();
    target = null;
    close();
    if (blur) {
      if (document.activeElement === input) {
        input.blur();
      } else if (panel.contains(document.activeElement)) {
        document.activeElement.blur();
      }
    }
    unlock(input);
  }

  function addDigit(digit) {
    if (draft === '' && digit === '0') {
      draft = '0';
      return;
    }
    if (draft.indexOf('.') !== -1) {
      if (draft.split('.')[1].length >= decimals) {
        return;
      }
    }
    draft = tidy(draft + digit);
  }

  function addDot() {
    if (decimals === 0 || draft.indexOf('.') !== -1) {
      return;
    }
    draft = draft === '' ? '0.' : draft + '.';
  }

  function shift(text, places) {
    if (!text) {
      return text;
    }
    var sign = '';
    if (text.charAt(0) === '-') {
      sign = '-';
      text = text.slice(1);
    }
    var point = text.indexOf('.');
    var whole = point === -1 ? text : text.slice(0, point);
    var fraction = point === -1 ? '' : text.slice(point + 1);
    var digits = (whole || '0') + fraction;
    var at = (whole || '0').length + places;
    while (digits.length < at) {
      digits += '0';
    }
    var result =
      at >= digits.length
        ? digits
        : digits.slice(0, at) + '.' + digits.slice(at);
    return sign + tidy(result);
  }

  function goNext() {
    if (!nextTarget) {
      return;
    }
    var next = nextTarget;
    commit();
    unlock(target);
    target = null;
    lock(next);
    next.focus();
    if (document.activeElement !== next) {
      unlock(next);
      close();
    }
  }

  function press(key) {
    if (!target) {
      return;
    }
    if (key === 'done') {
      finish(true);
      return;
    }
    if (key === 'next') {
      goNext();
      return;
    }
    keyed = true;
    if (key === 'back') {
      draft = draft.slice(0, -1);
    } else if (key === 'clear') {
      draft = '';
    } else if (key === 'dot') {
      addDot();
    } else if (key.indexOf('mul:') === 0) {
      draft = shift(draft, String(key.slice(4)).length - 1);
    } else if (key === '00') {
      addDigit('0');
      addDigit('0');
    } else if (/^[0-9]$/.test(key)) {
      addDigit(key);
    }
    refresh();
  }

  function onFocusIn(event) {
    var input = event.target;
    if (!input.matches || !input.matches(SELECTOR) || input.disabled) {
      return;
    }
    if (input.readOnly && input.getAttribute('data-keypad-readonly') !== '1') {
      return;
    }
    if (!panel) {
      build();
    }
    // Set before the device decides which keyboard to show.
    input.setAttribute('inputmode', 'none');
    open(input);
  }

  function onFocusOut(event) {
    var input = event.target;
    if (!target || input !== target) {
      return;
    }
    if (event.relatedTarget && panel.contains(event.relatedTarget)) {
      return;
    }
    unlock(input);
    window.setTimeout(function () {
      if (target !== input || document.activeElement === input) {
        return;
      }
      finish(false);
    }, 0);
  }

  function onClick(event) {
    var node = event.target;
    if (!node.closest) {
      return;
    }
    var input = node.closest(SELECTOR);
    if (!input || input.disabled) {
      return;
    }
    if (input.readOnly && input.getAttribute('data-keypad-readonly') !== '1') {
      return;
    }
    if (target === input) {
      return;
    }
    if (document.activeElement !== input) {
      input.focus();
    }
    if (target !== input) {
      open(input);
    }
  }

  function onInput(event) {
    if (!target || event.target !== target || updating) {
      return;
    }
    draft = tidy(target.value);
    if (event.isTrusted) {
      typed = true;
    }
    refresh();
  }

  function onKeyDown(event) {
    if (!target || event.key !== 'Escape') {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    finish(true);
  }

  function initAll() {
    var inputs = document.querySelectorAll(SELECTOR);
    for (var i = 0; i < inputs.length; i += 1) {
      if (!inputs[i].disabled && !inputs[i].readOnly) {
        inputs[i].setAttribute('inputmode', 'none');
      }
    }
  }

  var queued = false;
  function queue() {
    if (queued) {
      return;
    }
    queued = true;
    window.setTimeout(function () {
      queued = false;
      initAll();
    }, 0);
  }

  function watch(records) {
    if (target && !document.documentElement.contains(target)) {
      finish(false);
    }
    for (var i = 0; i < records.length; i += 1) {
      var added = records[i].addedNodes;
      for (var j = 0; j < added.length; j += 1) {
        var node = added[j];
        if (node.nodeType !== 1) {
          continue;
        }
        if (
          (node.matches && node.matches(SELECTOR)) ||
          (node.querySelector && node.querySelector(SELECTOR))
        ) {
          queue();
          return;
        }
      }
    }
  }

  function start() {
    build();
    initAll();
    document.addEventListener('focusin', onFocusIn);
    document.addEventListener('focusout', onFocusOut);
    document.addEventListener('click', onClick, true);
    document.addEventListener(
      'pointerdown',
      function (event) {
        if (event.pointerType !== 'mouse') {
          lockTouched(event);
        }
      },
      true
    );
    document.addEventListener('touchstart', lockTouched, true);
    document.addEventListener('input', onInput, true);
    document.addEventListener('keydown', onKeyDown, true);
    if ('MutationObserver' in window) {
      new MutationObserver(watch).observe(document.body, {
        childList: true,
        subtree: true,
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
