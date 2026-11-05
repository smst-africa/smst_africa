import {
  showErrorMessage,
  showSuccessMessage,
} from '/static/js/common/notification.prod.js';

export function debounce(func, delay = 500) {
  let timeout;

  return function (...args) {
    clearTimeout(timeout);

    timeout = setTimeout(() => {
      func.apply(this, args);
    }, delay);
  };
}

export function checkEmail(emailStr) {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(emailStr);
}

export function validatePassword(value) {
  if (value.length < 8) {
    return 'The password is too short.';
  }

  if (!/\d/.test(value)) {
    return 'Enter a number 0-9.';
  }

  if (!/[a-zA-Z]/.test(value)) {
    return 'Enter an alphabet letter A-Z.';
  }

  if (!/[^a-zA-Z0-9\s]/.test(value)) {
    return 'Enter a special character - !@#$%^&*(){}[],./';
  }

  return null;
}

export function parseDuration(duration) {
  const match = duration.match(
    /^P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/
  );

  if (!match) {
    return 0;
  }

  const days = Number(match[1] || 0);
  const hours = Number(match[2] || 0);
  const minutes = Number(match[3] || 0);
  const seconds = Number(match[4] || 0);

  return days * 86400 + hours * 3600 + minutes * 60 + seconds;
}

const COOLDOWN_KEY = 'login_cooldown_until';
let Timeout = null;
export function startCooldown(seconds) {
  const cooldownUntil = Date.now() + seconds * 1000;
  localStorage.setItem(COOLDOWN_KEY, cooldownUntil);
  clearTimeout(Timeout);
  updateCooldown();
}

export function updateCooldown() {
  clearTimeout(Timeout);
  const $button = $('#formButton');

  const cooldownUntil = Number(localStorage.getItem(COOLDOWN_KEY));

  if (!cooldownUntil) {
    $button.prop('disabled', false);
    return;
  }

  const remaining = Math.ceil((cooldownUntil - Date.now()) / 1000);

  if (remaining <= 0) {
    localStorage.removeItem(COOLDOWN_KEY);
    $button.prop('disabled', false);
    showSuccessMessage('Lockdown Lifted', 'Redirecting you');
    window.location.reload();
    return;
  }

  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;
  $button.prop('disabled', true);
  showErrorMessage(
    'Lockdown Initiated',
    `Try again after ${minutes} minute(s) and ${seconds} second(s)`
  );
  if (remaining < 60) {
    Timeout = setTimeout(updateCooldown, remaining * 1000);
  } else {
    Timeout = setTimeout(updateCooldown, 60000);
  }
}

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);

  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');

  const rawData = window.atob(base64);

  return Uint8Array.from([...rawData].map((char) => char.charCodeAt(0)));
}

export async function enableNotifications() {
  const VAPID_PUBLIC_KEY = $('#vapid_public_key').val();
  const permission = await Notification.requestPermission();
  let csrftoken = $('[name="csrftoken"]')[0].content;
  if (permission !== 'granted') {
    showErrorMessage(
      gettext('Notifications Denied'),
      gettext('Kindly allow Notifications.')
    );
    return;
  }

  showSuccessMessage(
    gettext('Notifications Accepted!'),
    gettext('Notifications have been allowed.')
  );

  const registration = await navigator.serviceWorker.ready;

  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
  });

  // We'll send this to Django next

  $.ajax({
    type: 'POST',
    url: '?action=activate_notifications',
    headers: {
      'X-CSRFToken': csrftoken,
    },
    data: JSON.stringify(subscription.toJSON()),
    success: function (response) {
      if (response.status) {
        showSuccessMessage(
          gettext('Notifications Registered'),
          gettext('You can now receive notifications.')
        );
      } else {
        showErrorMessage(
          gettext('Notifications Error'),
          gettext('Kindly Try again')
        );
      }
    },
  });
}

export async function unsubscribeNotifications() {
  const registration = await navigator.serviceWorker.ready;
  let csrftoken = $('[name="csrftoken"]')[0].content;

  const subscription = await registration.pushManager.getSubscription();

  if (subscription) {
    await subscription.unsubscribe();

    $.ajax({
      type: 'POST',
      url: '?action=silence_notifications',
      headers: {
        'X-CSRFToken': csrftoken,
      },
      data: JSON.stringify({ endpoint: subscription.endpoint }),
    });
  }
}

export function handleHttpError(status) {
  switch (status) {
    case 401:
      window.location.href = '/login/';
      break;

    case 403:
      showErrorMessage(
        gettext('Not Authenticated'),
        gettext('You do not have permission to do that.')
      );
      break;

    case 404:
      showErrorMessage(
        gettext('Not Found'),
        gettext('The requested resource was not found.')
      );
      break;

    case 500:
      showErrorMessage(
        gettext('An Error Occurred'),
        gettext('Server error. Please try again later.')
      );
      break;
  }
}

