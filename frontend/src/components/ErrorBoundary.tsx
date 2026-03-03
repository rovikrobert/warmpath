import { Component, ErrorInfo, ReactNode } from 'react';

function isChunkLoadError(error: Error): boolean {
  return (
    error?.name === 'ChunkLoadError' ||
    error?.message?.includes('Failed to fetch dynamically imported module') ||
    error?.message?.includes('Importing a module script failed') ||
    error?.message?.includes('error loading dynamically imported module')
  );
}

const RELOAD_KEY = 'chunk_reload_attempted';

interface ErrorBoundaryProps {
  children: ReactNode;
  resetKey?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

declare global {
  interface Window {
    posthog?: any;
  }
}

export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidUpdate(prevProps: ErrorBoundaryProps) {
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false, error: null });
    }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo);

    // Auto-reload on chunk load failures (stale deploy)
    if (isChunkLoadError(error)) {
      const lastReload = sessionStorage.getItem(RELOAD_KEY);
      const now = Date.now();
      // Only auto-reload if we haven't reloaded in the last 10 seconds
      if (!lastReload || now - Number(lastReload) > 10000) {
        sessionStorage.setItem(RELOAD_KEY, String(now));
        window.location.reload();
        return;
      }
    }

    // If PostHog is available, track the error
    try {
      const posthog = window.posthog;
      if (posthog?.__loaded) {
        posthog.capture('frontend_error', {
          error: error.message,
          stack: error.stack,
          componentStack: errorInfo.componentStack,
        });
      }
    } catch (_) {}
  }

  render() {
    if (this.state.hasError) {
      const isChunk = this.state.error && isChunkLoadError(this.state.error);
      return (
        <div className="flex min-h-[60vh] flex-col items-center justify-center px-4">
          <div className="mx-auto w-full max-w-md text-center">
            <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-red-500/10">
              <svg className="h-7 w-7 text-red-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-foreground">
              {isChunk ? 'Page failed to load' : 'Something went wrong'}
            </h2>
            <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
              {isChunk
                ? 'A newer version of WarmPath may have been deployed. Reloading should fix this.'
                : 'An unexpected error occurred. You can try reloading the page or navigating back.'}
            </p>

            {this.state.error?.message && !isChunk && (
              <details className="mt-4 rounded-lg border border-border bg-muted/30 text-left">
                <summary className="cursor-pointer px-4 py-2.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors">
                  Error details
                </summary>
                <pre className="max-h-32 overflow-auto border-t border-border px-4 py-3 text-xs font-mono text-muted-foreground">
                  {this.state.error.message}
                </pre>
              </details>
            )}

            <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:justify-center">
              <button
                onClick={() => {
                  this.setState({ hasError: false, error: null });
                  window.location.reload();
                }}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182" />
                </svg>
                Reload Page
              </button>
              <button
                onClick={() => {
                  this.setState({ hasError: false, error: null });
                  window.history.back();
                }}
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-card px-4 py-2.5 text-sm font-medium text-foreground hover:bg-muted transition-colors"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 15 3 9m0 0 6-6M3 9h12a6 6 0 0 1 0 12h-3" />
                </svg>
                Go Back
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
