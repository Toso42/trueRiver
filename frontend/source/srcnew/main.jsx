import React from 'react';
import ReactDOM from 'react-dom/client';
import AppRoot from './app/AppRoot';
import './styles.css';

const notifyAndroidBridge = (method, payload) => {
  try {
    const bridge = window.AndroidBridge;
    if (!bridge || typeof bridge[method] !== 'function') {
      return;
    }
    if (typeof payload === 'undefined') {
      bridge[method]();
      return;
    }
    bridge[method](String(payload));
  } catch (_) {}
};

window.addEventListener('error', (event) => {
  notifyAndroidBridge('onAppError', event?.message || 'window error');
});

window.addEventListener('unhandledrejection', (event) => {
  const reason = event?.reason;
  notifyAndroidBridge(
    'onAppError',
    typeof reason === 'string' ? reason : reason?.message || 'unhandled rejection',
  );
});

const cleanupStaleServiceWorkers = () => {
  if (!('serviceWorker' in navigator)) {
    return Promise.resolve(false);
  }

  const serviceWorkerReloadKey = 'triver.serviceWorkerCleanupReloaded';
  const reloadOnceIfStillControlled = () => {
    if (!navigator.serviceWorker.controller) {
      window.sessionStorage.removeItem(serviceWorkerReloadKey);
      return false;
    }
    if (window.sessionStorage.getItem(serviceWorkerReloadKey)) {
      return false;
    }
    window.sessionStorage.setItem(serviceWorkerReloadKey, '1');
    window.location.reload();
    return true;
  };

  const clearCaches = 'caches' in window
    ? window.caches.keys().then((keys) => Promise.all(keys.map((key) => window.caches.delete(key))))
    : Promise.resolve();
  const unregisterWorkers = navigator.serviceWorker.getRegistrations().then((registrations) => (
    Promise.all(registrations.map((registration) => registration.unregister().catch(() => false)))
  ));

  return Promise.all([clearCaches, unregisterWorkers])
    .then(reloadOnceIfStillControlled)
    .catch(() => false);
};

cleanupStaleServiceWorkers().then((reloadStarted) => {
  if (reloadStarted) {
    return;
  }

  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <AppRoot />
    </React.StrictMode>,
  );

  window.requestAnimationFrame(() => {
    notifyAndroidBridge('onAppReady');
  });
});
