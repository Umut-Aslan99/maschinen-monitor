// Service worker for Web Push only ("alarms on your phone"); the dashboard itself needs the live connection.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : {};
  event.waitUntil(self.registration.showNotification(data.title || 'Maschinen-Monitor', {
    body: data.body || '', icon: '/icons/icon-192.png', tag: 'alarm', renotify: true, data: { url: data.url || '/alarme' },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = event.notification.data && event.notification.data.url ? event.notification.data.url : '/';
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
    for (const client of list) if ('focus' in client) { client.navigate(url); return client.focus(); }
    return self.clients.openWindow(url);
  }));
});
