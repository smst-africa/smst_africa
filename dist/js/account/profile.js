import {
  handleHttpError,
  enableNotifications,
  checkInput,
  unsubscribeNotifications,
} from '/static/js/common/functions.prod.js';
import {
  showErrorMessage,
  showSuccessMessage,
} from '/static/js/common/notification.prod.js';

document.addEventListener('DOMContentLoaded', function () {
  NProgress.done();
  let csrftoken = $('[name="csrftoken"]')[0].content;

  $(document).on('htmx:afterSwap', function () {
    checkInput();
    NProgress.done();
  });

  window.addEventListener('popstate', () => {
    NProgress.start();
    setTimeout(() => {
      NProgress.done();
    }, 1000);
  });

  const params = new URLSearchParams(window.location.search);

  let view = params.get('view_page');
  if (view) {
    NProgress.start();
    // $.ajax({
    //   type: 'GET',
    //   url: `?page=${view}`,
    //   success: function (response) {
    //     $('.mainContent').empty().append(response);
    //     NProgress.done();
    //   },
    // });

    htmx.ajax('GET', `?page=${view}`, {
      target: '.mainContent',
      swap: 'replace',
    });
  }

  document.body.addEventListener('htmx:responseError', function (event) {
    handleHttpError(event.detail.xhr.status);
  });

  $('body').on('click', '#notifications.checkbox', async function () {
    let checked = $(this).prop('checked');
    if (checked) {
      await enableNotifications();
    } else {
      showErrorMessage(
        gettext('Notifications Silenced'),
        gettext('You will not receive notifications')
      );
      unsubscribeNotifications();
    }
  });

  $('body').on('click', '#email.checkbox', function () {});

  $('body').on('click', 'button', function () {
    let $input = $('.inputHolder').find('input');
    if ($input.length == 1) {
      let inputId = $input.attr('id');
      let value = $input.val().trim();
      let editName = $input.data('edit-name');
      if (value.length == 0) {
        showErrorMessage(
          gettext('Empty Field'),
          gettext('Kindly Fill in the Blank Space')
        );
        return;
      }

      if (editName && editName.length) {
        $.ajax({
          type: 'POST',
          headers: {
            'X-CSRFToken': csrftoken,
          },
          url: '?action=edit_personal_info',
          data: JSON.stringify({
            editName: inputId,
            editValue: value,
          }),
          success: function (response) {
            if (response.status) {
              const message = interpolate(
                gettext('You have updated your %(editName)s'),
                { ediName: editName },
                true
              );
              showSuccessMessage(gettext('Details Changed'), message);
              return;
            }
            showErrorMessage(
              gettext('Details Not Changed'),
              gettext('An error occurred try again.')
            );
          },
        });
      }

      if (inputId == 'login_password') {
        $.ajax({
          type: 'POST',
          url: '?action=confirm_password',
          headers: {
            'X-CSRFToken': csrftoken,
          },
          data: JSON.stringify({
            password: value,
          }),
          success: function (response) {
            if (response.status) {
              showSuccessMessage(
                gettext('Password Confirmed'),
                gettext('Enter your new password to change it.')
              );
              $('.mainContent').empty().append(response.html);
              return;
            } else {
              if (response.logout) {
                showErrorMessage(
                  gettext('Logging you out'),
                  gettext('Too many password attempts.')
                );
                NProgress.start();
                $('button').prop('disabled', true);
                setTimeout(() => {
                  window.location.reload();
                }, 2000);
              } else {
                showErrorMessage(
                  gettext('Password Failed'),
                  gettext('You will be logged out after 3 incorrect attempts.')
                );
              }
            }
          },
        });
      }
    } else if ($input.length == 2) {
      let $password = $input.first();
      let $reppassword = $input.last();
      if ($password.val().trim() == $reppassword.val().trim()) {
        $.ajax({
          type: 'POST',
          headers: {
            'X-CSRFToken': csrftoken,
          },
          url: '?action=change_password&verification=True',
          data: JSON.stringify({
            password: $password.val().trim(),
          }),
          success: function (response) {
            if (response.status) {
              showSuccessMessage(
                gettext('Password Changed'),
                gettext('Kindly log in with your new password')
              ).done(function () {
                window.location.reload();
              });
            } else {
              showErrorMessage();
            }
          },
        });
      }
    }
  });
  let confirmation = false;
  $('main').on('click', '.logout_content_button', function () {
    if (!confirmation) {
      showErrorMessage(
        gettext('Are you sure?'),
        gettext('Kindly click Logout again to confirm')
      );
      confirmation = true;
    } else {
      $.ajax({
        type: 'POST',
        headers: {
          'X-CSRFToken': csrftoken,
        },
        url: '?action=logout',
        success: function (response) {
          if (response.status) {
            showSuccessMessage('Logged Out', 'Refreshing your page');
            setTimeout(() => {
              window.location.reload();
            }, 2000);
          } else {
            showErrorMessage('Could Not Log Out', 'Kindly Try again.');
          }
        },
      });
    }
  });

  $('main').on('click', '#join_smst_pro_button', function () {
    $.ajax({
      type: 'GET',
      url: '?action=init_paystack',
      success: function (response) {
        let accessCode = response.response.data.access_code;
        const popup = new PaystackPop();
        popup.resumeTransaction(accessCode);
      },
    });
  });

  $('main').on('click', '#cancel_join_smst_pro', function () {
    history.back();
  });
});
