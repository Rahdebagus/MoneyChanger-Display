import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

// The service worker exists so a TV can reload while offline and still boot.
// Registered only in a production build: during development it would serve a
// stale shell and hide the changes being worked on.
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // Offline reload will not work, but everything else still does.
    });
  });
}
