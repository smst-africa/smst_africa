self.addEventListener('push', function (event) {
  let data = {};

  if (event.data) {
    data = event.data.json();
  }

  const title = data.title || 'My App';
  const options = {
    body: data.body || 'You have a new notification!',
    icon: data.icon || '/static/icons/icon-192x192.png',
    badge: data.badge || '/static/icons/badge-72x72.png',
    data: {
      url: data.url || '/',
    },
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();

  const url = event.notification.data?.url || '/';

  event.waitUntil(clients.openWindow(url));
});
