/* ==========================================================================
   SmSt Stocks — the shared page
   A customer asks for an item, and the stock line keeps up with the shop.
   ========================================================================== */

(function () {
  'use strict';

  var page = document.querySelector('[data-public-product]');
  var form = document.querySelector('[data-order-form]');

  function csrfToken() {
    var meta = document.querySelector(
      'meta[name="csrftoken"], meta[name="csrf-token"]'
    );
    return meta ? meta.content : '';
  }

  function say(message, isError) {
    if (!form) {
      return;
    }
    var slot = form.querySelector('[data-order-error]');
    if (!slot) {
      return;
    }
    slot.textContent = message;
    slot.hidden = !message;
    slot.style.background = isError ? 'var(--err-bg)' : 'var(--ok-bg)';
    slot.style.color = isError ? 'var(--err)' : 'var(--ok)';
  }

  if (form) {
    var submit = form.querySelector('[data-order-submit]');
    var label = form.querySelector('[data-order-label]');
    var idle = label ? label.textContent : '';

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      say('');

      var name = form.querySelector('[name="customer_name"]').value.trim();
      var phone = form.querySelector('[name="customer_phone"]').value.trim();

      if (!name) {
        say('Tell us your name.', true);
        return;
      }
      if (!phone) {
        say('Give us a phone number to reach you on.', true);
        return;
      }

      if (submit) {
        submit.classList.add('is-loading');
        submit.disabled = true;
      }
      if (label) {
        label.textContent = 'Sending';
      }

      fetch('/smst_stocks/api/public/orders/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken(),
        },
        body: JSON.stringify({
          product: form.dataset.product,
          customer_name: name,
          customer_phone: phone,
          customer_email: form
            .querySelector('[name="customer_email"]')
            .value.trim(),
          quantity: form.querySelector('[name="quantity"]').value,
          note: form.querySelector('[name="note"]').value.trim(),
        }),
      })
        .then(function (response) {
          return response.json().then(function (data) {
            return { ok: response.ok, data: data };
          });
        })
        .then(function (result) {
          if (!result.ok) {
            if (submit) {
              submit.classList.remove('is-loading');
              submit.disabled = false;
            }
            if (label) {
              label.textContent = idle;
            }
            say(
              result.data.detail || 'We could not send that. Please try again.',
              true
            );
            return;
          }

          if (submit) {
            submit.classList.remove('is-loading');
            submit.disabled = true;
          }
          if (label) {
            label.textContent = 'Sent';
          }

          var done = form.querySelector('[data-order-done]');
          var reference = form.querySelector('[data-order-reference]');
          if (reference) {
            reference.textContent = 'Reference ' + result.data.reference;
          }
          if (done) {
            done.hidden = false;
          }
          form
            .querySelectorAll('input, textarea, button')
            .forEach(function (element) {
              element.disabled = true;
            });
        })
        .catch(function () {
          if (submit) {
            submit.classList.remove('is-loading');
            submit.disabled = false;
          }
          if (label) {
            label.textContent = idle;
          }
          say('The connection failed. Please try again.', true);
        });
    });
  }

  /* -------------------------------------------------------------- live stock */
  if (page && 'WebSocket' in window) {
    var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    var socket;

    try {
      socket = new WebSocket(
        protocol +
          '//' +
          window.location.host +
          '/ws/smst_stocks/product/' +
          page.dataset.publicProduct +
          '/'
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
      if (!message || !message.data || message.data.quantity === undefined) {
        return;
      }

      var line = document.querySelector('[data-stock-badge]');
      var text = document.querySelector('[data-stock-text]');
      var quantity = Number(message.data.quantity || 0);
      var state = message.data.state || 'in_stock';

      if (line) {
        line.className = 'stock-line stock-line--' + state;
      }
      if (text) {
        if (quantity <= 0) {
          text.textContent = 'Out of stock at the moment';
        } else if (state === 'low') {
          text.textContent = 'Only ' + quantity + ' left';
        } else {
          text.textContent = quantity + ' in stock';
        }
      }

      var field = document.querySelector('[name="quantity"]');
      if (field) {
        field.max = String(quantity);
        if (Number(field.value) > quantity) {
          field.value = String(Math.max(quantity, 1));
        }
      }

      if (quantity <= 0 && form) {
        form
          .querySelectorAll('input, textarea, button')
          .forEach(function (element) {
            element.disabled = true;
          });
      }
    });
  }
})();
