import {
  showSuccessMessage,
  unreadNotifications,
} from '/static/js/common/notification.prod.js';
import {
  storeNotifications,
  renderNotifications,
} from '/static/js/common/functions.prod.js';
document.addEventListener('DOMContentLoaded', function () {
  let websocket = new WebSocket(
    'wss://' + window.location.host + '/ws/smst_app/'
  );
  let access = localStorage.getItem('access') || null;
  websocket.onopen = function () {};

  websocket.onmessage = function (response) {
    const data = JSON.parse(response.data);
    if (data.type == 'smst_notification') {
      showSuccessMessage(data.content.content_title, data.content.content_text);
    }

    $('#appFormHolder')
      .removeClass('animate__fadeInUp')
      .addClass('animate__fadeOutUp')
      .one('animationend', function () {
        $(this).parent().remove();
      });
    unreadNotifications();

    $.ajax({
      type: 'GET',
      url: 'https://cloud.smartstock.africa/notifications/',
      headers: {
        Authorization: `Bearer ${access}`,
      },
      success: function (response) {
        storeNotifications(response.results);
        renderNotifications(response.results);
      },
    });
  };
});
