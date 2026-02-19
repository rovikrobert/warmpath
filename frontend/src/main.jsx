import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ClerkProvider } from '@clerk/clerk-react';
import posthog from 'posthog-js';
import { AuthProvider } from './context/AuthContext';
import { ToastProvider } from './components/ui/Toast';
import App from './App.jsx';
import './index.css';

const CLERK_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

// Initialize PostHog (no-op when VITE_POSTHOG_KEY is not set)
const POSTHOG_KEY = import.meta.env.VITE_POSTHOG_KEY;
const POSTHOG_HOST = import.meta.env.VITE_POSTHOG_HOST || 'https://app.posthog.com';

if (POSTHOG_KEY) {
  posthog.init(POSTHOG_KEY, {
    api_host: POSTHOG_HOST,
    autocapture: true,
    captu[RESEND_KEY_REDACTED]: true,
    captu[RESEND_KEY_REDACTED]: true,
  });
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <ClerkProvider publishableKey={CLERK_KEY}>
        <ToastProvider>
          <AuthProvider>
            <App />
          </AuthProvider>
        </ToastProvider>
      </ClerkProvider>
    </BrowserRouter>
  </StrictMode>,
);
