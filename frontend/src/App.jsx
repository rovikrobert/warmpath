import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import Layout from './components/Layout';
import Spinner from './components/ui/Spinner';
import AuthPage from './pages/AuthPage';
import Dashboard from './pages/Dashboard';
import SearchResults from './pages/SearchResults';
import EditProfile from './pages/EditProfile';
import OnboardingPage from './pages/OnboardingPage';
import FindReferrals from './pages/FindReferrals';
import ReferralResults from './pages/ReferralResults';
import MarketplaceDashboard from './pages/MarketplaceDashboard';
import MyRequests from './pages/MyRequests';
import CreditsPage from './pages/CreditsPage';
import SharingSettings from './pages/SharingSettings';
import ApplicationsPage from './pages/ApplicationsPage';
import ContactsPage from './pages/ContactsPage';
import PrivacyPage from './pages/PrivacyPage';
import ReferralCodesPage from './pages/ReferralCodesPage';
import PrivacySettingsPage from './pages/PrivacySettingsPage';
import SettingsPage from './pages/SettingsPage';
import ScoreGlossary from './pages/ScoreGlossary';
import VerifyEmailPage from './pages/VerifyEmailPage';
import ForgotPasswordPage from './pages/ForgotPasswordPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import LinkedInCallback from './pages/LinkedInCallback';

function ProtectedRoute({ children }) {
  const { token, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950">
        <Spinner size="lg" />
      </div>
    );
  }
  return token ? children : <Navigate to="/" replace />;
}

function RootRedirect() {
  const { token, justSignedUp } = useAuth();
  if (!token) return <AuthPage />;
  if (justSignedUp) return <Navigate to="/onboarding" replace />;
  return <Navigate to="/dashboard" replace />;
}

export default function App() {
  const { loading } = useAuth();

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route path="/auth/linkedin/callback" element={<LinkedInCallback />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/privacy" element={<PrivacyPage />} />
      <Route path="/onboarding" element={<ProtectedRoute><OnboardingPage /></ProtectedRoute>} />
      <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/contacts" element={<ContactsPage />} />
        <Route path="/search/new" element={<FindReferrals />} />
        <Route path="/search/:id" element={<SearchResults />} />
        <Route path="/referrals" element={<FindReferrals />} />
        <Route path="/referrals/:id" element={<ReferralResults />} />
        <Route path="/applications" element={<ApplicationsPage />} />
        <Route path="/marketplace/dashboard" element={<MarketplaceDashboard />} />
        <Route path="/marketplace/requests" element={<MyRequests />} />
        <Route path="/credits" element={<CreditsPage />} />
        <Route path="/invite" element={<ReferralCodesPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/help/scores" element={<ScoreGlossary />} />
        {/* Legacy routes — redirect to unified settings */}
        <Route path="/profile/edit" element={<Navigate to="/settings?tab=profile" replace />} />
        <Route path="/settings/privacy" element={<Navigate to="/settings?tab=privacy" replace />} />
        <Route path="/marketplace/settings" element={<Navigate to="/settings?tab=sharing" replace />} />
        <Route path="/marketplace" element={<Navigate to="/marketplace/dashboard" replace />} />
        <Route path="/my-requests" element={<Navigate to="/marketplace/requests" replace />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
