import { updateCooldown } from '/static/js/common/functions.prod.js';

let notificationId = {
  success: 1,
  error: 1,
};
export function showSuccessMessage(title, content) {
  let deferred = $.Deferred();
  let id = notificationId['success'];
  let $notification =
    $(`<div class="notification success flex animate__animated animate__fadeInUp">
                <div class="notification-header-icon flex">
                    <svg width="30px" height="30px" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <g id="Interface / Check">
                    <path id="Vector" d="M6 12L10.2426 16.2426L18.727 7.75732" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </g>
                    </svg>
                </div>
                <div class="notification-content-holder">
                    <div class="notification-header">
                        <span id="notification-header-success-${id}"></span>
                    </div>
                    <div class="notification-content">
                        <span id="notification-content-success-${id}"></span>
                    </div>
                </div>
            </div>`);
  if ($('#notification-center').length) {
    $('.notification-center-holder').append($notification);
  } else {
    let $main = $(`<div id="notification-center" class="flex">
          </div>`);
    let $holder = $('<div class="notification-center-holder flex"></div>');

    $main.append($holder);
    $holder.append($notification);

    $('body').append($main);
  }
  $(`#notification-header-success-${id}`).text(title);
  $(`#notification-content-success-${id}`).text(content);

  $('.notification').one('animationend', function () {
    let $this = $(this);
    setTimeout(() => {
      $this
        .removeClass('animate__fadeInUp')
        .addClass('animate__fadeOutDown')
        .one('animationend', function () {
          $(this).remove();
          if (!$('.notification').length) {
            $('#notification-center').remove();
          }
          deferred.resolve();
        });
    }, 3000);
  });

  notificationId['success'] = ++id;
  return deferred.promise();
}

export function showErrorMessage(
  title = gettext('An Error Occurred'),
  content = gettext('Kindly Try Again Later')
) {
  let id = notificationId['error'];
  let $notification =
    $(`<div class="notification error flex animate__animated animate__fadeInUp">
                <div class="notification-header-icon flex">
                    <svg width="30px" height="30px" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M6.99486 7.00636C6.60433 7.39689 6.60433 8.03005 6.99486 8.42058L10.58 12.0057L6.99486 15.5909C6.60433 15.9814 6.60433 16.6146 6.99486 17.0051C7.38538 17.3956 8.01855 17.3956 8.40907 17.0051L11.9942 13.4199L15.5794 17.0051C15.9699 17.3956 16.6031 17.3956 16.9936 17.0051C17.3841 16.6146 17.3841 15.9814 16.9936 15.5909L13.4084 12.0057L16.9936 8.42059C17.3841 8.03007 17.3841 7.3969 16.9936 7.00638C16.603 6.61585 15.9699 6.61585 15.5794 7.00638L11.9942 10.5915L8.40907 7.00636C8.01855 6.61584 7.38538 6.61584 6.99486 7.00636Z" fill="#ffffff"/>
                    </svg>
                </div>
                <div class="notification-content-holder">
                    <div class="notification-header">
                        <span id="notification-header-error-${id}"></span>
                    </div>
                    <div class="notification-content">
                        <span id="notification-content-error-${id}"></span>
                    </div>
                </div>
            </div>`);
  if ($('#notification-center').length) {
    $('.notification-center-holder').append($notification);
  } else {
    let $main = $(`<div id="notification-center" class="flex">
          </div>`);
    let $holder = $('<div class="notification-center-holder flex"></div>');

    $main.append($holder);
    $holder.append($notification);

    $('body').append($main);
  }
  $(`#notification-header-error-${id}`).text(title);
  $(`#notification-content-error-${id}`).text(content);

  $('.notification').one('animationend', function () {
    let $this = $(this);
    setTimeout(() => {
      $this
        .removeClass('animate__fadeInUp')
        .addClass('animate__fadeOutDown')
        .one('animationend', function () {
          $(this).remove();
          if (!$('.notification').length) {
            $('#notification-center').remove();
          }
        });
    }, 3000);
  });

  notificationId['error'] = ++id;
}

export function showOutput(message, positive = false) {
  if (localStorage.getItem('login_cooldown_until')) {
    updateCooldown();
    return;
  }
  let $feedback = $('input:focus')
    .parent()
    .find('.feedback-icon')
    .addClass('loading')
    .removeClass('positive negative');
  if (!positive) {
    $('#formButton, button').prop('disabled', true);
  } else {
    $('#formButton, button').prop('disabled', false);
  }
  let $outputHolder = $('.formOutput');

  $outputHolder.empty();
  let messageClass = positive ? 'positive-msg' : 'negative-msg';
  if (messageClass == 'negative-msg') {
    $feedback.removeClass('loading positive').addClass('negative');
  } else {
    $feedback.removeClass('loading negative').addClass('positive');
  }
  let $output = $(
    `<div class="output ${messageClass} animate__animated animate__fadeInUp"></div>`
  );
  let $outputMessage = $(`<span>${message}</span>`);
  $output.append($outputMessage);
  $outputHolder.append($output);
}

export function clearOutput() {
  if (localStorage.getItem('login_cooldown_until')) {
    updateCooldown();
    return;
  }
  let $outputHolder = $('.formOutput');
  let $feedback = $('input:focus').parent().find('.feedback-icon');
  $outputHolder.empty();
  $feedback.removeClass('loading negative').addClass('positive');
  $('#formButton, button').prop('disabled', false);
}

export function unreadNotifications() {
  $.ajax({
    type: 'GET',
    url: '/?action=any_unread_notifications',
    success: function (response) {
      if (response.status) {
        let $notDot = $('<div class="notificationDot"></div>');
        $('.messageIconHolder').append($notDot);
      }
    },
  });
}
