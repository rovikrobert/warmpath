import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Spinner from "../components/ui/Spinner";
import { introReview } from "../api/client";
import useDocumentTitle from "../hooks/useDocumentTitle";

export default function IntroReview() {
  const { token } = useParams();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useDocumentTitle("Introduction | WarmPath");

  useEffect(() => {
    if (!token) {
      setError(true);
      setLoading(false);
      return;
    }
    introReview
      .get(token)
      .then((res) => setData(res.data))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [token]);

  return (
    <div className="min-h-screen bg-background">
      {/* Minimal nav bar — same as Join page */}
      <header className="border-b border-border bg-card">
        <nav
          className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3 sm:px-6"
          role="navigation"
          aria-label="Intro review navigation"
        >
          <Link
            to="/"
            className="flex items-center gap-2 text-xl font-bold text-foreground"
            aria-label="WarmPath home"
          >
            <span className="text-primary">~</span>
            <span>WarmPath</span>
          </Link>
          <Link
            to="/#sign-up"
            className="rounded-lg bg-primary px-4 py-1.5 text-sm font-medium text-white hover:bg-primary/90"
          >
            Sign up free
          </Link>
        </nav>
      </header>

      <main
        className="mx-auto max-w-xl px-4 py-16 sm:px-6"
        role="main"
        aria-label="Introduction details"
      >
        {/* Loading state */}
        {loading && (
          <div className="flex justify-center py-20">
            <Spinner size="lg" />
          </div>
        )}

        {/* Error state */}
        {!loading && error && (
          <section className="rounded-xl border border-border bg-card p-8 text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-muted">
              <svg
                className="h-6 w-6 text-muted-foreground"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth="1.5"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z"
                />
              </svg>
            </div>
            <h1 className="mb-2 text-lg font-semibold text-foreground">
              Introduction unavailable
            </h1>
            <p className="mb-6 text-sm text-muted-foreground">
              This introduction has expired or is no longer available.
            </p>
            <Link
              to="/join?intent=seeker"
              className="inline-block rounded-lg bg-primary px-5 py-2 text-sm font-medium text-white hover:bg-primary/90"
            >
              Join WarmPath
            </Link>
          </section>
        )}

        {/* Success state */}
        {!loading && !error && data && (
          <section className="rounded-xl border border-border bg-card p-8">
            {/* Intro card */}
            <div className="mb-6 text-center">
              <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
                <svg
                  className="h-7 w-7 text-primary"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth="1.5"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z"
                  />
                </svg>
              </div>
              <h1 className="text-xl font-bold text-foreground">
                {data.job_seeker_first_name}
                {data.job_seeker_headline
                  ? `, ${data.job_seeker_headline}`
                  : ""}
              </h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Introduced by {data.introducer_first_name}
                {data.target_company
                  ? ` for a role at ${data.target_company}`
                  : ""}
              </p>
            </div>

            {/* Sent date */}
            {data.sent_at && (
              <p className="mb-6 text-center text-xs text-muted-foreground">
                This introduction was sent on{" "}
                {new Date(data.sent_at).toLocaleDateString("en-US", {
                  year: "numeric",
                  month: "long",
                  day: "numeric",
                })}
              </p>
            )}

            {/* Divider */}
            <div className="mb-6 border-t border-border" />

            {/* CTAs */}
            <div className="space-y-3">
              <p className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary/10 border border-primary/30 px-5 py-2.5 text-sm font-medium text-primary">
                <svg
                  className="h-4 w-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth="1.5"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75"
                  />
                </svg>
                Check your inbox and reply
              </p>
              <Link
                to="/join?intent=network"
                className="flex w-full items-center justify-center rounded-lg border border-border px-5 py-2.5 text-sm font-medium text-secondary-foreground hover:border-border hover:text-foreground"
              >
                Join WarmPath
              </Link>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
