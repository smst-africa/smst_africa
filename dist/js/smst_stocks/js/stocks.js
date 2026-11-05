/* ==========================================================================
   SmSt Stocks — the app
   Every change goes through the API. The websocket keeps the numbers on
   screen honest while the shop is open.
   ========================================================================== */
import {
  searchTable,
  scrollLeftRight,
} from '/static/js/common/functions.prod.js';
(function () {
  'use strict';

  var started = false;
  var closeSheetNow = null;

  function boot() {
    var API = '/smst_stocks/api/';
    var root = document.querySelector('.stocks');
    var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

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
        return error ? '' : 'Error';
      }
    }

    function headers(extra) {
      let base = {
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
              (data && data.detail) || 'That did not work. Please try again.';
            if (typeof message !== 'string') {
              message = 'That did not work. Please try again.';
            }
            throw new Error(message);
          }
          return data;
        });
      });
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

    function fieldOf(form, name) {
      return form.querySelector('[name="' + name + '"]');
    }

    /* ---------------------------------------------------------------- toast */
    var toastTimer = null;

    function say(message, isError) {
      var toast = document.querySelector('[data-toast]');
      if (!toast) {
        return;
      }
      var text = toast.querySelector('[data-toast-text]');
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
        '[data-movement-label], [data-product-label], [data-order-label], ' +
          '[data-shop-label], [data-shop-create-label], [data-report-label]'
      );
      if (label) {
        label.textContent = isBusy ? busyLabel : idleLabel;
      }
    }

    function showError(form, message) {
      var slot = form.querySelector(
        '[data-movement-error], [data-product-error], [data-order-error], ' +
          '[data-shop-error], [data-shop-create-error]'
      );
      if (!slot) {
        say(message, true);
        return;
      }
      slot.textContent = message;
      slot.hidden = false;
    }

    function clearError(form) {
      var slot = form.querySelector(
        '[data-movement-error], [data-product-error], [data-order-error], ' +
          '[data-shop-error], [data-shop-create-error]'
      );
      if (slot) {
        slot.textContent = '';
        slot.hidden = true;
      }
    }

    /* --------------------------------------------------------- the rail */
    var toggle = document.querySelector('[data-rail-toggle]');
    if (root && toggle) {
      var stored = null;
      try {
        stored = window.localStorage.getItem('smst_stocks_rail');
      } catch (error) {
        stored = null;
      }

      var applyRail = function (collapsed) {
        root.classList.toggle('is-rail-collapsed', collapsed);
        root.dataset.railCollapsed = collapsed ? 'true' : 'false';
        toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        var label = toggle.querySelector('.sr-only');
        if (label) {
          label.textContent = collapsed
            ? 'Expand the menu'
            : 'Collapse the menu';
        }
      };

      applyRail(stored === 'collapsed');

      toggle.addEventListener('click', function () {
        var collapsed = !root.classList.contains('is-rail-collapsed');
        applyRail(collapsed);
        try {
          window.localStorage.setItem(
            'smst_stocks_rail',
            collapsed ? 'collapsed' : 'open'
          );
        } catch (error) {
          /* storage is not available, the choice lasts for this page only */
        }
      });
    }

    /* ---------------------------------------------------------- the sheet */
    var sheet = document.querySelector('[data-movement-sheet]');
    var lastFocused = null;

    function defaultAccountValue(select) {
      if (!select) {
        return '';
      }
      var preferred = select.querySelector('option[data-default]');
      return preferred ? preferred.value : '';
    }

    function financeMessage(finance) {
      if (!finance) {
        return '';
      }
      var label = finance.payment_account || finance.account || 'SmSt Finances';
      var sign =
        finance.kind === 'income' || finance.kind === 'profit' ? '+' : '−';
      return (
        'Movement recorded · ' + label + ' ' + sign + money(finance.amount)
      );
    }

    function moneyHint(kind) {
      if (kind === 'sale') {
        return gettext(
          'A sale is money in. It is posted to SmSt Finances through this account.'
        );
      }
      if (kind === 'delivery') {
        return 'A delivery is money out. It is paid from this account in SmSt Finances.';
      }
      if (kind === 'return') {
        return 'A customer return is money out. It is refunded from this account.';
      }
      if (kind === 'loss') {
        return 'A loss is written off stock, not cash. The cost is posted to Inventory.';
      }
      if (kind === 'opening') {
        return 'Opening stock is money out only if the shop paid for it. Choose the account that paid.';
      }
      return 'Choose the account the money moved through, or “No money movement” to keep it in stock only.';
    }

    function accountDefaultForKind(select, kind) {
      if (kind === 'opening' || kind === 'adjustment') {
        return '';
      }
      return defaultAccountValue(select);
    }

    function updateMoneyHint(form) {
      if (!form) {
        return;
      }
      var hint = form.querySelector('[data-money-hint]');
      var kindField = fieldOf(form, 'kind');
      var account = form.querySelector('[data-money-account]');
      if (!kindField) {
        return;
      }
      var kind = kindField.value;
      if (account && account.options.length <= 1) {
        if (hint) {
          hint.textContent =
            'SmSt Finances has no accounts for this shop yet, so the movement stays in stock only.';
        }
        return;
      }
      if (hint) {
        hint.textContent = moneyHint(kind);
      }
      if (!account) {
        return;
      }
      if (kind === 'loss') {
        var inventory = account.querySelector('option[data-code="1200"]');
        if (inventory) {
          account.value = inventory.value;
        }
        account.disabled = true;
      } else {
        account.disabled = false;
        account.value = accountDefaultForKind(account, kind);
      }
    }

    function openSheet(kind, productId) {
      if (!sheet) {
        return;
      }
      lastFocused = document.activeElement;
      sheet.hidden = false;
      document.body.style.overflow = 'hidden';

      var product = sheet.querySelector('[name="product"]');
      var kindField = sheet.querySelector('[name="kind"]');
      var quantity = sheet.querySelector('[name="quantity"]');
      var note = sheet.querySelector('[name="note"]');

      if (product) {
        product.value = productId || '';
      }
      if (kindField && kind) {
        kindField.value = kind;
      }
      if (quantity) {
        quantity.value = '1';
      }
      if (note) {
        note.value = '';
      }
      updateMoneyHint(sheet.querySelector('[data-movement-form]'));
      if (quantity) {
        quantity.focus();
      }
    }

    function closeSheet() {
      if (!sheet || sheet.hidden) {
        return;
      }
      sheet.hidden = true;
      document.body.style.overflow = '';
      if (lastFocused && typeof lastFocused.focus === 'function') {
        lastFocused.focus();
      }
    }

    if (sheet) {
      Array.prototype.forEach.call(
        sheet.querySelectorAll('[data-close-sheet]'),
        function (element) {
          element.addEventListener('click', closeSheet);
        }
      );

      closeSheetNow = closeSheet;

      var movementForm = sheet.querySelector('[data-movement-form]');
      if (movementForm) {
        var submit = movementForm.querySelector('[data-movement-submit]');
        var idle = submit
          ? submit.querySelector('[data-movement-label]').textContent
          : '';
        var movementKind = movementForm.querySelector('[name="kind"]');
        if (movementKind) {
          movementKind.addEventListener('change', function () {
            updateMoneyHint(movementForm);
          });
        }

        movementForm.addEventListener('submit', function (event) {
          event.preventDefault();
          clearError(movementForm);

          var product = fieldOf(movementForm, 'product').value;
          var kind = fieldOf(movementForm, 'kind').value;
          var quantity = fieldOf(movementForm, 'quantity').value;
          var note = fieldOf(movementForm, 'note').value;
          var account = fieldOf(movementForm, 'account');

          if (!product) {
            showError(movementForm, 'Choose the item that moved.');
            return;
          }
          if (quantity === '' || Number(quantity) === 0) {
            showError(movementForm, 'Enter how many items moved.');
            return;
          }

          busy(submit, true, 'Recording', idle);

          request('products/' + product + '/movement/', {
            method: 'POST',
            body: {
              kind: kind,
              quantity: quantity,
              note: note,
              account: account ? account.value : '',
            },
          })
            .then(function (result) {
              busy(submit, false, 'Recording', idle);
              closeSheet();
              say(financeMessage(result.finance) || 'Movement recorded.');
              applyProduct(result.product);
            })
            .catch(function (error) {
              busy(submit, false, 'Recording', idle);
              showError(
                movementForm,
                error.message || 'An Error Occurred. Try again.'
              );
            });
        });
      }
    }

    Array.prototype.forEach.call(
      document.querySelectorAll('[data-open-movement]'),
      function (button) {
        button.addEventListener('click', function () {
          openSheet('sale', '');
        });
      }
    );

    Array.prototype.forEach.call(
      document.querySelectorAll('[data-quick-movement]'),
      function (button) {
        button.addEventListener('click', function () {
          openSheet(button.dataset.quickMovement, button.dataset.product);
        });
      }
    );

    /* ------------------------------------------ an inline movement in a row */
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-inline-movement]'),
      function (button) {
        button.addEventListener('click', function () {
          var row = button.closest('tr');
          if (!row) {
            return;
          }

          var open = row.nextElementSibling;
          if (open && open.classList.contains('quick-row')) {
            open.remove();
            return;
          }

          var productId = button.dataset.product;
          var kind = button.dataset.inlineMovement || 'sale';
          var accountSelect = sheet
            ? sheet.querySelector('[name="account"]')
            : null;
          var accountOptions = accountSelect ? accountSelect.innerHTML : '';
          var accountDefault = defaultAccountValue(accountSelect);
          var accountField = accountOptions
            ? '<select class="field__control quick__account" name="account" ' +
              'aria-label="Money account">' +
              accountOptions +
              '</select>'
            : '';
          var quick = document.createElement('tr');
          quick.className = 'quick-row';
          quick.innerHTML =
            '<td colspan="7">' +
            '<form class="quick" data-quick-form>' +
            '<label class="sr-only" for="quick-' +
            productId +
            '">How many</label>' +
            '<input class="field__control quick__input" id="quick-' +
            productId +
            '" ' +
            'name="quantity" type="number" step="any" min="1" value="1" />' +
            '<select class="field__control" name="kind" aria-label="What happened">' +
            '<option value="sale"' +
            (kind === 'sale' ? ' selected' : '') +
            '>Sold</option>' +
            '<option value="delivery"' +
            (kind === 'delivery' ? ' selected' : '') +
            '>Delivered in</option>' +
            '<option value="return"' +
            (kind === 'return' ? ' selected' : '') +
            '>Returned</option>' +
            '<option value="loss"' +
            (kind === 'loss' ? ' selected' : '') +
            '>Lost</option>' +
            '</select>' +
            accountField +
            '<input class="field__control" name="note" type="text" maxlength="240" ' +
            'placeholder="Note (optional)" aria-label="Note" />' +
            '<button class="btn btn--primary btn--small" type="submit">Save</button>' +
            '<button class="link-button" type="button" data-cancel-quick>Cancel</button>' +
            '<span class="skeleton skeleton-line" data-quick-loading hidden></span>' +
            '</form></td>';

          row.after(quick);

          var form = quick.querySelector('[data-quick-form]');
          var quickAccount = form.querySelector('[name="account"]');
          if (quickAccount) {
            quickAccount.value = accountDefault;
          }
          var quickKind = form.querySelector('[name="kind"]');
          if (quickKind && quickAccount) {
            quickKind.addEventListener('change', function () {
              if (quickKind.value === 'loss') {
                var inventory = quickAccount.querySelector(
                  'option[data-code="1200"]'
                );
                if (inventory) {
                  quickAccount.value = inventory.value;
                }
                quickAccount.disabled = true;
              } else {
                quickAccount.disabled = false;
                quickAccount.value = accountDefault;
              }
            });
          }
          var input = form.querySelector('[name="quantity"]');
          input.focus();
          input.select();

          form.addEventListener('submit', function (event) {
            event.preventDefault();
            var loader = form.querySelector('[data-quick-loading]');
            loader.hidden = false;

            request('products/' + productId + '/movement/', {
              method: 'POST',
              body: {
                kind: form.querySelector('[name="kind"]').value,
                quantity: form.querySelector('[name="quantity"]').value,
                note: form.querySelector('[name="note"]').value,
                account: quickAccount ? quickAccount.value : '',
              },
            })
              .then(function (result) {
                quick.remove();
                say(financeMessage(result.finance) || 'Movement recorded.');
                applyProduct(result.product);
              })
              .catch(function (error) {
                loader.hidden = true;
                say(error.message, true);
              });
          });

          form
            .querySelector('[data-cancel-quick]')
            .addEventListener('click', function () {
              quick.remove();
            });
        });
      }
    );

    /* --------------------------------------------------------- product form */
    var productForm = document.querySelector('[data-product-form]');

    function attributePairs(form) {
      var pairs = {};
      form.querySelectorAll('.attribute-row').forEach(function (row) {
        var key = row.querySelector('[name="attribute_key"]').value.trim();
        var value = row.querySelector('[name="attribute_value"]').value.trim();
        if (key) {
          pairs[key] = value;
        }
      });
      return pairs;
    }

    if (productForm) {
      var rows = productForm.querySelector('[data-attribute-rows]');

      var addRow = function (key, value) {
        if (!rows) {
          return;
        }
        var row = document.createElement('div');
        row.className = 'attribute-row';
        row.innerHTML =
          '<input class="field__control" type="text" name="attribute_key" placeholder="Weight" aria-label="Detail name" />' +
          '<input class="field__control" type="text" name="attribute_value" placeholder="500g" aria-label="Detail value" />' +
          '<button class="icon-button" type="button" data-remove-attribute aria-label="Remove this detail">' +
          '<svg aria-hidden="true" viewBox="0 0 24 24"><use href="#i-close"></use></svg>' +
          '</button>';
        row.querySelector('[name="attribute_key"]').value = key || '';
        row.querySelector('[name="attribute_value"]').value = value || '';
        rows.appendChild(row);
      };

      Array.prototype.forEach.call(
        productForm.querySelectorAll('[data-add-attribute]'),
        function (button) {
          button.addEventListener('click', function () {
            const $attributeData = $('.attribute-row');
            const attributeLength = $attributeData.length;

            if (attributeLength <= 10) {
              let hasValue = false;

              $attributeData.find('input').each(function () {
                if ($(this).val().trim().length) {
                  hasValue = true;
                  return false; // Stop the loop
                }
              });

              if (attributeLength == 0) {
                hasValue = true;
              }

              if (hasValue) {
                addRow('', '');
              }
            } else {
            }
          });
        }
      );

      productForm.addEventListener('click', function (event) {
        var remove = event.target.closest('[data-remove-attribute]');
        if (remove) {
          remove.closest('.attribute-row').remove();
        }
      });

      var buying = productForm.querySelector('[name="buying_price"]');
      var selling = productForm.querySelector('[name="selling_price"]');
      var marginNote = productForm.querySelector('[data-margin-note]');

      var marginText = function () {
        $('.price-input').each(function () {
          const value = $(this).val().trim().replace(/\D/g, '');
          if (value === '') {
            value = '0';
          }
          const formattedNumber = formatNumber(value);
          if (formattedNumber === null) {
            $(this).closest('.field').find('[type=hidden]').val('');
            return;
          }

          $(this).closest('.field').find('[type=hidden]').val(value);
          $(this).val(formattedNumber.formattedNumber);
        });
        if (!buying || !selling || !marginNote) {
          return;
        }
        var cost = Number(buying.value || 0) / 100;
        var price = Number(selling.value || 0) / 100;
        if (!price) {
          marginNote.textContent = 'Margin shows here once both prices are in.';
          return;
        }
        var margin = ((price - cost) / price) * 100;
        marginNote.textContent =
          'Margin ' +
          margin.toFixed(1) +
          '% — ' +
          (price - cost).toFixed(2) +
          ' on each one.';
      };

      if (buying) {
        $('#product-buying')[0].addEventListener('input', marginText);
      }
      if (selling) {
        $('#product-selling')[0].addEventListener('input', marginText);
      }
      marginText();

      var submit = productForm.querySelector('[data-product-submit]');
      var idle = submit
        ? submit.querySelector('[data-product-label]').textContent
        : '';

      productForm.addEventListener('submit', function (event) {
        event.preventDefault();
        clearError(productForm);

        var id = productForm.dataset.productId;
        var payload = {
          name: fieldOf(productForm, 'name').value.trim(),
          sku: fieldOf(productForm, 'sku').value.trim(),
          category: fieldOf(productForm, 'category').value.trim(),
          description: fieldOf(productForm, 'description').value.trim(),
          attributes: attributePairs(productForm),
          buying_price:
            Number(fieldOf(productForm, 'buying_price').value) / 100,
          selling_price:
            Number(fieldOf(productForm, 'selling_price').value) / 100,
          quantity: fieldOf(productForm, 'quantity').value,
          reorder_level: fieldOf(productForm, 'reorderLevel').value,
          unit: fieldOf(productForm, 'unit').value,
          is_published: fieldOf(productForm, 'is_published').checked,
          shop: parseInt($('.stocks').data('shop')),
        };

        if (!payload.name) {
          showError(productForm, 'Give the item a name.');
          return;
        }

        busy(submit, true, 'Saving', idle);

        var save = function () {
          if (id) {
            payload;
            return request('products/' + id + '/', {
              method: 'PATCH',
              body: payload,
            });
          }
          return request('products/', { method: 'POST', body: payload });
        };

        save()
          .then(function (product) {
            var image = $('[name=image]')[0].files[0];
            if (!image) {
              return product;
            }
            var body = new FormData();
            body.append('image', image);
            $.ajax({
              method: 'PATCH',
              url: '/smst_stocks/api/products/' + product.id + '/',
              data: body,
              processData: false,
              contentType: false,
              headers: {
                'X-CSRFToken': csrfToken(),
              },
            });
            // return request(
            //   'products/' + product.id + '/',
            //   {
            //     method: 'PATCH',
            //     body: body,
            //   },
            //   true
            // );
          })
          .then(function () {
            busy(submit, false, 'Saving', idle);
            say('Saved.');
            window.setTimeout(function () {
              window.location.href = '/smst_stocks/products/';
            }, 500);
          })
          .catch(function (error) {
            busy(submit, false, 'Saving', idle);
            showError(productForm, error.message);
          });
      });
    }

    /* ------------------------------------------------------------- publish */
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-publish]'),
      function (button) {
        button.addEventListener('click', function () {
          var id = button.dataset.publish;
          var next = button.dataset.published !== '1';

          request('products/' + id + '/publish/', {
            method: 'POST',
            body: { isPublished: next },
          })
            .then(function () {
              say(
                next
                  ? 'Published. The shared page is live.'
                  : 'Hidden from the shared page.'
              );
              window.setTimeout(function () {
                refreshPage();
              }, 700);
            })
            .catch(function (error) {
              say(error.message, true);
            });
        });
      }
    );

    /* -------------------------------------------------------------- orders */
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-order-status]'),
      function (button) {
        button.addEventListener('click', function () {
          var id = button.dataset.orderStatus;
          var status = button.dataset.status;

          request('orders/' + id + '/', {
            method: 'PATCH',
            body: { status: status },
          })
            .then(function () {
              say(
                status === 'cancelled'
                  ? 'Order cancelled. The stock is back.'
                  : 'Order marked as done.'
              );
              window.setTimeout(function () {
                refreshPage();
              }, 700);
            })
            .catch(function (error) {
              say(error.message, true);
            });
        });
      }
    );

    /* ------------------------------------------------------------- reports */
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-build-report]'),
      function (button) {
        button.addEventListener('click', function () {
          var kind = button.dataset.buildReport;
          var format = button.dataset.format;
          var state = document.querySelector(
            '[data-report-state="' + kind + '"]'
          );
          var shop = root ? root.dataset.shop : '';

          button.classList.add('is-loading');
          if (state) {
            state.hidden = false;
            state.textContent = 'Building the report…';
            state.classList.add('skeleton');
          }

          request('reports/', {
            method: 'POST',
            body: { shop: shop, kind: kind, format: format },
          })
            .then(function () {
              button.classList.remove('is-loading');
              if (state) {
                state.classList.remove('skeleton');
                state.textContent =
                  'The report is being built. It will be ready in a moment.';
              }
              window.setTimeout(function () {
                refreshPage();
              }, 3000);
            })
            .catch(function (error) {
              button.classList.remove('is-loading');
              if (state) {
                state.classList.remove('skeleton');
                state.textContent = error.message;
              }
            });
        });
      }
    );

    /* ----------------------------------------------------------------- shop */
    var shopForm = document.querySelector('[data-shop-form]');
    if (shopForm) {
      var shopSubmit = shopForm.querySelector('[data-shop-submit]');
      var shopIdle = shopSubmit
        ? shopSubmit.querySelector('[data-shop-label]').textContent
        : '';

      shopForm.addEventListener('submit', function (event) {
        event.preventDefault();
        clearError(shopForm);

        var shop = root ? root.dataset.shop : '';
        var payload = {
          name: fieldOf(shopForm, 'name').value.trim(),
          tagline: fieldOf(shopForm, 'tagline').value.trim(),
          phone: fieldOf(shopForm, 'phone').value.trim(),
          email: fieldOf(shopForm, 'email').value.trim(),
          address: fieldOf(shopForm, 'address').value.trim(),
          currency: fieldOf(shopForm, 'currency').value.trim(),
          is_public: fieldOf(shopForm, 'is_public').checked,
        };

        busy(shopSubmit, true, 'Saving', shopIdle);
        request('shops/' + shop + '/', { method: 'PATCH', body: payload })
          .then(function () {
            busy(shopSubmit, false, 'Saving', shopIdle);
            say('The shop is saved.');
          })
          .catch(function (error) {
            busy(shopSubmit, false, 'Saving', shopIdle);
            showError(shopForm, error.message);
          });
      });
    }

    var createForm = document.querySelector('[data-shop-create]');
    if (createForm) {
      var createSubmit = createForm.querySelector('[data-shop-create-submit]');
      var createIdle = createSubmit
        ? createSubmit.querySelector('[data-shop-create-label]').textContent
        : '';

      createForm.addEventListener('submit', function (event) {
        event.preventDefault();
        clearError(createForm);

        var payload = {
          name: fieldOf(createForm, 'name').value.trim(),
          currency: fieldOf(createForm, 'currency').value.trim() || 'Ksh',
        };

        if (!payload.name) {
          showError(createForm, 'Give the shop a name.');
          return;
        }

        busy(createSubmit, true, 'Creating', createIdle);
        request('shops/', { method: 'POST', body: payload })
          .then(function () {
            busy(createSubmit, false, 'Creating', createIdle);
            refreshPage();
          })
          .catch(function (error) {
            busy(createSubmit, false, 'Creating', createIdle);
            showError(createForm, error.message);
          });
      });
    }

    $('[data-time]').each(function () {
      const time = new Date($(this).data('time').trim());
      let tzDate = time.toLocaleString('en-KE', {
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      });
      $(this).text(tzDate);
    });

    /* ------------------------------------------------------------ clipboard */
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-copy]'),
      function (button) {
        button.addEventListener('click', function () {
          var value = button.dataset.copy;
          var done = function () {
            say('Link copied.');
          };

          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(value).then(done, function () {
              say('Copy the link from the box instead.', true);
            });
          } else {
            var field = document.createElement('textarea');
            field.value = value;
            document.body.appendChild(field);
            field.select();
            try {
              document.execCommand('copy');
              done();
            } catch (error) {
              say('Copy the link from the box instead.', true);
            }
            document.body.removeChild(field);
          }
        });
      }
    );

    /* --------------------------------------------------------- live figures */
    function money(value) {
      var currency = root ? root.dataset.currency || 'Ksh' : 'Ksh';
      return (
        currency +
        ' ' +
        Number(value || 0).toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })
      );
    }

    function countUp(element) {
      var text = (element.textContent || '').trim();
      var match = text.match(/^([^\d.,-]*)([\d.,]+)(.*)$/);
      if (!match) {
        return;
      }
      var prefix = match[1];
      var raw = match[2];
      var suffix = match[3];
      var target = parseFloat(raw.replace(/,/g, ''));
      if (!isFinite(target) || target === 0) {
        return;
      }
      var parts = raw.split('.');
      var decimals = parts.length > 1 ? parts[1].length : 0;
      var start = null;

      var frame = function (now) {
        if (start === null) {
          start = now;
        }
        var progress = Math.min((now - start) / 900, 1);
        var eased = 1 - Math.pow(1 - progress, 3);
        element.textContent =
          prefix +
          (target * eased).toLocaleString(undefined, {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
          }) +
          suffix;
        if (progress < 1) {
          window.requestAnimationFrame(frame);
        }
      };

      window.requestAnimationFrame(frame);
    }

    Array.prototype.forEach.call(
      document.querySelectorAll('.stat__value'),
      function (element) {
        if (reduceMotion.matches) {
          return;
        }
        window.setTimeout(function () {
          countUp(element);
        }, 220);
      }
    );

    function formatNumber(value) {
      if (
        value === null ||
        value === undefined ||
        value === '' ||
        !Number.isFinite(Number(value))
      ) {
        return 0;
      }

      const number = (parseInt(value, 10) / 100).toFixed(2);

      const rawNumber = number;
      const formattedNumber = Number(number).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });

      return {
        rawNumber,
        formattedNumber,
      };
    }

    $('body').on('input', '.price-input', function () {});

    function applyProduct(product) {
      if (!product || !product.id) {
        return;
      }
      Array.prototype.forEach.call(
        document.querySelectorAll(
          '[data-product-row="' + product.id + '"] [data-cell="quantity"]'
        ),
        function (cell) {
          cell.textContent = Number(product.quantity || 0).toLocaleString();
        }
      );
      Array.prototype.forEach.call(
        document.querySelectorAll('[data-cell="quantity"]'),
        function (cell) {
          if (cell.closest('[data-product-detail="' + product.id + '"]')) {
            cell.textContent = Number(product.quantity || 0).toLocaleString();
          }
        }
      );

      // let the charts keep up with the number the ledger just changed
      try {
        window.dispatchEvent(
          new CustomEvent('stocks:movement-recorded', { detail: product })
        );
      } catch (error) {
        /* older browsers simply keep the charts as they were */
        return error ? null : null;
      }
    }

    function applySummary(summary) {
      if (!summary) {
        return;
      }
      var set = function (name, value) {
        var element = document.querySelector('[data-stat="' + name + '"]');
        if (element) {
          element.textContent = value;
        }
      };

      set('stock_value', money(summary.stock_value));
      set('buying_value', money(summary.buying_value));
      set('units', Number(summary.units || 0).toLocaleString());
      set(
        'low_stock_count',
        Number(summary.low_stock_count || 0).toLocaleString()
      );

      var lowCount = document.querySelector('[data-low-count]');
      if (lowCount) {
        lowCount.textContent = Number(summary.low_stock_count || 0);
      }
    }

    function connect() {
      if (!root || !('WebSocket' in window)) {
        return;
      }
      var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      var socket;

      try {
        socket = new WebSocket(
          protocol + '//' + window.location.host + '/ws/smst_stocks/shop/'
        );
      } catch (error) {
        return error ? '' : 'Error';
      }

      socket.addEventListener('message', function (event) {
        var message;
        try {
          message = JSON.parse(event.data);
        } catch (error) {
          return error ? '' : 'Error';
        }
        if (!message) {
          return;
        }
        if (
          message.event === 'product.moved' ||
          message.event === 'product.updated'
        ) {
          applyProduct(message.data);
          applySummary(message.data.summary);
        }
        if (message.event === 'order.created') {
          say('New order: ' + (message.data.reference || ''));
          var orderCount = document.querySelector('[data-order-count]');
          if (orderCount) {
            orderCount.textContent = Number(orderCount.textContent || 0) + 1;
          }
        }
      });

      socket.addEventListener('close', function () {
        window.setTimeout(connect, 5000);
      });
    }

    if (root && !started) {
      started = true;
      connect();
    }
  }

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && closeSheetNow) {
      closeSheetNow();
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  document.addEventListener('htmx:afterSwap', function (event) {
    if (event.detail.target && event.detail.target.id === 'mainContent') {
      boot();
    }
  });
  document.addEventListener('htmx:historyRestore', boot);

  scrollLeftRight(
    '.stocks__app__container',
    '.stocks__nav',
    '.stocks__nav-link'
  );
})();

