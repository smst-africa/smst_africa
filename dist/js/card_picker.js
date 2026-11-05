/* Turn the app selects into visual dropdowns.
   The native select stays in the form, hidden, so every existing handler and
   payload keeps working. The trigger previews the current choice; the panel
   lists the options and closes once a single choice is made. */

(function () {
  'use strict';

  var SELECTOR = 'select.field__control';

  function clean(value) {
    return (value || '').trim();
  }

  function labelFor(select) {
    if (!select.id) {
      return '';
    }
    var label = document.querySelector('label[for="' + select.id + '"]');
    return label ? label.textContent.trim() : '';
  }

  function brandHref(select) {
    var scope =
      select.closest('.stocks, .finances, .works') ||
      document.querySelector('.stocks, .finances, .works');
    var svg = scope ? scope.querySelector('aside svg') : null;
    if (!svg) {
      return '';
    }
    var app = scope.classList.contains('finances')
      ? 'finances'
      : scope.classList.contains('works')
        ? 'works'
        : 'stocks';
    var id = 'choice-brand-' + app;
    if (svg.id !== id) {
      svg.id = id;
    }
    return '#' + id;
  }

  function describe(option) {
    var text = clean(option.textContent);
    var parts = text.split(/\s+[·—]\s+/);
    var title = clean(option.dataset.title) || parts[0] || text;
    var meta = clean(option.dataset.meta);
    if (!meta && parts.length > 1 && !clean(option.dataset.title)) {
      meta = parts.slice(1).join(' · ');
    }
    return {
      value: option.value,
      title: title,
      eyebrow: clean(option.dataset.eyebrow),
      meta: meta,
      badge: clean(option.dataset.badge),
      image: clean(option.dataset.image),
    };
  }

  function chosen(select) {
    var picked = [];
    for (var i = 0; i < select.options.length; i += 1) {
      if (select.options[i].selected) {
        picked.push(select.options[i]);
      }
    }
    return picked;
  }

  function preview(select) {
    var picked = chosen(select);
    if (picked.length) {
      var data = describe(picked[0]);
      if (select.multiple && picked.length > 1) {
        data.title = picked.length + ' chosen';
        data.meta = picked
          .map(function (option) {
            return describe(option).title;
          })
          .join(' · ');
      }
      return data;
    }
    for (var i = 0; i < select.options.length; i += 1) {
      if (!select.options[i].value) {
        return describe(select.options[i]);
      }
    }
    return {
      value: '',
      title: '',
      eyebrow: '',
      meta: '',
      badge: '',
      image: '',
    };
  }

  function logo(brand) {
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'choice__logo');
    svg.setAttribute('viewBox', '0 0 512 512');
    svg.setAttribute('aria-hidden', 'true');
    if (brand) {
      var use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
      use.setAttribute('href', brand);
      svg.appendChild(use);
    }
    return svg;
  }

  function summary(data, rich, brand) {
    var wrap = document.createElement('span');
    wrap.className = 'choice__summary';

    if (rich) {
      var media = document.createElement('span');
      media.className = 'choice__media';
      if (data.image || data.logo) {
        var img = document.createElement('img');
        img.src = data.image || data.logo;
        img.alt = '';
        img.loading = 'lazy';
        img.decoding = 'async';
        media.appendChild(img);
      } else {
        media.classList.add('choice__media--logo');
        if (brand) {
          media.appendChild(logo(brand));
        } else {
          media.classList.add('choice__media--mark');
          media.textContent = data.value
            ? (data.title.charAt(0) || '·').toUpperCase()
            : '—';
        }
      }
      wrap.appendChild(media);
    }

    var body = document.createElement('span');
    body.className = 'choice__body';
    if (data.eyebrow || data.badge) {
      var top = document.createElement('span');
      top.className = 'choice__top';
      if (data.eyebrow) {
        var eyebrow = document.createElement('span');
        eyebrow.className = 'choice__eyebrow';
        eyebrow.textContent = data.eyebrow;
        top.appendChild(eyebrow);
      }
      if (data.badge) {
        var badge = document.createElement('span');
        badge.className = 'choice__badge';
        badge.textContent = data.badge;
        top.appendChild(badge);
      }
      body.appendChild(top);
    }
    var title = document.createElement('span');
    title.className = 'choice__title';
    title.textContent = data.title;
    body.appendChild(title);
    if (data.meta) {
      var meta = document.createElement('span');
      meta.className = 'choice__meta';
      meta.textContent = data.meta;
      body.appendChild(meta);
    }
    wrap.appendChild(body);
    return wrap;
  }

  function selectionKey(select) {
    var key = select.disabled ? 'd' : '';
    for (var i = 0; i < select.options.length; i += 1) {
      if (select.options[i].selected) {
        key += select.options[i].value + ',';
      }
    }
    return key;
  }

  function render(select) {
    var choice = select.__choice;
    if (!choice) {
      return;
    }
    var key = selectionKey(select);
    if (choice.key === key) {
      return;
    }
    choice.key = key;
    choice.__trigger.disabled = select.disabled;
    var data = preview(select);
    if (choice.label) {
      choice.__trigger.setAttribute(
        'aria-label',
        choice.label + ': ' + data.title
      );
    }
    choice.__trigger.textContent = '';
    choice.__trigger.appendChild(summary(data, choice.__rich, choice.brand));

    var caret = document.createElement('span');
    caret.className = 'choice__caret';
    caret.setAttribute('aria-hidden', 'true');
    choice.__trigger.appendChild(caret);

    for (var i = 0; i < choice.__list.children.length; i += 1) {
      var row = choice.__list.children[i];
      var option = row.__option;
      row.setAttribute(
        'aria-selected',
        option && option.selected ? 'true' : 'false'
      );
    }
  }

  function close(root, restoreFocus) {
    if (root.dataset.open !== 'true') {
      return;
    }
    root.dataset.open = 'false';
    root.__trigger.setAttribute('aria-expanded', 'false');
    root.__panel.setAttribute('aria-hidden', 'true');
    if (restoreFocus) {
      root.__trigger.focus();
    }
  }

  function closeAll(except) {
    var open = document.querySelectorAll('.choice[data-open="true"]');
    for (var i = 0; i < open.length; i += 1) {
      if (open[i] !== except) {
        close(open[i], false);
      }
    }
  }

  function place(root) {
    var rect = root.__trigger.getBoundingClientRect();
    var height = root.__panel.offsetHeight;
    root.dataset.side =
      rect.bottom + height + 16 > window.innerHeight && rect.top > height
        ? 'up'
        : 'down';
  }

  function open(root) {
    closeAll(root);
    root.dataset.open = 'true';
    root.__trigger.setAttribute('aria-expanded', 'true');
    root.__panel.setAttribute('aria-hidden', 'false');
    place(root);
    var target =
      root.__search ||
      root.__list.querySelector('[aria-selected="true"]') ||
      root.__list.querySelector('.choice__option');
    if (target) {
      target.focus();
    }
  }

  function build(select) {
    if (select.__choice || !select.options.length) {
      return;
    }

    var required = select.required;
    var rich = false;
    var i;
    for (i = 0; i < select.options.length; i += 1) {
      var option = select.options[i];
      if (
        option.dataset.image ||
        option.dataset.eyebrow ||
        option.dataset.meta ||
        option.dataset.badge
      ) {
        rich = true;
        break;
      }
    }
    var label = labelFor(select);
    var brand = brandHref(select);

    var root = document.createElement('div');
    root.className = 'choice';
    root.dataset.open = 'false';
    root.dataset.side = 'down';

    var trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'choice__trigger';
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    if (label) {
      trigger.setAttribute('aria-label', label);
    }

    var panel = document.createElement('div');
    panel.className = 'choice__panel';
    panel.setAttribute('aria-hidden', 'true');

    var search = null;
    if (select.options.length > 8) {
      var searchBox = document.createElement('label');
      searchBox.className = 'choice__search';
      search = document.createElement('input');
      search.type = 'search';
      search.placeholder = 'Search…';
      search.setAttribute('aria-label', label ? 'Search ' + label : 'Search');
      searchBox.appendChild(search);
      panel.appendChild(searchBox);
    }

    var list = document.createElement('div');
    list.className = 'choice__list';
    list.setAttribute('role', 'listbox');
    if (label) {
      list.setAttribute('aria-label', label);
    }
    if (select.multiple) {
      list.setAttribute('aria-multiselectable', 'true');
    }
    if (required) {
      list.setAttribute('aria-required', 'true');
    }

    for (i = 0; i < select.options.length; i += 1) {
      var offered = select.options[i];
      if (!offered.value && required) {
        continue;
      }
      var row = document.createElement('button');
      row.type = 'button';
      row.className = 'choice__option';
      row.dataset.value = offered.value;
      row.setAttribute('role', 'option');
      row.setAttribute('aria-selected', 'false');
      row.disabled = select.disabled || offered.disabled;
      row.__option = offered;
      row.appendChild(summary(describe(offered), rich, brand));

      var tick = document.createElement('span');
      tick.className = 'choice__tick';
      tick.setAttribute('aria-hidden', 'true');
      row.appendChild(tick);
      list.appendChild(row);
    }
    panel.appendChild(list);

    if (search) {
      search.addEventListener('keydown', function (event) {
        if (event.key === 'Enter') {
          event.preventDefault();
        }
      });
      search.addEventListener('input', function () {
        var query = search.value.trim().toLowerCase();
        for (var index = 0; index < list.children.length; index += 1) {
          var item = list.children[index];
          item.hidden =
            Boolean(query) &&
            item.textContent.toLowerCase().indexOf(query) === -1;
        }
      });
    }

    list.addEventListener('click', function (event) {
      var row = event.target.closest('.choice__option');
      if (!row || row.disabled) {
        return;
      }
      var changed = false;
      if (select.multiple) {
        row.__option.selected = !row.__option.selected;
        changed = true;
      } else if (select.value !== row.dataset.value) {
        select.value = row.dataset.value;
        changed = true;
      }
      if (!changed) {
        close(root, true);
        return;
      }
      render(select);
      select.dispatchEvent(new Event('input', { bubbles: true }));
      select.dispatchEvent(new Event('change', { bubbles: true }));
      if (!select.multiple) {
        close(root, true);
      }
    });

    trigger.addEventListener('click', function (event) {
      event.preventDefault();
      if (root.dataset.open === 'true') {
        close(root, false);
      } else {
        open(root);
      }
    });

    root.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        if (root.dataset.open !== 'true') {
          return;
        }
        event.preventDefault();
        close(root, true);
        return;
      }
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') {
        return;
      }
      if (root.dataset.open !== 'true') {
        event.preventDefault();
        open(root);
        return;
      }
      var rows = [];
      for (var index = 0; index < list.children.length; index += 1) {
        if (!list.children[index].hidden && !list.children[index].disabled) {
          rows.push(list.children[index]);
        }
      }
      if (!rows.length) {
        return;
      }
      event.preventDefault();
      var at = rows.indexOf(document.activeElement);
      var next = event.key === 'ArrowDown' ? at + 1 : at - 1;
      if (at === -1) {
        next = event.key === 'ArrowDown' ? 0 : rows.length - 1;
      }
      rows[(next + rows.length) % rows.length].focus();
    });

    root.addEventListener('focusout', function (event) {
      if (event.relatedTarget && root.contains(event.relatedTarget)) {
        return;
      }
      window.setTimeout(function () {
        if (!root.contains(document.activeElement)) {
          close(root, false);
        }
      }, 0);
    });

    root.appendChild(trigger);
    root.appendChild(panel);
    select.parentNode.insertBefore(root, select);
    root.appendChild(select);

    select.tabIndex = -1;
    select.setAttribute('aria-hidden', 'true');
    if (required) {
      select.removeAttribute('required');
    }
    select.addEventListener('change', function () {
      render(select);
    });
    select.addEventListener('focus', function () {
      open(root);
    });

    root.__trigger = trigger;
    root.__panel = panel;
    root.__list = list;
    root.__search = search;
    root.__rich = rich;
    root.brand = brand;
    root.label = label;
    select.__choice = root;
    render(select);
  }

  function initAll() {
    $(SELECTOR).each(function () {
      $(this).toggleClass('choice__native', true);
      if (this.__choice) {
        render(this);
      } else {
        build(this);
      }
    });
    // for (var i = 0; i < selects.length; i += 1) {
    //   console.log(selects[i].__choice)
    //   if (selects[i].__choice) {
    //     render(selects[i]);
    //   } else {
    //     build(selects[i]);
    //   }
    // }
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

  document.addEventListener('click', queue, true);
  document.addEventListener('reset', queue, true);
  document.addEventListener('htmx:afterSwap', queue);
  document.addEventListener('htmx:historyRestore', queue);
  document.addEventListener('click', function (event) {
    if (!event.target.closest || !event.target.closest('.choice')) {
      closeAll(null);
    }
  });
  window.addEventListener('resize', function () {
    closeAll(null);
  });

  if ('MutationObserver' in window) {
    new MutationObserver(queue).observe(document.body, {
      childList: true,
      subtree: true,
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }
})();