export function checkInput() {
  $('.switchInput').each(function () {
    let $this = $(this);
    if ($this.attr('id') == 'notificationInput') {
      let endpoint = $(this).data('endpoint');
      $.ajax({
        type: 'GET',
        url: `?action=check_notifications&endpoint=${endpoint}`,
        success: function (response) {
          if (response.status) {
            $this.find('input[type="checkbox"]').prop('checked', true);
          }
        },
      });
    } else if ($this.attr('id') == 'emailNewsletter') {
      $.ajax({
        type: 'GET',
        url: '?action=check_newsletter_subscription',
        success: function (response) {
          if (response.status) {
            $this.find('input[type="checkbox"]').prop('checked', true);
          }
        },
      });
    }
  });
}

export function subscribeNewsletter() {
  let csrftoken = $('[name="csrftoken"]')[0].content;
  $.ajax({
    type: 'POST',
    headers: {
      'X-CSRFToken': csrftoken,
    },
    url: '?action=subscribe_newsletter',
    success: function (response) {
      if (response.status) {
        showSuccessMessage(
          'NewsLetter Subscription',
          'You have subscribed to Smst Newsletter.'
        );
      } else {
        showErrorMessage('Error Occurred', 'Kindly Try Again');
      }
    },
  });
}

export function saveImage() {
  const $editedImage = $('#imageEditPreview');
  const croppedImage = $editedImage.cropper('getCroppedCanvas');
  croppedImage.toBlob(
    function (blob) {
      const url = URL.createObjectURL(blob);
      $('#imgPreview')[0].src = url;
      const croppedFile = new File([blob], 'product_image.jpg', {
        type: 'image/jpeg',
        lastModified: Date.now(),
      });
      const dt = new DataTransfer();
      dt.items.add(croppedFile);
      $('#imageInput')[0].files = dt.files;
    },
    'image/webp',
    0.9
  );
  fadeOutModal('.imageEdit', '.imageEditHolder');
  $('.imagePreviewHolder').addClass('animate__fadeIn');
}

export function fadeInModal(childElement, parentElement) {
  $(parentElement)
    .removeClass('animate__fadeOut')
    .addClass('animate__fadeIn')
    .one('animationend', function () {
      $(childElement)
        .removeClass('animate__fadeOutDown')
        .addClass('animate__fadeInUp');
      fadeOutLoader();
    });
}

export function fadeOutModal(childElement, parentElement) {
  $(childElement)
    .removeClass('animate__fadeInUp')
    .addClass('animate__fadeOutDown')
    .one('animationend', function () {
      $(parentElement)
        .removeClass('animate__fadeIn')
        .addClass('animate__fadeOut');
    });
}

export function loaderScreen(message) {
  let $loader = $(
    '<div class="smst_loader animate__animated animate__fadeIn"></div>'
  );
  let $childLoader = $('<div class="smst_loader_holder"></div>');
  let $badgeLogo = $('<div class="badge_logo"></div>');
  let $messageHolder = $(
    `<div class="loader_message"><span>${message}</span></div>`
  );

  $loader.append($childLoader.append($badgeLogo, $messageHolder));
  $('body').append($loader);
}

export function fadeOutLoader() {
  $('.smst_loader')
    .removeClass('animate__fadeIn')
    .addClass('animate__fadeOut')
    .one('animationend', function () {
      $(this).remove();
    });
}

const NOTIFICATIONS_STORAGE_KEY = 'smst_notifications';

export function getStoredNotifications() {
  const stored = localStorage.getItem(NOTIFICATIONS_STORAGE_KEY);
  if (!stored) {
    return [];
  }

  try {
    return JSON.parse(stored);
  } catch (e) {
    e;
    localStorage.removeItem(NOTIFICATIONS_STORAGE_KEY);
    return [];
  }
}

export function storeNotifications(notifications) {
  localStorage.setItem(
    NOTIFICATIONS_STORAGE_KEY,
    JSON.stringify(notifications)
  );
}

export function renderNotifications(results) {
  let notifications = [...results];
  if (!notifications.length) {
    notifications.push({
      id: 0,
      notificationId: 'empty_notification',
      notificationTitle: 'No Notifications',
      notificationContent: 'You have 0 notifications.',
      notificationRead: true,
    });
  }
  let $notificationFP = $(
    '<div class="app_notification_grand_parent animate__animated animate__fadeInTopRight"></div>'
  );
  let $notificationP = $('<div class="app_notification_parent"></div>');
  let $notificationHolder = $('<div class="app_notification_holder"></div>');
  let $notifications = notifications.map((not) => {
    let unreadClass = not.notificationRead ? '' : 'unread';
    let $notification = $(
      `<div class="app_notification ${unreadClass}" data-notification-id="${not.notificationId}"></div>`
    );
    let $notificationTitle = $('<div class="notification_title"></div>');
    $notificationTitle.append(`<span>${not.notificationTitle}</span>`);
    let $notificationContent = $('<div class="notification_content"></div>');
    $notificationContent.append(`<span>${not.notificationContent}</span>`);
    $notification.append($notificationTitle, $notificationContent);
    return $notification;
  });
  $('#mainContent').append(
    $notificationFP.append(
      $notificationP.append($notificationHolder.append($notifications))
    )
  );
}

