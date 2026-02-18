import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import posthog from 'posthog-js';
import { AuthProvider } from './context/AuthContext';
import App from './App.jsx';
import './index.css';

// Initialize PostHog (no-op when env vars are not set)
const phKey = import.meta.env.VITE_POSTHOG_KEY;
const phHost = import.meta.env.VITE_POSTHOG_HOST;
if (phKey && phHost) {
  posthog.init(phKey, {
    api_host: phHost,
    capture_pageview: true,
    capture_pageleave: true,
  });
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
