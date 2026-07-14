self.addEventListener('push', function(event) {
    if (event.data) {
        let payload = {};
        try {
            payload = event.data.json();
        } catch(e) {
            payload = { title: 'Antigravity', body: event.data.text() };
        }
        
        const promiseChain = self.registration.showNotification(payload.title, {
            body: payload.body,
            icon: '/favicon.ico',
            vibrate: [200, 100, 200],
            requireInteraction: false
        });

        event.waitUntil(promiseChain);
    }
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();

    event.waitUntil(
        clients.matchAll({ type: 'window' }).then(windowClients => {
            for (let i = 0; i < windowClients.length; i++) {
                const client = windowClients[i];
                if (client.url.includes('/') && 'focus' in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow('/');
            }
        })
    );
});

self.addEventListener('message', function(event) {
    if (event.data === 'clear_notifications') {
        event.waitUntil(
            self.registration.getNotifications().then(function(notifications) {
                notifications.forEach(function(notification) {
                    notification.close();
                });
            })
        );
    }
});

self.addEventListener('install', function(event) {
    self.skipWaiting();
});

self.addEventListener('activate', function(event) {
    event.waitUntil(clients.claim());
});
