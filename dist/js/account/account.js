import {
  debounce,
  checkEmail,
  updateCooldown,
  startCooldown,
  parseDuration,
  handleHttpError,
} from '/static/js/common/functions.prod.js';
import {
  showOutput,
  showSuccessMessage,
  clearOutput,
  showErrorMessage,
} from '/static/js/common/notification.prod.js';

document.addEventListener('DOMContentLoaded', function () {
  let csrftoken = $('[name="csrftoken"]')[0].content;
  updateCooldown();
  $(document).ajaxError(function (event, xhr) {
    handleHttpError(xhr.status);
  });

  document.body.addEventListener('htmx:responseError', function (event) {
    handleHttpError(event.detail.xhr.status);
  });

  $.ajaxPrefilter(function (options, originalOptions, jqXHR) {
    if (localStorage.getItem('login_cooldown_until')) {
      updateCooldown();
      jqXHR.abort();
    }
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
  });

  $('main').on('click', '#formButton', function () {
    let invalid = false;
    $('input').each(function () {
      const $input = $(this);
      let val = $input.val().trim();
      if (val.length <= 0) {
        showErrorMessage(
          gettext('Empty Fields'),
          gettext('Kindly fill the input with information')
        );
        invalid = true;
        return;
      }
    });
    if (invalid) {
      invalid = false;
      return;
    }
    let $username = $('#username');
    let $email = $('#email');
    let $otp = $('#fullOtp');
    let $pwd1 = $('#password1');
    let $resetPwd1 = $('#reppassword1');
    let $pwd2 = $('#password2');
    let $resetPwd2 = $('#reppassword2');
    let $loginEmail = $('#login_email');
    let $loginPassword = $('#login_password');
    let $resetEmail = $('#reset_email');
    if ($username.length) {
      let username = $username.val().trim();
      $.ajax({
        type: 'POST',
        headers: {
          'X-CSRFToken': csrftoken,
        },
        url: '/?action=update_username',
        data: JSON.stringify({
          username: username,
        }),
        success: function (response) {
          if (response.status) {
            showSuccessMessage(
              gettext('Username Changed'),
              gettext('You have successfully updated your username.')
            ).done(() => {
              window.location.reload();
            });
          } else {
            showErrorMessage(
              gettext('Error'),
              gettext('Your username could not be changed.')
            );
          }
        },
      });
    } else if ($email.length) {
      $.ajax({
        type: 'POST',
        headers: {
          'X-CSRFToken': csrftoken,
        },
        data: JSON.stringify({
          email: $email.val().trim(),
        }),
        url: '/?action=verify_email',
        success: function (response) {
          $('#formContent').empty().append(response);
        },
      });
    } else if ($otp.length) {
      if ($otp.val().trim().length < 5) {
        showErrorMessage(
          gettext('Invalid OTP'),
          gettext('The OTP is 6 digits long.')
        );
        return;
      }
      $.ajax({
        type: 'POST',
        url: '?action=validate_email',
        headers: {
          'X-CSRFToken': csrftoken,
        },
        data: JSON.stringify({
          otp: $otp.val().trim(),
        }),
        success: function (response) {
          let status = response.status;
          if (status == 'social_auth') {
            window.location.href = response.url;
            return;
          } else if (status) {
            showSuccessMessage(
              gettext('OTP Correct!'),
              gettext('Validating your details')
            ).done(() => {
              $('#formContent').empty().append(response.html);
            });
          } else {
            showErrorMessage(
              gettext('Invalid OTP!'),
              gettext(
                'Confirm you are entering the latest password and it has not expired.'
              )
            );
          }
        },
      });
    } else if ($pwd1.length && $pwd2.length) {
      let value = $pwd1.val().trim();
      let repValue = $pwd2.val().trim();
      if (value == repValue) {
        $.ajax({
          type: 'POST',
          url: '?action=create_account',
          headers: {
            'X-CSRFToken': csrftoken,
          },
          data: JSON.stringify({
            password: value,
          }),
          success: function (response) {
            if (response.status) {
              showOutput(
                gettext('Details Saved'),
                gettext('Log into your account.')
              );
              window.location.reload();
            } else {
              showErrorMessage(
                gettext('Error Occurred'),
                gettext('Try creating again.')
              );
            }
          },
        });
      }
    } else if ($loginEmail.length && $loginPassword.length) {
      let email = $loginEmail.val().trim();
      let password = $loginPassword.val().trim();
      $.ajax({
        type: 'POST',
        url: '?action=login_user',
        headers: {
          'X-CSRFToken': csrftoken,
        },
        data: JSON.stringify({
          email: email,
          password: password,
        }),
        success: function (response) {
          let status = response.status;
          if (status) {
            showSuccessMessage('Success', 'Logging your Account').done(() => {
              window.location.reload();
            });
          } else {
            showErrorMessage(
              gettext('Invalid'),
              gettext('You have entered the wrong password or email.')
            );
          }
        },
        error: function (xhr) {
          if (xhr.status === 429) {
            const data = xhr.responseJSON;

            const seconds = parseDuration(data.cooloff_timedelta);
            startCooldown(seconds);
          }
        },
      });
    } else if ($resetEmail.length) {
      $.ajax({
        type: 'POST',
        headers: {
          'X-CSRFToken': csrftoken,
        },
        url: '?action=reset_email',
        data: JSON.stringify({
          email: $resetEmail.val().trim(),
        }),
        success: function (response) {
          $('#formContent').empty().append(response);
        },
      });
    } else if ($resetPwd1.length && $resetPwd2.length) {
      const params = new URLSearchParams(window.location.search);
      $.ajax({
        type: 'POST',
        headers: {
          'X-CSRFToken': csrftoken,
        },
        url: '/?action=change_password',
        data: JSON.stringify({
          password1: $resetPwd1.val().trim(),
          password2: $resetPwd2.val().trim(),
          token: params.get('token'),
        }),
        success: function (response) {
          if (response.status) {
            showSuccessMessage(
              gettext('Password Changed'),
              gettext('Login with your new values')
            ).done(() => {
              $('#formContent').empty().append(response.html);
              return;
            });
          }
          showErrorMessage(
            gettext('Password Not Changed'),
            gettext('Kindly Try again.')
          );
        },
      });
    }
  });

  $('main').on(
    'input',
    '#email, #reset_email',
    debounce(function (e) {
      const value = e.target.value.trim().toLowerCase();
      $(this).val(value);
      if (!checkEmail(value)) {
        showOutput(gettext('Kindly Enter a valid Email'));
        return;
      }
      clearOutput();
    })
  );
  let otpCode = [];
  $('main').on('input', '.numeric-input', function () {
    let $this = $(this);
    let value = $this.val().replace(/[^0-9]/g, '');
    $this.val(value);
    value = $(this).val();
    if (value.length == 1) {
      if ($this.next().length) {
        $this.next().focus();
      }
    }

    $('.numeric-input').each((_, input) => {
      let value = input.value.trim();
      otpCode.push(value);
    });
    $('.otpFullValue').val(otpCode.join(''));
    otpCode = [];
  });

  $('main').on('keydown', '.numeric-input', function (e) {
    let $this = $(this);
    if (e.key == 'Backspace') {
      if ($this.prev().length && $this.val().length == 0) {
        e.preventDefault();
        $this.prev().focus();
      }
    }
  });
});