export function parseImage(e) {
  const file = e.target.files[0];
  if (!file) {
    return;
  }

  const maxSize = 5 * 1024 * 1024;
  if (file.size > maxSize) {
    showErrorMessage(
      gettext('Image too big'),
      gettext('Kindly choose an image lower than 5MB')
    );
    this.value = '';

    return;
  }

  const allowedTypes = ['image/jpeg'];

  if (!allowedTypes.includes(file.type)) {
    showErrorMessage(
      gettext('Not an Image'),
      gettext('Only JPG and JPEG images are allowed!')
    );
    this.value = '';
    fadeOutLoader();
    return;
  }
  loaderScreen(gettext('Loading your Image'));

  const img = new Image();
  img.src = URL.createObjectURL(file);

  img.onload = function () {
    const maxWidth = 1280;
    const scale = maxWidth / img.width;
    const width = maxWidth;
    const height = img.height * scale;

    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    canvas.width = width;
    canvas.height = height;
    ctx.drawImage(img, 0, 0, width, height);
    canvas.toBlob(
      function (blob) {
        if (!blob) {
          showErrorMessage(
            gettext('Image Processing Failed'),
            gettext('Could not process image, kindly try again')
          );
          fadeOutLoader();

          return;
        }

        const $cropImage = $('#imageEditPreview');
        if ($cropImage[0].dataset.objectURL) {
          URL.revokeObjectURL($cropImage[0].dataset.objectURL);
        }
        const objectURL = URL.createObjectURL(blob);
        $cropImage[0].dataset.objectURL = objectURL;
        $cropImage[0].onload = function () {
          if ($cropImage.data('cropper')) {
            $cropImage.cropper('destroy');
          }

          $cropImage.cropper({
            aspectRatio: 1 / 1,
            viewMode: 3,
            minCanvasHeight: 100,
            autoCropArea: 1,
            zoomable: false,
            minCropBoxHeight: 100,
          });
        };
        $cropImage[0].src = objectURL;
        fadeInModal('.imageEdit', '.imageEditHolder');
      },
      'image/webp',
      0.9
    );
  };
}
export async function searchTable({
  input,
  storageKey,
  apiEndpoint,
  searchKeys,
  renderRow,
  table,
  threshold = 0,
  fallbackToAll = false,
}) {
  $(input).on(
    'input',
    debounce(async function (e) {
      $(e.target).closest('.field')[0].scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      });
      const value = e.target.value.trim().toLowerCase();

      let products;

      try {
        products = JSON.parse(localStorage.getItem(storageKey));
      } catch {
        products = null;
      }

      if (!Array.isArray(products)) {
        const response = await api(apiEndpoint);

        products = Array.isArray(response) ? response : response.results || [];

        localStorage.setItem(storageKey, JSON.stringify(products));
      }

      const fuse = new Fuse(products, {
        keys: searchKeys,
        threshold,
      });

      let results = value
        ? fuse.search(value).map((result) => result.item)
        : products;

      if (!results.length && fallbackToAll) {
        results = products;
      }

      const rows = results.map((item) => renderRow(item));

      $(table).find('tbody').empty().append(rows);
    })
  );

  $(input).on('blur', function () {
    localStorage.removeItem(storageKey);
  });
}

export function scrollLeftRight(app_container, nav_link_holder, nav_link) {
  let startX = 0;
  let startY = 0;
  $('main')
    .on('touchstart', app_container, function (e) {
      if (
        $(e.target).closest('table').length ||
        $(e.target).closest('.sheet').length
      ) {
        return;
      }
      const touch = e.originalEvent.changedTouches[0];
      startX = touch.clientX;
      startY = touch.clientY;
    })
    .on('touchend', app_container, async function (e) {
      if (
        $(e.target).closest('table').length ||
        $(e.target).closest('.sheet').length
      ) {
        return;
      }
      const navLinkElements = $('main').find(nav_link_holder);
      let totalIndex = navLinkElements.find(nav_link).length;

      const touch = e.originalEvent.changedTouches[0];

      const diffX = touch.clientX - startX;
      const diffY = touch.clientY - startY;

      // Ignore small movements and vertical swipes
      if (Math.abs(diffX) < 50 || Math.abs(diffX) < Math.abs(diffY)) {
        return;
      }

      const $links = navLinkElements.find(nav_link);
      const index = $links.index($links.filter('.is-active'));
      $links.removeClass('is-active');
      let modulo = index % totalIndex;
      let url;
      if (diffX < 0) {
        if (modulo == totalIndex - 1) {
          modulo = -1;
        }
        $(app_container).addClass('animate__animated animate__fadeOutLeft');
        url = $links
          .eq(modulo + 1)
          .addClass('is-active')
          .attr('href');
      } else {
        if (!modulo) {
          modulo = totalIndex;
        }
        $(app_container).addClass('animate__animated animate__fadeOutRight');

        url = $links
          .eq(modulo - 1)
          .addClass('is-active')
          .attr('href');
      }
      htmx.ajax('GET', url, {
        target: '#mainContent',
        swap: 'outerHTML',
        select: '#mainContent',
      });
    });
}
