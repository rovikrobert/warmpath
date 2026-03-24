import { WarmPathIcon } from './WarmPathLogo';

export default function MissingClerkKey() {
  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-lg text-center">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
          <WarmPathIcon size={36} className="text-primary" />
        </div>

        <h1 className="text-2xl font-bold text-foreground">
          WarmPath
        </h1>
        <p className="mt-1 text-muted-foreground">
          Get referred to your dream job
        </p>

        <div className="mt-8 rounded-xl border border-border bg-card p-6 text-left">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-500/10">
              <svg className="h-4 w-4 text-amber-500" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
              </svg>
            </div>
            <div>
              <h2 className="font-semibold text-foreground">
                Clerk authentication not configured
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                The <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-mono text-foreground">VITE_CLERK_PUBLISHABLE_KEY</code> environment
                variable is missing. The frontend needs this to handle authentication.
              </p>
            </div>
          </div>

          <div className="mt-5 space-y-3">
            <h3 className="text-sm font-medium text-foreground">To fix this:</h3>
            <ol className="list-inside list-decimal space-y-2 text-sm text-muted-foreground">
              <li>
                Create a free Clerk account at{' '}
                <a
                  href="https://dashboard.clerk.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-primary underline decoration-primary/30 hover:decoration-primary"
                >
                  dashboard.clerk.com
                </a>
              </li>
              <li>
                Copy your <strong className="text-foreground">Publishable Key</strong> from the Clerk dashboard
              </li>
              <li>
                Add it to your <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-mono text-foreground">.env.dev</code> file:
                <pre className="mt-2 rounded-lg bg-muted/50 px-3 py-2 text-xs font-mono text-foreground">
                  VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
                </pre>
              </li>
              <li>Restart the frontend dev server</li>
            </ol>
          </div>
        </div>

        <div className="mt-6 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
          <a
            href={`${apiUrl}/health`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2.5 text-sm font-medium text-foreground hover:bg-muted transition-colors"
          >
            <svg className="h-4 w-4 text-emerald-500" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
            Check API Health
          </a>
          <a
            href="https://dashboard.clerk.com"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            Get Clerk Key
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
            </svg>
          </a>
        </div>

        <p className="mt-8 text-xs text-muted-foreground">
          Backend tests don't require Clerk keys — they use mock authentication.
          <br />
          Run <code className="rounded bg-muted px-1 py-0.5 text-xs font-mono">pytest -v</code> to verify the backend works.
        </p>
      </div>
    </div>
  );
}