/* ==========================================================================
   SmSt Stocks — charts and quiet motion
   The charts are drawn with plain SVG so the app carries no chart library.
   They read the same API the rest of the page uses and keep their own state.
   ========================================================================== */

(function () {
  'use strict';

  var started = false;

  function bootCharts() {
    var root = document.querySelector('.stocks');
    if (!root) {
      return;
    }

    var API = '/smst_stocks/api/';
    var shopId = root.dataset.shop || '';
    var currency = root.dataset.currency || 'Ksh';
    var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    var NS = 'http://www.w3.org/2000/svg';
    var resizeObserver = null;

    var colours = {
      brown: '#a65a17',
      brownDeep: '#6d3f0f',
      brownSoft: '#d29a63',
      sage: '#6f7d68',
      ink: '#241e17',
      grid: '#efe9de',
      ok: '#3f6b4a',
      warn: '#8a5a12',
      err: '#9c3b2e',
      muted: '#b3a795',
    };

    /* ------------------------------------------------------------- helpers */
    function all(selector, context) {
      return Array.prototype.slice.call(
        (context || document).querySelectorAll(selector)
      );
    }

    function one(selector, context) {
      return (context || document).querySelector(selector);
    }

    function number(value) {
      var result = Number(value);
      return isFinite(result) ? result : 0;
    }

    function clamp(value, low, high) {
      return Math.min(high, Math.max(low, value));
    }

    function money(value, digits) {
      var places = digits === undefined ? 0 : digits;
      return (
        currency +
        ' ' +
        Number(value || 0).toLocaleString(undefined, {
          minimumFractionDigits: places,
          maximumFractionDigits: places,
        })
      );
    }

    function plain(value) {
      return Number(value || 0).toLocaleString(undefined, {
        maximumFractionDigits: 1,
      });
    }

    function compact(value) {
      var amount = Math.abs(value);
      if (amount >= 1000000) {
        return (value / 1000000).toFixed(1).replace(/\.0$/, '') + 'm';
      }
      if (amount >= 1000) {
        return (value / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
      }
      if (amount >= 100) {
        return Math.round(value).toString();
      }
      return (Math.round(value * 10) / 10).toString();
    }

    function svgNode(name, attributes) {
      var node = document.createElementNS(NS, name);
      if (attributes) {
        Object.keys(attributes).forEach(function (key) {
          node.setAttribute(key, attributes[key]);
        });
      }
      return node;
    }

    function emptyNode(node) {
      while (node.firstChild) {
        node.removeChild(node.firstChild);
      }
    }

    function startOfDay(date) {
      return new Date(date.getFullYear(), date.getMonth(), date.getDate());
    }

    function addDays(date, count) {
      var copy = new Date(date.getTime());
      copy.setDate(copy.getDate() + count);
      return copy;
    }

    function shortDate(date) {
      return date.toLocaleDateString(undefined, {
        day: 'numeric',
        month: 'short',
      });
    }

    function longDate(date) {
      return date.toLocaleDateString(undefined, {
        weekday: 'short',
        day: 'numeric',
        month: 'short',
      });
    }

    function dayKey(date) {
      return (
        date.getFullYear() +
        '-' +
        String(date.getMonth() + 1).padStart(2, '0') +
        '-' +
        String(date.getDate()).padStart(2, '0')
      );
    }

    function niceMax(value) {
      if (!isFinite(value) || value <= 0) {
        return 10;
      }
      if (value <= 10) {
        return Math.max(1, Math.ceil(value));
      }
      var power = Math.pow(10, Math.floor(Math.log10(value)));
      var fraction = value / power;
      var rounded =
        fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
      return rounded * power;
    }

    function relativePath(url) {
      try {
        var parsed = new URL(url, window.location.origin);
        return parsed.pathname + parsed.search;
      } catch (error) {
        return error ? url : url;
      }
    }

    function api(path) {
      return fetch(path.indexOf('https') === 0 ? path : API + path, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      }).then(function (response) {
        if (!response.ok) {
          throw new Error('The figures could not be loaded.');
        }
        return response.json();
      });
    }

    function rowsOf(data) {
      if (Array.isArray(data)) {
        return data;
      }
      if (data && Array.isArray(data.results)) {
        return data.results;
      }
      return [];
    }

    function fetchAll(path) {
      return api(path).then(function (data) {
        var rows = rowsOf(data);
        var next = data && data.next;
        var pages = 0;

        function more(collected) {
          if (!next || pages >= 8) {
            return collected;
          }
          pages += 1;
          return api(relativePath(next)).then(function (page) {
            var pageRows = rowsOf(page);
            next = page && page.next;
            return more(collected.concat(pageRows));
          });
        }

        return more(rows);
      });
    }

    function renderProductRow(product) {
      const $row = $(`
    <tr
      class="animate__animated animate__fadeIn"
      data-product-row="${product.id}"
    ></tr>
  `);

      const $productCell = $(`
    <th scope="row">
      <a class="table__item" href="/smst_stocks/products/${product.id}/">
        ${
          product.image
            ? `<img
                class="table__thumb"
                src="${product.image}"
                alt="Photo of ${product.name}"
                width="34"
                height="34"
                loading="lazy"
              >`
            : ''
        }
        <span>
          <span class="table__name">${product.name}</span>
          <span class="table__meta">${product.category}</span>
        </span>
      </a>
    </th>
  `);

      const $quantityCell = $(`
    <td class="is-numeric" data-cell="quantity">
      ${product.quantity}
    </td>
    <td class="is-numeric">${product.buying_price}</td>
    <td class="is-numeric">${product.selling_price}</td>
    <td class="is-numeric ${product.margin > 0 ? '' : 'is-thin'}">
      ${product.margin}%
    </td>
  `);

      const $stockCell = $(`
    <td>
      <span class="tag tag--${product.quantity > 0 ? 'ok' : 'out'}">
        ${product.quantity > 0 ? 'IN STOCK' : 'OUT'}
      </span>
    </td>
  `);

      const $actionsCell = $(`
    <td class="is-actions">
      <div class="row-actions">
        <button
          class="link-button"
          type="button"
          data-inline-movement="sale"
          data-product="${product.id}"
        >
          Move
        </button>

        <a
          class="link-button"
          href="/smst_stocks/products/${product.id}/edit/"
        >
          Edit
        </a>
      </div>
    </td>
  `);

      $row.append($productCell, $quantityCell, $stockCell, $actionsCell);

      return $row;
    }

    searchTable({
      input: '#product-search',
      storageKey: 'smst_products',
      apiEndpoint: 'products',
      searchKeys: ['name'],
      renderRow: renderProductRow,
      table: '[data-products-table]',
      threshold: 0,
      fallbackToAll: true,
    });

    /* -------------------------------------------------------------- reveal */
    function initReveal() {
      var items = all('[data-reveal]');
      if (!items.length) {
        return;
      }

      root.classList.add('is-reveal-ready');

      if (reduceMotion.matches || !('IntersectionObserver' in window)) {
        items.forEach(function (item) {
          item.classList.add('is-revealed');
        });
        return;
      }

      var observer = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            if (entry.isIntersecting) {
              entry.target.classList.add('is-revealed');
              observer.unobserve(entry.target);
            }
          });
        },
        { rootMargin: '0px 0px -6% 0px', threshold: 0.04 }
      );

      items.forEach(function (item, index) {
        item.style.setProperty('--reveal-delay', (index % 4) * 70 + 'ms');
        observer.observe(item);
      });
    }

    /* --------------------------------------------------------- shop switch */
    all('[data-shop-switch]').forEach(function (select) {
      select.addEventListener('change', function () {
        if (select.form) {
          select.form.submit();
        }
      });
    });

    /* ------------------------------------------------------------- sources */
    function readProducts() {
      var source = one('[data-products-source]');
      if (!source) {
        return [];
      }
      return all('span[data-name]', source).map(function (node) {
        return {
          id: node.dataset.id,
          name: node.dataset.name,
          quantity: number(node.dataset.quantity),
          buying: number(node.dataset.buying),
          selling: number(node.dataset.selling),
          reorder: number(node.dataset.reorder),
          category: node.dataset.category || 'Uncategorised',
          state: node.dataset.state || 'in_stock',
          margin: number(node.dataset.margin),
          url: node.dataset.url || '',
        };
      });
    }

    function readReorderItems() {
      var source = one('[data-reorder-source]');
      if (!source) {
        return [];
      }
      return all('span[data-name]', source).map(function (node) {
        return {
          id: node.dataset.id,
          name: node.dataset.name,
          quantity: number(node.dataset.quantity),
          suggested: number(node.dataset.suggested),
          cost: number(node.dataset.cost),
          unit: node.dataset.unit || 'piece',
          category: node.dataset.category || '',
          url: node.dataset.url || '',
        };
      });
    }

    function readMovementRows() {
      var rows = all('tr[data-movement]').map(function (row) {
        return {
          kind: row.dataset.kind,
          quantity: number(row.dataset.quantity),
          at: row.dataset.at,
          product: row.dataset.product || '',
        };
      });

      if (rows.length) {
        return rows;
      }

      var source = one('[data-ledger-source]');
      if (!source) {
        return [];
      }
      return all('span[data-kind]', source).map(function (node) {
        return {
          kind: node.dataset.kind,
          quantity: number(node.dataset.quantity),
          at: node.dataset.at,
          product: node.dataset.product || '',
        };
      });
    }

    function readHistoryRows() {
      var source = one('[data-history-source]');
      if (!source) {
        return [];
      }
      return all('span[data-kind]', source).map(function (node) {
        return {
          kind: node.dataset.kind,
          kindLabel: node.dataset.kindLabel || node.dataset.kind,
          quantity: number(node.dataset.quantity),
          at: node.dataset.at,
          note: node.dataset.note || '',
        };
      });
    }

    function normaliseMovements(rows) {
      return (rows || []).map(function (row) {
        return {
          kind: row.kind,
          kindLabel: row.kindLabel || row.kindLabel || row.kind || 'Movement',
          quantity: number(row.quantity),
          at: row.at || row.created_at,
          note: row.note || '',
          product: row.product || '',
        };
      });
    }

    function ordersForShop(rows) {
      if (!shopId) {
        return rows || [];
      }
      return (rows || []).filter(function (row) {
        return !row.shop || String(row.shop) === String(shopId);
      });
    }

    function updateProductSource(product) {
      if (!product || !product.id) {
        return;
      }
      var node = one(
        '[data-products-source] span[data-id="' + product.id + '"]'
      );
      if (!node) {
        return;
      }
      node.dataset.quantity = product.quantity;
      node.dataset.state = product.state || node.dataset.state;
      if (product.sellingPrice !== undefined) {
        node.dataset.selling = product.sellingPrice;
      }
      if (product.inStock !== undefined) {
        node.dataset.buying = product.inStock;
      }
      if (product.margin !== undefined) {
        node.dataset.margin = product.margin;
      }
    }

    /* ------------------------------------------------------------ tooltips */
    function ensureTooltip(host) {
      var tooltip = one('.chart__tooltip', host);
      if (!tooltip) {
        tooltip = document.createElement('div');
        tooltip.className = 'chart__tooltip';
        tooltip.setAttribute('role', 'status');
        tooltip.setAttribute('aria-live', 'polite');
        host.appendChild(tooltip);
      }
      return tooltip;
    }

    function showTooltip(tooltip, host, x, y, html) {
      tooltip.innerHTML = html;
      tooltip.classList.add('is-visible');
      var width = tooltip.offsetWidth || 160;
      var left = clamp(x, width / 2 + 8, host.clientWidth - width / 2 - 8);
      tooltip.style.left = left + 'px';
      tooltip.style.top = Math.max(8, y) + 'px';
    }

    function hideTooltip(tooltip) {
      tooltip.classList.remove('is-visible');
    }

    function tooltipRows(rows) {
      return rows
        .map(function (row) {
          return (
            '<div class="chart__tooltip-row"><span>' +
            row[0] +
            '</span><span>' +
            row[1] +
            '</span></div>'
          );
        })
        .join('');
    }

    /* --------------------------------------------------------- area charts */

    function renderSeriesChart(widget, points, series, options) {
      options = options || {};
      var canvas = one('[data-chart-canvas]', widget);
      var empty = one('[data-chart-empty]', widget);
      if (!canvas) {
        return;
      }

      var hasData =
        points.length > 1 &&
        series.some(function (item) {
          return points.some(function (point) {
            return number(point.values[item.key]) > 0;
          });
        });

      if (!hasData) {
        emptyNode(canvas);
        canvas.hidden = true;
        if (empty) {
          empty.hidden = false;
        }
        return;
      }

      canvas.hidden = false;
      if (empty) {
        empty.hidden = true;
      }

      var width = Math.max(320, canvas.clientWidth || 640);
      var height = options.height || 248;
      var margin = { top: 18, right: 18, bottom: 30, left: 46 };
      var plotWidth = width - margin.left - margin.right;
      var plotHeight = height - margin.top - margin.bottom;
      var maxValue = niceMax(
        Math.max.apply(
          null,
          points.map(function (point) {
            return Math.max.apply(
              null,
              series.map(function (item) {
                return number(point.values[item.key]);
              })
            );
          })
        )
      );
      var step = plotWidth / Math.max(points.length - 1, 1);

      function x(index) {
        return margin.left + index * step;
      }

      function y(value) {
        return (
          margin.top + plotHeight - (number(value) / maxValue) * plotHeight
        );
      }

      emptyNode(canvas);
      var tooltip = ensureTooltip(canvas);
      var svg = svgNode('svg', {
        viewBox: '0 0 ' + width + ' ' + height,
        role: 'img',
        tabindex: '0',
        'aria-label':
          options.label ||
          'A chart of ' +
            points.length +
            ' points between ' +
            shortDate(points[0].date) +
            ' and ' +
            shortDate(points[points.length - 1].date) +
            '.',
      });

      for (var gridIndex = 0; gridIndex <= 4; gridIndex += 1) {
        var value = (maxValue / 4) * gridIndex;
        var gridY = y(value);
        svg.appendChild(
          svgNode('line', {
            x1: margin.left,
            x2: margin.left + plotWidth,
            y1: gridY,
            y2: gridY,
            class: 'chart-grid-line',
          })
        );
        var label = svgNode('text', {
          x: margin.left - 8,
          y: gridY + 3,
          'text-anchor': 'end',
        });
        label.textContent = compact(value);
        svg.appendChild(label);
      }

      var tickCount = Math.min(5, points.length);
      for (var tick = 0; tick < tickCount; tick += 1) {
        var tickIndex = Math.round(
          (tick * (points.length - 1)) / Math.max(tickCount - 1, 1)
        );
        var tickLabel = svgNode('text', {
          x: x(tickIndex),
          y: height - 9,
          'text-anchor':
            tick === 0 ? 'start' : tick === tickCount - 1 ? 'end' : 'middle',
        });
        tickLabel.textContent = shortDate(points[tickIndex].date);
        svg.appendChild(tickLabel);
      }

      series.forEach(function (item) {
        if (item.hidden) {
          return;
        }
        var linePath = '';
        var areaPath = '';
        points.forEach(function (point, index) {
          var px = x(index);
          var py = y(point.values[item.key]);
          linePath += (index === 0 ? 'M' : 'L') + px + ' ' + py + ' ';
          areaPath += (index === 0 ? 'M' : 'L') + px + ' ' + py + ' ';
        });
        areaPath +=
          'L' +
          x(points.length - 1) +
          ' ' +
          y(0) +
          ' L' +
          x(0) +
          ' ' +
          y(0) +
          ' Z';

        svg.appendChild(
          svgNode('path', {
            d: areaPath,
            class: 'chart-area',
            fill: item.colour,
            'fill-opacity':
              item.fillOpacity === undefined ? 0.09 : item.fillOpacity,
          })
        );
        svg.appendChild(
          svgNode('path', {
            d: linePath,
            class: 'chart-line',
            stroke: item.colour,
          })
        );
      });

      var crosshair = svgNode('line', {
        class: 'chart-crosshair',
        y1: margin.top,
        y2: margin.top + plotHeight,
        opacity: 0,
      });
      svg.appendChild(crosshair);

      var hoverDots = series.map(function (item) {
        var dot = svgNode('circle', {
          r: 4,
          class: 'chart-hover-dot',
          stroke: item.colour,
          opacity: 0,
        });
        svg.appendChild(dot);
        return { key: item.key, node: dot, hidden: item.hidden };
      });

      var hit = svgNode('rect', {
        x: margin.left,
        y: margin.top,
        width: plotWidth,
        height: plotHeight,
        class: 'chart-hit',
      });
      svg.appendChild(hit);

      var activeIndex = Math.min(
        points.length - 1,
        Math.floor(points.length / 2)
      );

      function activate(index) {
        activeIndex = clamp(index, 0, points.length - 1);
        var point = points[activeIndex];
        var px = x(activeIndex);
        crosshair.setAttribute('x1', px);
        crosshair.setAttribute('x2', px);
        crosshair.setAttribute('opacity', 1);

        var topY = margin.top + plotHeight;
        hoverDots.forEach(function (dot) {
          if (
            dot.hidden ||
            !series.find(function (item) {
              return item.key === dot.key && !item.hidden;
            })
          ) {
            dot.node.setAttribute('opacity', 0);
            return;
          }
          var py = y(point.values[dot.key]);
          dot.node.setAttribute('cx', px);
          dot.node.setAttribute('cy', py);
          dot.node.setAttribute('opacity', 1);
          topY = Math.min(topY, py);
        });

        var html =
          '<p class="chart__tooltip-title">' +
          longDate(point.date) +
          '</p>' +
          options.tooltip(point, series, activeIndex);

        var scale = canvas.getBoundingClientRect().width / width || 1;
        showTooltip(tooltip, canvas, px * scale, topY * scale - 8, html);
      }

      function deactivate() {
        crosshair.setAttribute('opacity', 0);
        hoverDots.forEach(function (dot) {
          dot.node.setAttribute('opacity', 0);
        });
        hideTooltip(tooltip);
      }

      function indexFromEvent(event) {
        var rect = svg.getBoundingClientRect();
        var px = (event.clientX - rect.left) * (width / rect.width);
        return Math.round((px - margin.left) / step);
      }

      hit.addEventListener('pointermove', function (event) {
        activate(indexFromEvent(event));
      });
      hit.addEventListener('pointerleave', deactivate);
      svg.addEventListener('focus', function () {
        activate(activeIndex);
      });
      svg.addEventListener('blur', deactivate);
      svg.addEventListener('keydown', function (event) {
        if (event.key === 'ArrowRight') {
          event.preventDefault();
          activate(activeIndex + 1);
        } else if (event.key === 'ArrowLeft') {
          event.preventDefault();
          activate(activeIndex - 1);
        } else if (event.key === 'Escape') {
          deactivate();
        }
      });

      canvas.appendChild(svg);
    }

    /* --------------------------------------------------------- flow chart */
    function bucketMovements(rows, range) {
      var today = startOfDay(new Date());
      var start = addDays(today, -(range - 1));
      var buckets = [];

      for (var index = 0; index < range; index += 1) {
        buckets.push({
          date: addDays(start, index),
          values: { inflow: 0, outflow: 0 },
        });
      }

      rows.forEach(function (row) {
        var when = row.at ? new Date(row.at) : null;
        if (!when || isNaN(when.getTime())) {
          return;
        }
        var day = startOfDay(when);
        var offset = Math.round((day - start) / 86400000);
        if (offset < 0 || offset >= range) {
          return;
        }
        var amount = number(row.quantity);
        var isOut = row.kind === 'sale' || row.kind === 'loss' || amount < 0;
        if (isOut) {
          buckets[offset].values.outflow += Math.abs(amount);
        } else {
          buckets[offset].values.inflow += amount;
        }
      });

      return buckets;
    }

    function buildLegend(widget, series, onChange) {
      var legend = one('[data-chart-legend]', widget);
      if (!legend) {
        return;
      }
      emptyNode(legend);
      series.forEach(function (item) {
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'legend-btn' + (item.hidden ? ' is-off' : '');
        button.dataset.series = item.key;
        button.setAttribute('aria-pressed', item.hidden ? 'false' : 'true');
        button.innerHTML =
          '<span class="legend-btn__swatch" style="background:' +
          item.colour +
          '"></span>' +
          item.label;
        button.addEventListener('click', function () {
          item.hidden = !item.hidden;
          button.classList.toggle('is-off', item.hidden);
          button.setAttribute('aria-pressed', item.hidden ? 'false' : 'true');
          onChange();
        });
        legend.appendChild(button);
      });
    }

    function renderFlow(widget, rows) {
      var series = [
        {
          key: 'inflow',
          label: 'In',
          colour: colours.brown,
          hidden: Boolean(widget._inHidden),
          fillOpacity: 0.1,
        },
        {
          key: 'outflow',
          label: 'Out',
          colour: colours.sage,
          hidden: Boolean(widget._outHidden),
          fillOpacity: 0.08,
        },
      ];

      var range = number(widget.dataset.range) || 30;
      var points = bucketMovements(rows, range);

      buildLegend(widget, series, function () {
        widget._inHidden = series[0].hidden;
        widget._outHidden = series[1].hidden;
        renderSeriesChart(widget, points, series, {
          height: 248,
          label:
            'Stock in and out over the last ' +
            range +
            ' days. Use the arrow keys to read each day.',
          tooltip: function (point) {
            var inflow = number(point.values.inflow);
            var outflow = number(point.values.outflow);
            return (
              tooltipRows([
                ['In', plain(inflow)],
                ['Out', plain(outflow)],
              ]) +
              '<div class="chart__tooltip-row chart__tooltip-total"><span>Net</span><span>' +
              (inflow - outflow > 0 ? '+' : '') +
              plain(inflow - outflow) +
              '</span></div>'
            );
          },
        });
      });

      renderSeriesChart(widget, points, series, {
        height: 248,
        label:
          'Stock in and out over the last ' +
          range +
          ' days. Use the arrow keys to read each day.',
        tooltip: function (point) {
          var inflow = number(point.values.inflow);
          var outflow = number(point.values.outflow);
          return (
            tooltipRows([
              ['In', plain(inflow)],
              ['Out', plain(outflow)],
            ]) +
            '<div class="chart__tooltip-row chart__tooltip-total"><span>Net</span><span>' +
            (inflow - outflow > 0 ? '+' : '') +
            plain(inflow - outflow) +
            '</span></div>'
          );
        },
      });
    }

    function loadFlow(widget, force) {
      var rows = readMovementRows();
      widget._movements = rows;
      renderFlow(widget, rows);

      if (!shopId) {
        return;
      }

      fetchAll('movements/?shop=' + encodeURIComponent(shopId))
        .then(function (data) {
          widget._movements = normaliseMovements(data);
          renderFlow(widget, widget._movements);
        })
        .catch(function () {
          if (force) {
            renderFlow(widget, readMovementRows());
          }
        });
    }

    /* -------------------------------------------------------- donut chart */
    function renderDonut(widget, segments, options) {
      options = options || {};
      var canvas = one('[data-chart-canvas]', widget);
      var empty = one('[data-chart-empty]', widget);
      if (!canvas) {
        return;
      }

      var visible = segments.filter(function (segment) {
        return !segment.hidden && segment.value > 0;
      });
      var total = visible.reduce(function (sum, segment) {
        return sum + segment.value;
      }, 0);

      var hasValue = segments.some(function (segment) {
        return segment.value > 0;
      });
      if (!hasValue) {
        emptyNode(canvas);
        canvas.hidden = true;
        if (empty) {
          empty.hidden = false;
        }
        return;
      }

      canvas.hidden = false;
      if (empty) {
        empty.hidden = true;
      }
      emptyNode(canvas);

      var figure = document.createElement('div');
      figure.className = 'donut__figure';
      var chartHost = canvas.closest('.chart') || canvas;
      var tooltip = ensureTooltip(chartHost);

      var size = 120;
      var radius = 46;
      var circumference = 2 * Math.PI * radius;
      var svg = svgNode('svg', {
        viewBox: '0 0 ' + size + ' ' + size,
        class: 'donut__svg',
        role: 'img',
        'aria-label': options.label || 'A breakdown of the total.',
      });

      svg.appendChild(
        svgNode('circle', {
          cx: 60,
          cy: 60,
          r: radius,
          fill: 'none',
          stroke: '#f0ebe1',
          'stroke-width': 16,
        })
      );

      var offset = 0;
      visible.forEach(function (segment) {
        var length = (segment.value / total) * circumference;
        var drawn = Math.max(length - 1.5, 0.5);
        var circle = svgNode('circle', {
          cx: 60,
          cy: 60,
          r: radius,
          fill: 'none',
          stroke: segment.colour,
          'stroke-width': 16,
          'stroke-dasharray': drawn + ' ' + (circumference - drawn),
          'stroke-dashoffset': -offset,
          transform: 'rotate(-90 60 60)',
          class: 'donut__seg',
          tabindex: '0',
          role: 'button',
          'aria-label':
            segment.label +
            ': ' +
            plain(segment.value) +
            ' of ' +
            plain(total) +
            '.',
        });

        function seek() {
          var rect = figure.getBoundingClientRect();
          showTooltip(
            tooltip,
            chartHost,
            rect.left - chartHost.getBoundingClientRect().left + rect.width / 2,
            rect.top - chartHost.getBoundingClientRect().top + 14,
            '<p class="chart__tooltip-title">' +
              segment.label +
              '</p><div class="chart__tooltip-row"><span>Count</span><span>' +
              plain(segment.value) +
              '</span></div><div class="chart__tooltip-row"><span>Share</span><span>' +
              Math.round((segment.value / total) * 100) +
              '%</span></div>'
          );
        }

        circle.addEventListener('pointerenter', seek);
        circle.addEventListener('focus', seek);
        circle.addEventListener('pointerleave', function () {
          hideTooltip(tooltip);
        });
        circle.addEventListener('blur', function () {
          hideTooltip(tooltip);
        });
        circle.addEventListener('keydown', function (event) {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            if (options.onSelect) {
              options.onSelect(segment.key);
            } else {
              toggleSegment(segment);
            }
          }
        });
        circle.addEventListener('click', function () {
          if (options.onSelect) {
            options.onSelect(segment.key);
          } else {
            toggleSegment(segment);
          }
        });

        svg.appendChild(circle);
        offset += length;
      });

      figure.appendChild(svg);

      var centre = document.createElement('div');
      centre.className = 'donut__center';
      centre.innerHTML =
        '<span class="donut__total">' +
        plain(total) +
        '</span><span class="donut__caption">' +
        (options.caption || 'total') +
        '</span>';
      figure.appendChild(centre);
      canvas.appendChild(figure);

      var legend = document.createElement('div');
      legend.className = 'donut__legend';

      function toggleSegment(segment) {
        segment.hidden = !segment.hidden;
        renderDonut(widget, segments, options);
      }

      segments.forEach(function (segment) {
        var key = document.createElement('button');
        key.type = 'button';
        key.className = 'donut__key' + (segment.hidden ? ' is-off' : '');
        key.setAttribute('aria-pressed', segment.hidden ? 'false' : 'true');
        key.innerHTML =
          '<span class="donut__dot" style="--key:' +
          segment.colour +
          '"></span><span class="donut__key-label">' +
          segment.label +
          '</span><span class="donut__key-value"><strong>' +
          plain(segment.value) +
          '</strong> · ' +
          (total ? Math.round((segment.value / total) * 100) : 0) +
          '%</span>';
        key.addEventListener('click', function () {
          if (options.onSelect) {
            options.onSelect(segment.key);
          } else {
            segment.hidden = !segment.hidden;
            renderDonut(widget, segments, options);
          }
        });
        legend.appendChild(key);
      });

      canvas.appendChild(legend);
    }

    /* ------------------------------------------------------------ ordering */
    function renderHealth(widget) {
      var products = readProducts();
      var counts = { inStock: 0, low: 0, out: 0 };
      products.forEach(function (product) {
        if (product.quantity <= 0 || product.state === 'out') {
          counts.out += 1;
        } else if (product.state === 'low') {
          counts.low += 1;
        } else {
          counts.inStock += 1;
        }
      });

      var segments = [
        {
          key: 'in_stock',
          label: gettext('In stock'),
          value: counts.inStock,
          colour: colours.ok,
        },
        {
          key: 'low',
          label: gettext('Running low'),
          value: counts.low,
          colour: colours.warn,
        },
        {
          key: 'out',
          label: gettext('Out of stock'),
          value: counts.out,
          colour: colours.err,
        },
      ];

      renderDonut(widget, segments, { caption: 'items' });
    }

    /* -------------------------------------------------------------- bars */
    function barRow(item, maximum, formatValue, note, href, tagName) {
      var row = document.createElement(tagName || 'button');
      if (!tagName) {
        row.type = 'button';
      }
      row.className = 'bar-row' + (item.value > 0 ? '' : ' is-empty');
      if (href) {
        row.dataset.url = href;
        row.addEventListener('click', function () {
          window.location.href = href;
        });
      }
      var percent = maximum > 0 ? (item.value / maximum) * 100 : 0;
      row.innerHTML =
        '<span class="bar-row__label">' +
        item.label +
        (note ? '<span class="bar-row__note">' + note + '</span>' : '') +
        '</span><span class="bar-row__value">' +
        formatValue(item.value, item) +
        '</span><span class="bar-row__track"><span class="bar-row__fill" style="--bar:' +
        Math.max(percent, item.value > 0 ? 2 : 0) +
        '%"></span></span>';
      return row;
    }

    function renderBars(widget, rowsData, options) {
      options = options || {};
      var canvas = one('[data-chart-canvas]', widget);
      var empty = one('[data-chart-empty]', widget);
      if (!canvas) {
        return;
      }

      emptyNode(canvas);
      var usable = rowsData.filter(function (row) {
        return row.value > 0;
      });

      if (!usable.length) {
        canvas.hidden = true;
        if (empty) {
          empty.hidden = false;
        }
        return;
      }

      canvas.hidden = false;
      if (empty) {
        empty.hidden = true;
      }
      var maximum = Math.max.apply(
        null,
        usable.map(function (row) {
          return row.value;
        })
      );
      usable.forEach(function (row) {
        canvas.appendChild(
          barRow(
            row,
            maximum,
            options.format || plain,
            row.note || '',
            row.url || '',
            options.tagName || 'button'
          )
        );
      });
    }

    function renderValue(widget) {
      var products = readProducts();
      var metric = widget.dataset.metric || 'value';

      var rowsData = products
        .map(function (product) {
          var value =
            metric === 'units'
              ? product.quantity
              : metric === 'margin'
                ? product.quantity * (product.selling - product.buying)
                : product.quantity * product.selling;
          var note =
            metric === 'units'
              ? money(product.selling) + ' each'
              : metric === 'margin'
                ? product.margin.toFixed(1) + '% margin'
                : product.category;
          return {
            label: product.name,
            value: value,
            note: note,
            url: product.url,
            product: product,
          };
        })
        .sort(function (a, b) {
          return b.value - a.value;
        })
        .slice(0, 7);

      renderBars(widget, rowsData, {
        format: function (value) {
          return metric === 'units' ? plain(value) : money(value);
        },
      });
    }

    function renderCategories(widget) {
      var products = readProducts();
      var metric = widget.dataset.metric || 'value';
      var groups = {};

      products.forEach(function (product) {
        var key = product.category || 'Uncategorised';
        if (!groups[key]) {
          groups[key] = {
            label: key,
            value: 0,
            note: '',
            url: '',
            count: 0,
          };
        }
        groups[key].count += 1;
        groups[key].value +=
          metric === 'units'
            ? product.quantity
            : metric === 'margin'
              ? product.quantity * (product.selling - product.buying)
              : product.quantity * product.selling;
      });

      var rowsData = Object.keys(groups)
        .map(function (key) {
          var group = groups[key];
          group.note = group.count + ' item' + (group.count === 1 ? '' : 's');
          return group;
        })
        .sort(function (a, b) {
          return b.value - a.value;
        })
        .slice(0, 8);

      renderBars(widget, rowsData, {
        tagName: 'div',
        format: function (value) {
          return metric === 'units' ? plain(value) : money(value);
        },
      });
    }

    function renderReorder(widget) {
      var items = readReorderItems();
      var metric = widget.dataset.metric || 'units';
      var rowsData = items
        .map(function (item) {
          return {
            label: item.name,
            value: metric === 'cost' ? item.cost : item.suggested,
            note:
              metric === 'cost'
                ? plain(item.suggested) + ' ' + item.unit + 's'
                : plain(item.quantity) + ' in hand',
            url: item.url,
          };
        })
        .sort(function (a, b) {
          return b.value - a.value;
        })
        .slice(0, 8);

      renderBars(widget, rowsData, {
        format: function (value) {
          return metric === 'cost' ? money(value) : plain(value);
        },
      });
    }

    /* ------------------------------------------------------------- orders */
    function renderOrders(widget, rows) {
      var labels = {
        pending: gettext('Pending'),
        confirmed: gettext('Confirmed'),
        fulfilled: gettext('Fulfilled'),
        cancelled: gettext('Cancelled'),
      };
      var palette = {
        pending: colours.warn,
        confirmed: colours.brown,
        fulfilled: colours.ok,
        cancelled: colours.muted,
      };
      var counts = { pending: 0, confirmed: 0, fulfilled: 0, cancelled: 0 };

      rows.forEach(function (row) {
        var status = row.status;
        if (counts[status] === undefined) {
          counts[status] = 0;
        }
        counts[status] += 1;
      });

      var segments = Object.keys(counts).map(function (key) {
        return {
          key: key,
          label: labels[key] || key,
          value: counts[key],
          colour: palette[key] || colours.muted,
        };
      });

      renderDonut(widget, segments, {
        caption: 'orders',
        label: 'Orders by status. Choose a status to filter the list.',
        onSelect: function (key) {
          var query = new URLSearchParams();
          query.set('status', key);
          if (shopId) {
            query.set('shop', shopId);
          }
          window.location.href = '?' + query.toString();
        },
      });
    }

    function readOrderRows() {
      return all('tr[data-order-row]').map(function (row) {
        return {
          status: row.dataset.orderState,
          total: number(row.dataset.orderTotal),
          at: row.dataset.orderAt,
        };
      });
    }

    /* ------------------------------------------------------ product history */
    function renderHistory(widget, rows) {
      var canvas = one('[data-chart-canvas]', widget);
      var empty = one('[data-chart-empty]', widget);
      if (!canvas) {
        return;
      }

      var current = number(widget.dataset.quantity);
      var chronological = rows.slice().sort(function (a, b) {
        return new Date(a.at) - new Date(b.at);
      });

      var initial =
        current -
        chronological.reduce(function (sum, row) {
          return sum + row.quantity;
        }, 0);

      var points = [];
      var running = initial;
      if (chronological.length) {
        points.push({
          date: new Date(chronological[0].at),
          values: { level: running },
          row: {
            kindLabel: 'Opening balance',
            quantity: 0,
            note: 'Before the first recorded movement',
          },
        });
      }
      chronological.forEach(function (row) {
        running += row.quantity;
        points.push({
          date: new Date(row.at),
          values: { level: running },
          row: row,
        });
      });

      var range = number(widget.dataset.range) || 20;
      if (points.length > range) {
        points = points.slice(points.length - range);
      }

      var series = [
        {
          key: 'level',
          label: 'In hand',
          colour: colours.brown,
          hidden: false,
          fillOpacity: 0.1,
        },
      ];

      renderSeriesChart(widget, points, series, {
        height: 220,
        label:
          'Quantity in hand after each movement. Use the arrow keys to read each point.',
        tooltip: function (point) {
          var row = point.row || {};
          var change = number(row.quantity);
          return (
            tooltipRows([
              [
                row.kindLabel || 'Movement',
                (change > 0 ? '+' : '') + plain(change),
              ],
              ['In hand', plain(point.values.level)],
            ]) +
            (row.note
              ? '<div class="chart__tooltip-row"><span>Note</span><span>' +
                row.note +
                '</span></div>'
              : '')
          );
        },
      });
    }

    /* ----------------------------------------------------------- chart boot */
    function renderWidget(widget) {
      var kind = widget.dataset.chart;
      if (kind === 'flow' || kind === 'movements-flow') {
        loadFlow(widget);
      } else if (kind === 'health') {
        renderHealth(widget);
      } else if (kind === 'value') {
        renderValue(widget);
      } else if (kind === 'categories') {
        renderCategories(widget);
      } else if (kind === 'reorder') {
        renderReorder(widget);
      } else if (kind === 'orders') {
        if (widget._orders) {
          renderOrders(widget, widget._orders);
        } else {
          renderOrders(widget, readOrderRows());
          if (shopId) {
            fetchAll('orders/?shop=' + encodeURIComponent(shopId))
              .then(function (rows) {
                widget._orders = ordersForShop(rows);
                renderOrders(widget, widget._orders);
              })
              .catch(function () {
                /* the page rows are enough */
              });
          }
        }
      } else if (kind === 'product-history') {
        var productId = widget.dataset.product || '';
        renderHistory(widget, readHistoryRows());
        if (productId) {
          fetchAll('movements/?product=' + encodeURIComponent(productId))
            .then(function (rows) {
              widget._history = normaliseMovements(rows);
              renderHistory(widget, widget._history);
            })
            .catch(function () {
              /* the page rows are enough */
            });
        }
      }
    }

    function initChartControls() {
      all('[data-flow-range]').forEach(function (control) {
        control.addEventListener('click', function (event) {
          var button = event.target.closest('[data-range]');
          if (!button) {
            return;
          }
          var widget = control.closest('[data-chart]');
          if (!widget) {
            return;
          }
          all('[data-range]', control).forEach(function (item) {
            item.classList.toggle('is-active', item === button);
          });
          widget.dataset.range = button.dataset.range;
          renderWidget(widget);
        });
      });

      all('[data-value-metric]').forEach(function (control) {
        control.addEventListener('click', function (event) {
          var button = event.target.closest('[data-metric]');
          if (!button) {
            return;
          }
          var widget = control.closest('[data-chart]');
          if (!widget) {
            return;
          }
          all('[data-metric]', control).forEach(function (item) {
            item.classList.toggle('is-active', item === button);
          });
          widget.dataset.metric = button.dataset.metric;
          renderWidget(widget);
        });
      });

      all('[data-reorder-metric]').forEach(function (control) {
        control.addEventListener('click', function (event) {
          var button = event.target.closest('[data-metric]');
          if (!button) {
            return;
          }
          var widget = control.closest('[data-chart]');
          if (!widget) {
            return;
          }
          all('[data-metric]', control).forEach(function (item) {
            item.classList.toggle('is-active', item === button);
          });
          widget.dataset.metric = button.dataset.metric;
          renderWidget(widget);
        });
      });

      all('[data-history-range]').forEach(function (control) {
        control.addEventListener('click', function (event) {
          var button = event.target.closest('[data-range]');
          if (!button) {
            return;
          }
          var widget = control.closest('[data-chart]');
          if (!widget) {
            return;
          }
          all('[data-range]', control).forEach(function (item) {
            item.classList.toggle('is-active', item === button);
          });
          widget.dataset.range = button.dataset.range;
          renderWidget(widget);
        });
      });
    }

    function initResize() {
      if (!('ResizeObserver' in window)) {
        if (!started) {
          window.addEventListener('resize', function () {
            all('[data-chart]').forEach(function (widget) {
              var kind = widget.dataset.chart;
              if (kind === 'flow' || kind === 'movements-flow') {
                renderFlow(widget, widget._movements || readMovementRows());
              } else if (kind === 'product-history') {
                renderHistory(widget, widget._history || readHistoryRows());
              }
            });
          });
        }
        return;
      }

      if (resizeObserver) {
        resizeObserver.disconnect();
      }
      var observer = new ResizeObserver(function (entries) {
        entries.forEach(function (entry) {
          var widget = entry.target.closest('[data-chart]');
          if (!widget) {
            return;
          }
          var width = Math.round(entry.contentRect.width);
          if (widget._lastWidth === width || width < 100) {
            return;
          }
          widget._lastWidth = width;
          var kind = widget.dataset.chart;
          if (kind === 'flow' || kind === 'movements-flow') {
            renderFlow(widget, widget._movements || readMovementRows());
          } else if (kind === 'product-history') {
            renderHistory(widget, widget._history || readHistoryRows());
          } else if (
            kind === 'health' ||
            kind === 'value' ||
            kind === 'categories' ||
            kind === 'reorder' ||
            kind === 'orders'
          ) {
            renderWidget(widget);
          }
        });
      });
      resizeObserver = observer;

      all('[data-chart-canvas]').forEach(function (canvas) {
        observer.observe(canvas);
      });
    }

    function initCharts() {
      all('[data-chart]').forEach(renderWidget);
    }

    function refreshCharts(product) {
      updateProductSource(product);
      all('[data-chart]').forEach(function (widget) {
        var kind = widget.dataset.chart;
        if (kind === 'flow' || kind === 'movements-flow') {
          loadFlow(widget, true);
        } else if (kind === 'orders') {
          if (widget._orders) {
            renderOrders(widget, widget._orders);
          }
        } else if (kind === 'product-history') {
          var productId = widget.dataset.product || '';
          if (productId) {
            fetchAll(
              'movements/?product=' + encodeURIComponent(productId)
            ).then(function (rows) {
              widget._history = normaliseMovements(rows);
              renderHistory(widget, widget._history);
            });
          }
        } else {
          renderWidget(widget);
        }
      });
    }

    initReveal();
    initChartControls();
    initCharts();
    initResize();

    

    if (!started) {
      started = true;
      window.addEventListener('stocks:movement-recorded', function (event) {
        refreshCharts(event.detail);
      });
    }
  }

  bootCharts();

  document.addEventListener('htmx:afterSwap', function (event) {
    if (event.detail.target && event.detail.target.id === 'mainContent') {
      bootCharts();
    }
  });
  document.addEventListener('htmx:historyRestore', bootCharts);
})();
