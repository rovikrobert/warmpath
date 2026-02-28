import posthog from 'posthog-js';

export function trackEvent(event: string, properties: Record<string, any> = {}) {
  if (posthog.__loaded) {
    posthog.capture(event, properties);
  }
}

export function identifyUser(userId: string, traits: Record<string, any> = {}) {
  if (posthog.__loaded) {
    posthog.identify(userId, traits);
  }
}

export function resetAnalytics() {
  if (posthog.__loaded) {
    posthog.reset();
  }
}
