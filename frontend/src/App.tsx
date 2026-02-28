import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { SignedIn, SignedOut, RedirectToSignIn } from '@clerk/clerk-react';
import { useAuth } from './context/AuthContext';
import ErrorBoundary from './components/ErrorBoundary';
import Layout from './components/Layout';
import Spinner from './components/ui/Spinner';

const AuthPage = lazy(() => import('./pages/AuthPage'));
const CoachPage = lazy(() => import('./pages/CoachPage'));
const SearchResults = lazy(() => import('./pages/SearchResults'));
const OnboardingPage = lazy(() => import('./pages/OnboardingPage'));
const FindReferrals = lazy(() => import('./pages/FindReferrals'));
const ReferralResults = lazy(() => import('./pages/ReferralResults'));
const MarketplaceOverview = lazy(() => import('./pages/MarketplaceOverview'));
const MyRequests = lazy(() => import('./pages/MyRequests'));
const CreditsPage = lazy(() => import('./pages/CreditsPage'));
const SharingSettings = lazy(() => import('./pages/SharingSettings'));
const ApplicationsPage = lazy(() => import('./pages/ApplicationsPage'));
const ContactsPage = lazy(() => import('./pages/ContactsPage'));
const PrivacyPage = lazy(() => import('./pages/PrivacyPage'));
const ReferralCodesPage = lazy(() => import('./pages/ReferralCodesPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const ScoreGlossary = lazy(() => import('./pages/ScoreGlossary'));
const Join = lazy(() => import('./pages/Join'));
const IntroReview = lazy(() => import('./pages/IntroReview'));

interface ProtectedRouteProps {
  children: React.ReactNode;
  allowIncomplete?: boolean;
}

function ProtectedRoute({ children, allowIncomplete = false }: ProtectedRouteProps) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <Spinner size="lg" />
      </div>
    );
  }
  return (
    <>
      <SignedIn>
        {!allowIncomplete && user && !user.onboarding_complete ? (
          <Navigate to="/onboarding" replace />
        ) : (
          children
        )}
      </SignedIn>
      <SignedOut><RedirectToSignIn /></SignedOut>
    </>
  );
}

function RootRedirect() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <Spinner size="lg" />
      </div>
    );
  }
  return (
    <>
      <SignedIn>
        <Navigate to={!user?.onboarding_complete ? '/onboarding' : user?.intent === 'share_network' ? '/contacts' : '/coach'} replace />
      </SignedIn>
      <SignedOut><AuthPage /></SignedOut>
    </>
  );
}

export default function App() {
  const { loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <Spinner size="lg" />
      </div>
    );
  }

  const fallback = (
    <div className="flex h-screen items-center justify-center bg-background">
      <Spinner size="lg" />
    </div>
  );

  return (
    <ErrorBoundary resetKey={location.pathname}>
      <Suspense fallback={fallback}>
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/privacy" element={<PrivacyPage />} />
          <Route path="/join" element={<Join />} />
          <Route path="/intro/:token" element={<IntroReview />} />
          <Route path="/onboarding" element={<ProtectedRoute allowIncomplete><OnboardingPage /></ProtectedRoute>} />
          <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
            <Route path="/coach" element={<CoachPage />} />
            <Route path="/contacts" element={<ContactsPage />} />
            <Route path="/search/new" element={<FindReferrals />} />
            <Route path="/search/:id" element={<SearchResults />} />
            <Route path="/referrals" element={<FindReferrals />} />
            <Route path="/referrals/:id" element={<ReferralResults />} />
            <Route path="/applications" element={<ApplicationsPage />} />
            <Route path="/marketplace" element={<MarketplaceOverview />} />
            <Route path="/marketplace/browse" element={<Navigate to="/referrals" replace />} />
            <Route path="/marketplace/requests" element={<MyRequests />} />
            <Route path="/credits" element={<CreditsPage />} />
            <Route path="/invite" element={<ReferralCodesPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/help/scores" element={<ScoreGlossary />} />
            {/* Legacy routes — redirect to unified settings */}
            <Route path="/dashboard" element={<Navigate to="/coach" replace />} />
            <Route path="/profile/edit" element={<Navigate to="/settings?tab=profile" replace />} />
            <Route path="/settings/privacy" element={<Navigate to="/settings?tab=privacy" replace />} />
            <Route path="/marketplace/settings" element={<Navigate to="/settings?tab=sharing" replace />} />
            <Route path="/marketplace/dashboard" element={<Navigate to="/marketplace" replace />} />
            <Route path="/my-requests" element={<Navigate to="/marketplace/requests" replace />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}
