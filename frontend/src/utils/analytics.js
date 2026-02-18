import posthog from 'posthog-js';

export function trackEvent(event, properties = {}) {
  if (posthog.__loaded) {
    posthog.capture(event, properties);
  }
}

export function identifyUser(userId, traits = {}) {
  if (posthog.__loaded) {
    posthog.identify(userId, traits);
  }
}

export function resetAnalytics() {
  if (posthog.__loaded) {
    posthog.reset();
  }
}
