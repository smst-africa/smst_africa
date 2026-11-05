import {
  debounce,
  validatePassword,
  handleHttpError,
} from '/static/js/common/functions.prod.js';
import {
  showOutput,
  clearOutput,
} from '/static/js/common/notification.prod.js';

document.addEventListener('DOMContentLoaded', function () {
  $(document).ajaxError(function (event, xhr) {
    handleHttpError(xhr.status);
  });

  $(document).ajaxStart(function () {
    NProgress.start();
  });
  $(document).ajaxComplete(function () {
    NProgress.done();
  });

  $(document).on('htmx:beforeRequest', function () {
    NProgress.start();
  });

  $(document).on('htmx:afterSwap', function () {
    NProgress.done();
    resetTime();
    if ($('.is-active').length) {
      $('.is-active')[0].scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }
  });

  $('main').on(
    'input',
    '#username',
    debounce(function (e) {
      const value = e.target.value
        .toLowerCase()
        .trim()
        .replace(/[^a-zA-Z0-9_]/g, '');
      e.target.value = value;

      if (value.length <= 4) {
        showOutput(gettext('Username too short.'));
        return;
      } else if (value.length > 12) {
        showOutput(gettext('Username too long.'));
        return;
      }
      $.ajax({
        type: 'GET',
        url: `/?action=check_username&username=${value}`,
        success: function (response) {
          if (response.status == 'valid') {
            showOutput(gettext('Username is unique.'), true);
          } else {
            showOutput(gettext('Username already taken.'));
          }
        },
      });
    })
  );

  $('main').on(
    'input',
    '#password1, #reppassword1',
    debounce(function (e) {
      let value = e.target.value.trim();
      $(this).val(value);
      const error = validatePassword(value);
      if (error) {
        showOutput(error);
        return;
      }
      clearOutput();
    })
  );
  $('main').on(
    'input',
    '#password2, #reppassword2',
    debounce(function (e) {
      let value = e.target.value.trim();
      let passwordField =
        e.target.id === 'password2' ? '#password1' : '#reppassword1';
      if (value !== $(passwordField).val()) {
        showOutput(gettext('Passwords do not match.'));
        return;
      }
      clearOutput();
    })
  );

  $('body').on('keypress', 'input', function (e) {
    if (e.key == 'Enter') {
      $(this).parent().parent().find('button').trigger('click');
    }
  });
  window.visualViewport?.addEventListener('resize', () => {
    document.documentElement.style.setProperty(
      '--vh',
      `${window.visualViewport.height}px`
    );
  });

  function resetTime() {
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
  }

  resetTime();

  $('input').on('focus', function (e) {
    if ($(this).closest('.sheet__panel').length) {
      $(this).closest('.field')[0].scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      });
    }
  });
});
