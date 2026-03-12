/**
 * Web Vitals collection — sends LCP, INP, CLS metrics to PostHog.
 *
 * Initialized once at app startup. Metrics are sent as PostHog events
 * with the metric name, value, and rating (good/needs-improvement/poor).
 */
import { onLCP, onINP, onCLS, type Metric } from 'web-vitals';
import { trackEvent } from './analytics';

function sendMetric(metric: Metric) {
  trackEvent('web_vital', {
    metric_name: metric.name,
    metric_value: Math.round(metric.value),
    metric_rating: metric.rating,
    metric_delta: Math.round(metric.delta),
    metric_id: metric.id,
    navigation_type: metric.navigationType,
  });
}

export function initWebVitals() {
  onLCP(sendMetric);
  onINP(sendMetric);
  onCLS(sendMetric);
}
