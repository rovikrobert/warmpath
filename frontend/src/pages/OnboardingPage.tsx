import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { auth as authApi, contacts as contactsApi, preferences, marketplace, referrals as referralsApi } from '../api/client';
import TagInput from '../components/TagInput';
import KeevsAvatar from '../components/KeevsAvatar';
import TrebAvatar from '../components/TrebAvatar';
import KeevsTrivia from '../components/KeevsTrivia';
import MarketplaceVisibilityExplainer from '../components/MarketplaceVisibilityExplainer';
import { trackEvent } from '../utils/analytics';
import { SOURCES } from '../utils/sources';
import { KEEVS_TRIVIA, shuffleArray } from '../utils/keevs-trivia';
import Button from '../components/ui/Button';
import SourceTag from '../components/ui/SourceTag';
import Spinner from '../components/ui/Spinner';
import useDocumentTitle from '../hooks/useDocumentTitle';

function ResumePreviewModal({ data, onApply, onClose }) {
  if (!data) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="resume-preview-title">
      <div className="mx-4 w-full max-w-lg max-h-[80vh] overflow-y-auto rounded-xl bg-card border border-border p-6 shadow-xl">
        <h3 id="resume-preview-title" className="text-lg font-bold text-foreground">Resume Preview</h3>
        <p className="mt-1 text-sm text-muted-foreground">Review parsed data before applying.</p>
        <div className="mt-4 space-y-3 text-sm">
          {data.headline && <div><span className="font-medium text-secondary-foreground">Headline:</span> {data.headline}</div>}
          {data.current_title && <div><span className="font-medium text-secondary-foreground">Title:</span> {data.current_title}</div>}
          {data.current_company && <div><span className="font-medium text-secondary-foreground">Company:</span> {data.current_company}</div>}
          {data.industry && <div><span className="font-medium text-secondary-foreground">Industry:</span> {data.industry}</div>}
          {data.location && <div><span className="font-medium text-secondary-foreground">Location:</span> {data.location}</div>}
          {data.bio_summary && <div><span className="font-medium text-secondary-foreground">Summary:</span> {data.bio_summary}</div>}
          {data.work_history?.length > 0 && (
            <div>
              <span className="font-medium text-secondary-foreground">Work History:</span>
              <ul className="mt-1 space-y-1 pl-4">
                {data.work_history.map((w, i) => (
                  <li key={i} className="text-muted-foreground">
                    {w.title} at {w.company} ({w.start_date || '?'} - {w.end_date || 'Present'})
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div className="mt-5 flex gap-3">
          <Button variant="secondary" onClick={onClose} className="flex-1">
            Cancel
          </Button>
          <Button onClick={() => onApply(data)} className="flex-1">
            Apply
          </Button>
        </div>
      </div>
    </div>
  );
}

const EMPTY_WORK = { company: '', title: '', start_date: '', end_date: '', is_current: false };

const SENIORITY_OPTIONS = ['Staff / Principal', 'Manager', 'Director', 'VP', 'C-Suite'];
const CAREER_LEVEL_OPTIONS = ['Entry (0-2 yrs)', 'Mid (3-5 yrs)', 'Senior (6-10 yrs)', 'Staff / Principal (10+ yrs)', 'Manager', 'Director', 'VP+', 'C-Suite'];

// Steps: 1=Intent, 2=Job Prefs (skipped by NHs), 3=Bonus Pitch (NH/explore only),
// 4=Privacy (consolidated), 5=Meet Keevs, 6=Upload CSV, 7=Work History
const TOTAL_STEPS = 7;

// Privacy step data (rendered as compact rows in consolidated step 4)
const PRIVACY_STEPS = [
  {
    title: 'Your Data Stays Private',
    text: 'Everything you upload lives in your Private Vault \u2014 encrypted and visible only to you. Your full contact data is never shared with other users.',
    icon: (
      <svg className="h-10 w-10 text-primary" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
      </svg>
    ),
    bgColor: 'bg-primary/10',
    borderColor: 'border-primary/30',
  },
  {
    title: 'Contacts Are Protected',
    text: 'If you share contacts on the marketplace, only anonymized listing fields are shown (company, role level, department, strength). Names, emails, and LinkedIn profiles are never revealed without your explicit approval.',
    icon: (
      <svg className="h-10 w-10 text-success" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" />
      </svg>
    ),
    bgColor: 'bg-success/10',
    borderColor: 'border-success/30',
  },
  {
    title: "Your Employer Can't See You",
    text: 'Your job search activity is completely invisible. No employer \u2014 including yours \u2014 can discover you\'re looking for new opportunities.',
    icon: (
      <svg className="h-10 w-10 text-purple-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 0 0 1.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.451 10.451 0 0 1 12 4.5c4.756 0 8.773 3.162 10.065 7.498a10.522 10.522 0 0 1-4.293 5.774M6.228 6.228 3 3m3.228 3.228 3.65 3.65m7.894 7.894L21 21m-3.228-3.228-3.65-3.65m0 0a3 3 0 1 0-4.243-4.243m4.242 4.242L9.88 9.88" />
      </svg>
    ),
    bgColor: 'bg-purple-500/10',
    borderColor: 'border-purple-500/30',
  },
  {
    title: 'Anyone Can Opt Out',
    text: 'Any person can request removal from WarmPath at any time, even if they don\'t have an account. We maintain a permanent suppression list.',
    icon: (
      <svg className="h-10 w-10 text-info" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6a2.25 2.25 0 0 0-2.25 2.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15m3 0 3-3m0 0-3-3m3 3H9" />
      </svg>
    ),
    bgColor: 'bg-info/10',
    borderColor: 'border-info/30',
  },
  {
    title: 'How We Use AI',
    text: 'We use AI from Anthropic, Google, Groq, and OpenAI to coach you, draft intro messages, parse resumes, and normalise company names. Your contacts\' names and emails never leave our servers \u2014 only company names and job titles are processed by AI, and no provider retains or trains on your data.',
    icon: (
      <svg className="h-10 w-10 text-sky-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456Z" />
      </svg>
    ),
    bgColor: 'bg-sky-500/10',
    borderColor: 'border-sky-500/30',
  },
];

export default function OnboardingPage() {
  useDocumentTitle('Get Started');
  const { refreshUser, clerkUser } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);

  // Step 1: Intent — pre-select from /join landing page if available
  const [intent, setIntent] = useState(() => {
    const saved = localStorage.getItem('join_intent');
    if (saved) localStorage.removeItem('join_intent');
    return saved === 'seeker' ? 'find_referrals' : saved === 'network' ? 'sha[RESEND_KEY_REDACTED]' : '';
  });

  // Step 1: Referral code (captured early, redeemed on completion)
  // Seed from localStorage (set by /join landing page) if present
  const [referralCode, setReferralCode] = useState(
    () => localStorage.getItem('referral_code') || ''
  );
  const [referralExpanded, setReferralExpanded] = useState(
    () => !!localStorage.getItem('referral_code')
  );

  // Step 2: Job preferences (skipped by sha[RESEND_KEY_REDACTED])
  const [prefs, setPrefs] = useState({
    target_role: '',
    target_seniority: '',
    career_level: '',
    target_industries: [],
    target_locations: [],
    target_companies: [],
    key_skills: [],
    open_to_remote: true,
  });

  // Step 6: Upload
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [optInMarketplace, setOptInMarketplace] = useState(false);
  // Step 3 (NH): Current employer
  const [nhEmployer, setNhEmployer] = useState('');
  const [error, setError] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadProgressWidth, setUploadProgressWidth] = useState(0);
  const [uploadProgressMsg, setUploadProgressMsg] = useState('');

  // Keevs trivia rotation during upload
  const [triviaPool, setTriviaPool] = useState([]);
  const [triviaIdx, setTriviaIdx] = useState(-1); // -1 = greeting
  const [triviaFade, setTriviaFade] = useState(true);

  // Resume from last completed step on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [prefsRes, contactsRes, meRes] = await Promise.allSettled([
          preferences.getJob(),
          contactsApi.list({ per_page: 1 }),
          authApi.me(),
        ]);

        if (cancelled) return;

        const hasIntent = meRes.status === 'fulfilled' && meRes.value?.data?.intent;
        const userIntent = hasIntent ? meRes.value.data.intent : null;
        const hasPrefs = prefsRes.status === 'fulfilled' && prefsRes.value?.data?.target_role;
        const hasContacts = contactsRes.status === 'fulfilled' && (contactsRes.value?.data?.length > 0 || contactsRes.value?.meta?.total > 0);

        // Pre-fill intent from existing data
        if (hasIntent) setIntent(userIntent);

        // Jump to first incomplete step (intent is now step 1)
        if (!hasIntent) { setStep(1); return; }
        // sha[RESEND_KEY_REDACTED] skips job prefs; others need them
        if (userIntent !== 'sha[RESEND_KEY_REDACTED]' && !hasPrefs) { setStep(2); return; }
        // Steps 3-5 are informational — skip to data steps
        if (!hasContacts) { setStep(6); return; }
        // Work history is the last step
        setStep(7);
      } catch (err) {
        console.error('OnboardingPage: failed to determine onboarding step', err);
        // Default to step 1 on error
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const PHASE_LABELS = {
    parsing: 'Parsing contacts...',
    cleaning: 'Normalizing names and companies...',
    importing: 'Importing contacts...',
    scoring: 'Calculating warm scores...',
  };

  // Gentle ease-in animation for the first ~2s before real data arrives,
  // then switch to data-driven progress once polling provides numbers.
  useEffect(() => {
    if (!uploading) { setUploadProgressWidth(0); setUploadProgressMsg('Uploading file...'); return; }
    let frame;
    const start = Date.now();
    const tick = () => {
      const elapsed = (Date.now() - start) / 1000;
      // Only animate up to 15% — real data takes over after that
      if (elapsed < 2) {
        setUploadProgressWidth((prev) => Math.max(prev, elapsed * 7.5));
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [uploading]);

  // Keevs trivia rotation — greeting first, then shuffled trivia at 8s intervals
  useEffect(() => {
    if (!uploading) {
      setTriviaIdx(-1);
      setTriviaFade(true);
      return;
    }
    setTriviaPool(shuffleArray(KEEVS_TRIVIA));
    setTriviaIdx(-1);
    setTriviaFade(true);

    const interval = setInterval(() => {
      setTriviaFade(false);
      setTimeout(() => {
        setTriviaIdx((prev) => {
          const next = prev + 1;
          return next >= KEEVS_TRIVIA.length ? 0 : next;
        });
        setTriviaFade(true);
      }, 300);
    }, 8000);
    return () => clearInterval(interval);
  }, [uploading]);

  const currentTrivia = triviaIdx === -1
    ? { text: 'Hang tight — scoring your network takes a moment. Worth it.', source: null, isGreeting: true }
    : { ...triviaPool[triviaIdx], isGreeting: false };

  // Step 7: Work history + resume import
  const [workHistory, setWorkHistory] = useState([]);
  const [resumePreview, setResumePreview] = useState(null);
  const [resumeProfileData, setResumeProfileData] = useState(null);
  const [resumeImporting, setResumeImporting] = useState(false);
  const resumeInputRef = useRef(null);

  const handleResumeUpload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setResumeImporting(true);
    setError('');
    try {
      const res = await authApi.uploadResume(f);
      setResumePreview(res.data);
    } catch (err) {
      setError(err.message);
    } finally {
      setResumeImporting(false);
      if (resumeInputRef.current) resumeInputRef.current.value = '';
    }
  };

  const applyResumeData = (data) => {
    // Populate work history from parsed resume
    if (data.work_history?.length) {
      setWorkHistory(data.work_history.map((w) => ({
        company: w.company || '',
        title: w.title || '',
        start_date: w.start_date || '',
        end_date: w.end_date || '',
        is_current: !w.end_date,
      })));
    }
    // Store profile fields for saving alongside work history
    setResumeProfileData({
      headline: data.headline || null,
      current_company: data.current_company || null,
      current_title: data.current_title || null,
      industry: data.industry || null,
      location: data.location || null,
      bio_summary: data.bio_summary || null,
    });
    setResumePreview(null);
  };

  const setPref = (key) => (e) => setPrefs({ ...prefs, [key]: typeof e === 'object' && e.target ? e.target.value : e });
  const setArrayPref = (key) => (val) => setPrefs({ ...prefs, [key]: val });

  // Step 2 -> 3 (bonus pitch for explore) or 4 (privacy for find_referrals)
  const handlePrefs = async () => {
    const requiredRole = prefs.target_role.trim();
    if (!requiredRole) {
      setError('Target role is required to continue.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await preferences.upsertJob({
        target_role: requiredRole,
        target_seniority: prefs.target_seniority || null,
        career_level: prefs.career_level || null,
        target_industries: prefs.target_industries.length ? prefs.target_industries : null,
        target_locations: prefs.target_locations.length ? prefs.target_locations : null,
        target_companies: prefs.target_companies.length ? prefs.target_companies : null,
        key_skills: prefs.key_skills.length ? prefs.key_skills : null,
        open_to_remote: prefs.open_to_remote,
      });
      // find_referrals skips bonus pitch; explore sees it
      setStep(intent === 'find_referrals' ? 4 : 3);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // Step 1 -> 2 (job prefs for find_referrals/explore) or 3 (bonus pitch for sha[RESEND_KEY_REDACTED])
  const handleIntent = async () => {
    if (!intent) return;
    setSaving(true);
    setError('');
    try {
      await authApi.updateIntent(intent, clerkUser?.fullName);
      await refreshUser();
      // sha[RESEND_KEY_REDACTED] skips job prefs, goes straight to bonus pitch
      // find_referrals and explore need job prefs first
      setStep(intent === 'sha[RESEND_KEY_REDACTED]' ? 3 : 2);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // File handling
  const handleFile = (f) => {
    if (f && f.name.endsWith('.csv')) {
      setFile(f);
      setError('');
    } else {
      setError('Please select a .csv file');
    }
  };

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    handleFile(e.dataTransfer.files[0]);
  }, []);

  const pollUploadStatus = async (uploadId, onProgress) => {
    const maxAttempts = 540; // up to ~9 minutes (matches backend soft_time_limit)
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      try {
        const poll = await contactsApi.getUploadStatus(uploadId);
        const s = poll.data;
        if (onProgress) onProgress(s);
        if (s.status === 'completed') return s;
        if (s.status === 'failed') throw new Error(s.error_message || 'CSV processing failed');
      } catch (err) {
        if (err.message?.includes('failed')) throw err;
        // Network blip — keep polling
      }
    }
    throw new Error('Upload timed out — please refresh and try again');
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError('');
    try {
      const res = await contactsApi.upload(file);
      let result = res.data;

      // If async processing, poll until contacts are actually imported
      if (result.status === 'queued' || result.status === 'processing') {
        const final = await pollUploadStatus(result.id, (s) => {
          // Update progress bar from real backend data
          const phase = s.progress_phase;
          if (phase && PHASE_LABELS[phase]) {
            const label = phase === 'importing' && s.row_count && s.processed_count != null
              ? `Importing contacts... (${s.processed_count} of ${s.row_count})`
              : PHASE_LABELS[phase];
            setUploadProgressMsg(label);
          }
          // Compute percentage from processed_count / row_count
          if (s.row_count && s.row_count > 0) {
            const processed = s.processed_count || 0;
            // Reserve 0-15% for initial upload, 15-85% for importing, 85-95% for scoring
            let pct;
            if (phase === 'parsing' || phase === 'cleaning') {
              pct = 15 + Math.min((processed / s.row_count) * 5, 5);
            } else if (phase === 'importing') {
              pct = 20 + (processed / s.row_count) * 65;
            } else if (phase === 'scoring') {
              pct = 90;
            } else {
              pct = 15;
            }
            setUploadProgressWidth((prev) => Math.max(prev, Math.min(pct, 95)));
          } else if (phase) {
            // No row_count yet — show at least 15%
            setUploadProgressWidth((prev) => Math.max(prev, 15));
          }
        });
        if (final) {
          result = final;
        } else {
          // Poll timed out — check if contacts were actually created
          try {
            const check = await contactsApi.list({ page: 1, per_page: 1 });
            if (check.meta?.total > 0) {
              // Contacts exist — processing completed after timeout, let user proceed
              result = { processed_count: check.meta.total, status: 'completed' };
            } else {
              setError('Import is taking longer than expected. Please wait a moment and try again.');
              return;
            }
          } catch (err) {
            console.error('OnboardingPage: failed to check contacts after upload timeout', err);
            setError('Import is taking longer than expected. Please wait a moment and try again.');
            return;
          }
        }
      }

      setUploadResult(result);
      trackEvent('csv_uploaded', { contact_count: result?.processed_count ?? result?.row_count ?? 0 });
      // Always save sharing prefs for NH/both users so the checklist
      // can detect that onboarding sharing was completed.
      if (isHolder) {
        await marketplace.updateSharingPrefs({ opt_in_marketplace: optInMarketplace });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const postWizardRoute = intent === 'sha[RESEND_KEY_REDACTED]' ? '/contacts' : '/coach';

  const isHolder = intent === 'sha[RESEND_KEY_REDACTED]' || intent === 'explore';

  const inputClass = 'w-full rounded-lg border border-border bg-muted px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring';

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-12" role="main">
      <div className="w-full max-w-lg">
        {/* Logo */}
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-bold text-foreground">
            <span className="text-primary">~</span> WarmPath
          </h1>
        </div>

        {/* Progress — clickable segments to jump back */}
        <div className="mb-6 flex items-center gap-1" role="progressbar" aria-valuenow={step} aria-valuemin={1} aria-valuemax={TOTAL_STEPS} aria-label={`Onboarding step ${step} of ${TOTAL_STEPS}`}>
          {Array.from({ length: TOTAL_STEPS }, (_, i) => i + 1).map((s) => {
            // NHs skip step 2 (job prefs); job seekers skip step 3 (bonus pitch)
            if (s === 2 && intent === 'sha[RESEND_KEY_REDACTED]') return null;
            if (s === 3 && intent === 'find_referrals') return null;
            return (
              <button
                key={s}
                type="button"
                aria-label={`Go to step ${s}`}
                onClick={() => { if (s < step) { setError(''); setStep(s); } }}
                disabled={s >= step}
                className={`h-1.5 flex-1 rounded-full transition ${s <= step ? 'bg-primary' : 'bg-muted'} ${s < step ? 'cursor-pointer hover:bg-primary/90' : ''}`}
              />
            );
          })}
        </div>

        <div className="rounded-xl bg-card border border-border p-6 shadow-sm">
          {/* Step 1: Intent (first — determines which steps follow) */}
          {step === 1 && (
            <div className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-foreground">What brings you to WarmPath?</h2>
                <p className="mt-1 text-sm text-muted-foreground">You can change this anytime.</p>
              </div>

              <div className="space-y-3">
                {[
                  { value: 'find_referrals', title: 'I want to get referred to companies', desc: 'Search networks, find referral paths, and get introduced to people at your target companies.' },
                  { value: 'sha[RESEND_KEY_REDACTED]', title: 'I want to share my network and earn', desc: `Share your network anonymously. Your employer pays ${SOURCES.REFERRAL_BONUS_RANGE.claim} per referral hire \u2014 we send you pre-qualified candidates so you can capture those bonuses.` },
                  { value: 'explore', title: "Both \u2014 I'm exploring", desc: 'Search for referrals AND share your network. Most members choose this.' },
                ].map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setIntent(opt.value)}
                    className={`w-full rounded-lg border-2 p-4 text-left transition ${
                      intent === opt.value
                        ? 'border-primary bg-primary/10'
                        : 'border-border hover:border-border'
                    }`}
                  >
                    <p className="font-medium text-foreground">{opt.title}</p>
                    <p className="mt-1 text-sm text-muted-foreground">{opt.desc}</p>
                  </button>
                ))}
              </div>

              <div>
                {!referralExpanded ? (
                  <button
                    type="button"
                    onClick={() => setReferralExpanded(true)}
                    className="text-sm text-muted-foreground hover:text-primary transition"
                  >
                    Have a referral code?
                  </button>
                ) : (
                  <div className="space-y-1">
                    <label htmlFor="onboard-referral-code" className="mb-1 block text-sm font-medium text-secondary-foreground">Referral Code</label>
                    <input
                      id="onboard-referral-code"
                      type="text"
                      value={referralCode}
                      onChange={(e) => setReferralCode(e.target.value.trim())}
                      className={inputClass}
                      placeholder="e.g. WARM-ABC123"
                      maxLength={32}
                      autoFocus
                    />
                    <p className="text-xs text-muted-foreground">Optional — enter a code from a friend to earn bonus credits.</p>
                  </div>
                )}
              </div>

              {error && <p role="alert" aria-live="polite" className="rounded-md bg-destructive/10 p-2 text-sm text-destructive">{error}</p>}

              <div className="flex gap-3">
                <Button
                  onClick={handleIntent}
                  disabled={!intent}
                  loading={saving}
                  className="flex-1"
                  size="lg"
                >
                  Continue
                </Button>
              </div>
            </div>
          )}

          {/* Step 2: Job Preferences (skipped by sha[RESEND_KEY_REDACTED]) */}
          {step === 2 && (
            <div className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-foreground">What are you looking for?</h2>
                <p className="mt-1 text-sm text-muted-foreground">Help us find the best referral paths for you.</p>
              </div>

              <div>
                <label htmlFor="onboard-target-role" className="mb-1 block text-sm font-medium text-secondary-foreground">Target Role</label>
                <input id="onboard-target-role" type="text" value={prefs.target_role} onChange={setPref('target_role')} className={inputClass} placeholder="e.g. Software Engineer, Product Manager" />
              </div>

              <div>
                <label htmlFor="onboard-seniority" className="mb-1 block text-sm font-medium text-secondary-foreground">Seniority Level</label>
                <select id="onboard-seniority" value={prefs.target_seniority} onChange={setPref('target_seniority')} className={inputClass}>
                  <option value="">Select level</option>
                  {SENIORITY_OPTIONS.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="onboard-career-level" className="mb-1 block text-sm font-medium text-secondary-foreground">Career Level <span className="text-muted-foreground font-normal">(optional)</span></label>
                <select id="onboard-career-level" value={prefs.career_level} onChange={setPref('career_level')} className={inputClass}>
                  <option value="">Select your level</option>
                  {CAREER_LEVEL_OPTIONS.map((l) => (
                    <option key={l} value={l}>{l}</option>
                  ))}
                </select>
                <p className="mt-0.5 text-xs text-muted-foreground">Helps us match you with contacts at the right seniority.</p>
              </div>

              <TagInput
                label="Key Skills"
                value={prefs.key_skills}
                onChange={setArrayPref('key_skills')}
                placeholder="e.g. React, Python, Product Strategy"
                sublabel="Optional \u2014 improves match accuracy within departments."
              />

              <TagInput
                label="Dream Companies"
                value={prefs.target_companies}
                onChange={setArrayPref('target_companies')}
                placeholder="e.g. Stripe, Grab, Notion"
                sublabel="Optional \u2014 we'll alert you when contacts or jobs appear at these companies."
              />

              <TagInput
                label="Target Industries"
                value={prefs.target_industries}
                onChange={setArrayPref('target_industries')}
                placeholder="e.g. Fintech, SaaS, Healthcare"
              />

              <TagInput
                label="Preferred Locations"
                value={prefs.target_locations}
                onChange={setArrayPref('target_locations')}
                placeholder="e.g. Singapore, San Francisco, Remote"
              />

              <label className="flex items-center gap-2 text-sm text-secondary-foreground">
                <input
                  type="checkbox"
                  checked={prefs.open_to_remote}
                  onChange={(e) => setPrefs({ ...prefs, open_to_remote: e.target.checked })}
                  className="h-4 w-4 rounded border-border bg-muted text-primary focus:ring-ring"
                />
                Open to remote roles
              </label>

              {error && <p role="alert" aria-live="polite" className="rounded-md bg-destructive/10 p-2 text-sm text-destructive">{error}</p>}

              <div className="flex gap-3">
                <Button variant="secondary" onClick={() => { setError(''); setStep(1); }} className="flex-1" size="lg">
                  Back
                </Button>
                <Button onClick={handlePrefs} disabled={!prefs.target_role.trim()} loading={saving} className="flex-1" size="lg">
                  Continue
                </Button>
              </div>
            </div>
          )}

          {/* Step 3: Referral Bonus Pitch (NH / both only) */}
          {step === 3 && (
            <div className="space-y-5">
              <div className="text-center">
                <p className="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">Why share your network</p>
                <h2 className="text-lg font-semibold text-foreground">You're sitting on unclaimed referral bonuses</h2>
              </div>

              {intent === 'sha[RESEND_KEY_REDACTED]' && (
                <div>
                  <label htmlFor="onboard-nh-employer" className="mb-1 block text-sm font-medium text-secondary-foreground">Where do you work?</label>
                  <input id="onboard-nh-employer" type="text" value={nhEmployer} onChange={(e) => setNhEmployer(e.target.value)} className={inputClass} placeholder="e.g. Google, Grab, DBS" />
                  <p className="mt-0.5 text-xs text-muted-foreground">Helps us route relevant candidates to you.</p>
                </div>
              )}

              <div className="space-y-3">
                <div className="flex items-start gap-3 rounded-xl border border-success/30 bg-success/10 p-3 sm:p-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-success/10">
                    <svg className="h-5 w-5 text-success" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" aria-hidden="true">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                    </svg>
                  </div>
                  <div>
                    <p className="font-medium text-foreground">{SOURCES.REFERRAL_BONUS_RANGE.claim} per successful hire</p>
                    <p className="mt-0.5 text-sm text-muted-foreground">
                      Most employers pay referral bonuses when you help them hire. WarmPath sends you pre-qualified candidates so you can capture those bonuses.{' '}
                      <SourceTag source={SOURCES.REFERRAL_BONUS_RANGE.source} label={SOURCES.REFERRAL_BONUS_RANGE.label} />
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3 rounded-xl border border-primary/30 bg-primary/10 p-3 sm:p-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10">
                    <svg className="h-5 w-5 text-primary" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" aria-hidden="true">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M11.48 3.499a.562.562 0 0 1 1.04 0l2.125 5.111a.563.563 0 0 0 .475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 0 0-.182.557l1.285 5.385a.562.562 0 0 1-.84.61l-4.725-2.885a.562.562 0 0 0-.586 0L6.982 20.54a.562.562 0 0 1-.84-.61l1.285-5.386a.562.562 0 0 0-.182-.557l-4.204-3.602a.562.562 0 0 1 .321-.988l5.518-.442a.563.563 0 0 0 .475-.345L11.48 3.5Z" />
                    </svg>
                  </div>
                  <div>
                    <p className="font-medium text-foreground">Build your connector reputation</p>
                    <p className="mt-0.5 text-sm text-muted-foreground">Every successful intro builds your public connector score. Top connectors get priority visibility and early access to high-quality candidates.</p>
                  </div>
                </div>

                <div className="flex items-start gap-3 rounded-xl border border-purple-500/30 bg-purple-500/10 p-3 sm:p-4">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-purple-500/10">
                    <svg className="h-5 w-5 text-purple-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" aria-hidden="true">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" />
                    </svg>
                  </div>
                  <div>
                    <p className="font-medium text-foreground">You stay in control</p>
                    <p className="mt-0.5 text-sm text-muted-foreground">Only anonymized info is shown. You review every request and approve each intro personally. Nothing happens without your consent.</p>
                  </div>
                </div>
              </div>

              <div className="flex gap-3">
                <Button variant="secondary" onClick={() => { setError(''); setStep(intent === 'sha[RESEND_KEY_REDACTED]' ? 1 : 2); }} className="flex-1" size="lg">
                  Back
                </Button>
                <Button onClick={async () => {
                  if (nhEmployer.trim()) {
                    try { await authApi.upsertProfile({ current_company: nhEmployer.trim() }); } catch (err) { console.error('OnboardingPage: failed to save employer', err); }
                  }
                  setStep(4);
                }} className="flex-1" size="lg">
                  Next
                </Button>
              </div>
            </div>
          )}

          {/* Step 4: Privacy (consolidated) */}
          {step === 4 && (
            <div className="space-y-5">
              <div className="text-center">
                <p className="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">How we protect your data</p>
                <h2 className="text-lg font-semibold text-foreground">Your Data Journey</h2>
              </div>

              {/* Data flow summary */}
              <div className="flex flex-wrap items-center justify-center gap-x-1.5 gap-y-0.5 rounded-lg border border-border bg-muted/50 px-3 py-3 text-xs font-medium text-secondary-foreground sm:px-4">
                <span>CSV Upload</span>
                <span className="text-muted-foreground" aria-hidden="true">&rarr;</span>
                <span className="text-primary">Your Private Vault</span>
                <span className="text-muted-foreground" aria-hidden="true">&rarr;</span>
                <span className="text-success">Anonymized Marketplace</span>
                <span className="text-muted-foreground" aria-hidden="true">&rarr;</span>
                <span className="text-purple-400">You Review</span>
                <span className="text-muted-foreground" aria-hidden="true">&rarr;</span>
                <span className="text-info">You Approve</span>
              </div>

              {/* Privacy points — compact rows */}
              <div className="space-y-3">
                {PRIVACY_STEPS.map((ps) => (
                  <div key={ps.title} className={`flex items-start gap-3 rounded-xl border ${ps.borderColor} ${ps.bgColor} p-3 sm:p-4`}>
                    <div className="shrink-0 [&>svg]:h-6 [&>svg]:w-6">{ps.icon}</div>
                    <div>
                      <p className="text-sm font-medium text-foreground">{ps.title}</p>
                      <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{ps.text}</p>
                    </div>
                  </div>
                ))}
              </div>

              <p className="text-center text-sm text-muted-foreground">
                Learn more in our{' '}
                <Link to="/privacy" className="font-medium text-primary hover:text-primary hover:underline">
                  Privacy Policy
                </Link>
              </p>

              <div className="flex gap-3">
                <Button variant="secondary" onClick={() => {
                  setError('');
                  setStep(intent === 'find_referrals' ? 2 : 3);
                }} className="flex-1" size="lg">
                  Back
                </Button>
                <Button onClick={() => setStep(5)} className="flex-1" size="lg">
                  Next
                </Button>
              </div>
            </div>
          )}

          {/* Step 5: Meet your AI coach */}
          {step === 5 && (
            <div className="space-y-5">
              {intent === 'sha[RESEND_KEY_REDACTED]' ? (
                <>
                  <div className="text-center">
                    <p className="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">Your AI network partner</p>
                    <h2 className="text-lg font-semibold text-foreground">Meet Treb</h2>
                  </div>
                  <div className="flex flex-col items-center rounded-xl border border-teal-500/30 bg-teal-500/5 p-8">
                    <TrebAvatar size="xl" pulse />
                    <p className="mt-4 text-center text-base font-medium text-foreground">Hey! I'm Treb.</p>
                    <p className="mt-2 text-center text-sm leading-relaxed text-muted-foreground max-w-sm">
                      I'm your AI network partner. I help you manage intro requests, track referral bonuses, and make the most of sharing your professional network.
                    </p>
                  </div>
                  <div className="space-y-3">
                    <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/50 p-3">
                      <span className="mt-0.5 text-lg" aria-hidden="true">🤝</span>
                      <div>
                        <p className="text-sm font-medium text-foreground">Manage intro requests</p>
                        <p className="text-xs text-muted-foreground">Review and approve intro requests from job seekers who want to connect with people in your network.</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/50 p-3">
                      <span className="mt-0.5 text-lg" aria-hidden="true">💰</span>
                      <div>
                        <p className="text-sm font-medium text-foreground">Capture referral bonuses</p>
                        <p className="text-xs text-muted-foreground">Your employer likely offers $2-10K per referral hire. I help you track and capture these bonuses.</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/50 p-3">
                      <span className="mt-0.5 text-lg" aria-hidden="true">🔒</span>
                      <div>
                        <p className="text-sm font-medium text-foreground">Privacy controls</p>
                        <p className="text-xs text-muted-foreground">You always decide what's shared. Exclude contacts, filter categories, pause anytime.</p>
                      </div>
                    </div>
                  </div>
                </>
              ) : intent === 'explore' ? (
                <>
                  <div className="text-center">
                    <p className="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">Your AI coaches</p>
                    <h2 className="text-lg font-semibold text-foreground">Meet Your Coaches</h2>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="flex flex-col items-center rounded-xl border border-primary/30 bg-primary/5 p-6">
                      <KeevsAvatar size="lg" pulse />
                      <p className="mt-3 text-center text-sm font-medium text-foreground">Keevs</p>
                      <p className="mt-1 text-center text-xs text-muted-foreground">Career Coach</p>
                      <p className="mt-2 text-center text-xs leading-relaxed text-muted-foreground">Finds referral paths, drafts intros, tracks your job search.</p>
                    </div>
                    <div className="flex flex-col items-center rounded-xl border border-teal-500/30 bg-teal-500/5 p-6">
                      <TrebAvatar size="lg" pulse />
                      <p className="mt-3 text-center text-sm font-medium text-foreground">Treb</p>
                      <p className="mt-1 text-center text-xs text-muted-foreground">Network Partner</p>
                      <p className="mt-2 text-center text-xs leading-relaxed text-muted-foreground">Manages intro requests, tracks referral bonuses, privacy controls.</p>
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <div className="text-center">
                    <p className="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">Your AI career coach</p>
                    <h2 className="text-lg font-semibold text-foreground">Meet Keevs</h2>
                  </div>
                  <div className="flex flex-col items-center rounded-xl border border-primary/30 bg-primary/5 p-8">
                    <KeevsAvatar size="xl" pulse />
                    <p className="mt-4 text-center text-base font-medium text-foreground">Hey! I'm Keevs.</p>
                    <p className="mt-2 text-center text-sm leading-relaxed text-muted-foreground max-w-sm">
                      I'm your AI career coach built into WarmPath. I work in the background to find opportunities, warm introductions, and insights you'd miss on your own.
                    </p>
                  </div>
                  <div className="space-y-3">
                    <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/50 p-3">
                      <span className="mt-0.5 text-lg" aria-hidden="true">🔔</span>
                      <div>
                        <p className="text-sm font-medium text-foreground">Proactive alerts</p>
                        <p className="text-xs text-muted-foreground">I'll surface job matches, follow-up reminders, and network insights before you even ask.</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/50 p-3">
                      <span className="mt-0.5 text-lg" aria-hidden="true">💬</span>
                      <div>
                        <p className="text-sm font-medium text-foreground">Ask me anything</p>
                        <p className="text-xs text-muted-foreground">Strategy questions, intro message drafts, company research — I'm here whenever you need me.</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/50 p-3">
                      <span className="mt-0.5 text-lg" aria-hidden="true">📈</span>
                      <div>
                        <p className="text-sm font-medium text-foreground">Gets smarter over time</p>
                        <p className="text-xs text-muted-foreground">The more you use WarmPath, the better I understand your goals and network — and the better my recommendations get.</p>
                      </div>
                    </div>
                  </div>
                </>
              )}

              <div className="flex gap-3">
                <Button variant="secondary" onClick={() => { setError(''); setStep(4); }} className="flex-1" size="lg">
                  Back
                </Button>
                <Button onClick={() => setStep(6)} className="flex-1" size="lg">
                  Let's Go
                </Button>
              </div>
            </div>
          )}

          {/* Step 6: Upload CSV */}
          {step === 6 && !uploadResult && (
            <div className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-foreground">Upload your LinkedIn connections</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Export your connections from LinkedIn (Settings &rarr; Data Privacy &rarr; Get a copy of your data).
                </p>
                <div className="mt-2 rounded-lg border border-primary/30 bg-primary/5 px-3 py-2">
                  <p className="text-xs text-primary/90">
                    <span className="font-semibold">Tip:</span> LinkedIn may require you to download your <span className="font-medium text-primary">full data archive</span> instead of just connections. Once downloaded, unzip and look for <span className="rounded bg-muted px-1 py-0.5 font-mono text-primary">Connections.csv</span> inside.
                  </p>
                </div>
              </div>

              <div
                role="button"
                tabIndex={0}
                aria-label="Upload CSV file - drag and drop or click to browse"
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInputRef.current?.click(); } }}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition ${
                  dragOver ? 'border-primary bg-primary/10' : 'border-border bg-muted/50 hover:border-primary hover:bg-muted'
                }`}
              >
                <input ref={fileInputRef} type="file" accept=".csv" aria-label="Select CSV file" className="hidden" onChange={(e) => handleFile(e.target.files[0])} />
                {file ? (
                  <div>
                    <p className="text-sm font-medium text-foreground">{file.name}</p>
                    <p className="text-xs text-muted-foreground">{(file.size / 1024).toFixed(1)} KB</p>
                  </div>
                ) : (
                  <div>
                    <p className="text-sm text-muted-foreground">Drag and drop your CSV here, or click to browse</p>
                    <p className="mt-1 text-xs text-muted-foreground">.csv files only</p>
                  </div>
                )}
              </div>

              {isHolder && (
                <label className="flex items-start gap-3 rounded-lg border border-border p-3">
                  <input
                    type="checkbox"
                    checked={optInMarketplace}
                    onChange={(e) => setOptInMarketplace(e.target.checked)}
                    className="mt-0.5 h-4 w-4 rounded border-border bg-muted text-primary focus:ring-ring"
                  />
                  <div>
                    <p className="text-sm font-medium text-secondary-foreground">Share my network on the marketplace</p>
                    <p className="text-xs text-muted-foreground">Candidates see anonymized listing fields only (company, role level, department, and connection strength). You approve every intro request before any identity is revealed.</p>
                  </div>
                </label>
              )}

              {isHolder && (
                <MarketplaceVisibilityExplainer compact className="text-xs text-muted-foreground" />
              )}

              <p className="text-xs text-muted-foreground">
                You can exclude specific contacts from the marketplace anytime in{' '}
                <span className="font-medium text-muted-foreground">Settings &gt; Sharing</span>.
              </p>

              {error && <p role="alert" aria-live="polite" className="rounded-md bg-destructive/10 p-2 text-sm text-destructive">{error}</p>}

              {uploading && (
                <div aria-live="polite">
                  <div className="mb-1 h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={Math.round(uploadProgressWidth)} aria-valuemin={0} aria-valuemax={100} aria-label="Upload progress">
                    <div
                      className="h-full rounded-full bg-primary transition-[width] duration-300 ease-out"
                      style={{ width: `${uploadProgressWidth}%` }}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">{uploadProgressMsg}</p>

                  {/* Keevs trivia */}
                  <KeevsTrivia
                    triviaIdx={triviaIdx}
                    triviaFade={triviaFade}
                    triviaPool={triviaPool}
                    currentTrivia={currentTrivia}
                  />
                </div>
              )}

              <div className="flex gap-3">
                <Button variant="secondary" onClick={() => { setError(''); setStep(5); }} size="lg" className="px-4">
                  Back
                </Button>
                <Button onClick={handleUpload} disabled={!file} loading={uploading} className="flex-1" size="lg">
                  Upload
                </Button>
              </div>
              {!uploading && (
                <p className="text-center text-xs text-muted-foreground">
                  Upload is required to finish setup.
                </p>
              )}
            </div>
          )}

          {/* Step 6 done — prompt for work history */}
          {step === 6 && uploadResult && (
            <div className="space-y-4 text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-success/10">
                <span className="text-xl text-success">&#10003;</span>
              </div>
              <h2 className="text-lg font-semibold text-foreground">
                {uploadResult.status === 'queued' || uploadResult.status === 'processing'
                  ? 'CSV uploaded successfully!'
                  : (uploadResult.processed_count ?? uploadResult.row_count)
                    ? `${uploadResult.processed_count ?? uploadResult.row_count} contacts imported!`
                    : 'CSV uploaded successfully!'}
              </h2>
              {uploadResult.status === 'queued' || uploadResult.status === 'processing' ? (
                <p className="text-sm text-muted-foreground">
                  Your contacts are being imported in the background. You can continue — they'll be ready shortly.
                </p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Add your work history to improve referral matching — contacts at your former companies get boosted scores.
                </p>
              )}
              <div className="flex gap-3">
                <Button variant="secondary" onClick={() => { setError(''); setStep(5); }} size="lg" className="px-4">
                  Back
                </Button>
                <Button onClick={() => setStep(7)} className="flex-1" size="lg">
                  Add Work History
                </Button>
              </div>
            </div>
          )}

          {/* Step 7: Work History */}
          {step === 7 && (
            <div className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-foreground">Your work history</h2>
                <p className="mt-1 text-sm text-muted-foreground">Contacts at your former companies will get boosted referral scores.</p>
              </div>

              <input ref={resumeInputRef} type="file" accept=".pdf" aria-label="Upload resume PDF" onChange={handleResumeUpload} className="hidden" />
              <ResumePreviewModal data={resumePreview} onApply={applyResumeData} onClose={() => setResumePreview(null)} />

              {workHistory.length === 0 && (
                <div className="rounded-lg border border-dashed border-border p-4 text-center">
                  <p className="text-sm text-muted-foreground">No entries yet.</p>
                  <div className="mt-3 flex items-center justify-center gap-3">
                    <button
                      type="button"
                      onClick={() => resumeInputRef.current?.click()}
                      disabled={resumeImporting}
                      className="rounded-lg border border-primary px-4 py-2 text-sm font-medium text-primary hover:bg-primary/10 disabled:opacity-50"
                    >
                      {resumeImporting ? (
                        <span className="flex items-center gap-2"><Spinner size="sm" /> Parsing...</span>
                      ) : 'Import from Resume (PDF)'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setWorkHistory([{ ...EMPTY_WORK }])}
                      className="text-sm font-medium text-primary hover:text-primary"
                    >
                      Add manually
                    </button>
                  </div>
                </div>
              )}

              <div className="space-y-3">
                {workHistory.map((entry, i) => (
                  <div key={i} className="rounded-lg border border-border bg-muted/50 p-3">
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <div>
                        <label htmlFor={`wh-company-${i}`} className="mb-1 block text-xs font-medium text-secondary-foreground">Company</label>
                        <input
                          id={`wh-company-${i}`}
                          type="text"
                          value={entry.company}
                          onChange={(e) => setWorkHistory((wh) => wh.map((en, j) => j === i ? { ...en, company: e.target.value } : en))}
                          className={inputClass}
                          placeholder="Company name"
                        />
                      </div>
                      <div>
                        <label htmlFor={`wh-title-${i}`} className="mb-1 block text-xs font-medium text-secondary-foreground">Title / Role</label>
                        <input
                          id={`wh-title-${i}`}
                          type="text"
                          value={entry.title}
                          onChange={(e) => setWorkHistory((wh) => wh.map((en, j) => j === i ? { ...en, title: e.target.value } : en))}
                          className={inputClass}
                          placeholder="e.g. Software Engineer"
                        />
                      </div>
                    </div>
                    <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <div>
                        <label htmlFor={`wh-start-${i}`} className="mb-1 block text-xs font-medium text-secondary-foreground">Start date (month/year)</label>
                        <input
                          id={`wh-start-${i}`}
                          type="month"
                          value={entry.start_date}
                          onChange={(e) => setWorkHistory((wh) => wh.map((en, j) => j === i ? { ...en, start_date: e.target.value } : en))}
                          className={inputClass}
                          placeholder="YYYY-MM"
                        />
                      </div>
                      <div>
                        <label htmlFor={`wh-end-${i}`} className="mb-1 block text-xs font-medium text-secondary-foreground">End date (month/year)</label>
                        {entry.is_current ? (
                          <p className="py-2 text-sm text-muted-foreground">Present</p>
                        ) : (
                          <input
                            id={`wh-end-${i}`}
                            type="month"
                            value={entry.end_date}
                            onChange={(e) => setWorkHistory((wh) => wh.map((en, j) => j === i ? { ...en, end_date: e.target.value } : en))}
                            className={inputClass}
                            placeholder="YYYY-MM"
                          />
                        )}
                      </div>
                    </div>
                    <div className="mt-2 flex items-center justify-between">
                      <label className="flex items-center gap-2 text-xs text-muted-foreground">
                        <input
                          type="checkbox"
                          checked={entry.is_current}
                          onChange={(e) => setWorkHistory((wh) => wh.map((en, j) => j === i ? { ...en, is_current: e.target.checked } : en))}
                          className="h-3.5 w-3.5 rounded border-border bg-muted text-primary focus:ring-ring"
                        />
                        I currently work here
                      </label>
                      <button
                        type="button"
                        aria-label={`Remove work history entry ${i + 1}`}
                        onClick={() => setWorkHistory((wh) => wh.filter((_, j) => j !== i))}
                        className="text-xs text-destructive hover:text-destructive/80 cursor-pointer transition-colors duration-200"
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              {workHistory.length > 0 && (
                <button
                  type="button"
                  onClick={() => setWorkHistory((wh) => [...wh, { ...EMPTY_WORK }])}
                  className="text-sm font-medium text-primary hover:text-primary"
                >
                  + Add another role
                </button>
              )}

              {error && <p role="alert" aria-live="polite" className="rounded-md bg-destructive/10 p-2 text-sm text-destructive">{error}</p>}

              <div className="flex gap-3">
                <Button variant="secondary" onClick={() => { setError(''); setStep(6); }} size="lg" className="px-4">
                  Back
                </Button>
                <Button
                  onClick={async () => {
                    setSaving(true);
                    setError('');
                    try {
                      const entries = workHistory
                        .filter((e) => e.company.trim())
                        .map((e) => ({
                          company: e.company,
                          title: e.title || undefined,
                          start_date: e.start_date || undefined,
                          end_date: e.is_current ? undefined : (e.end_date || undefined),
                        }));
                      if (entries.length === 0) {
                        setError('Add at least one work history entry to finish setup.');
                        return;
                      }
                      const profilePayload = { work_history: entries.length > 0 ? entries : undefined };
                      if (resumeProfileData) {
                        Object.entries(resumeProfileData).forEach(([k, v]) => {
                          if (v) profilePayload[k] = v;
                        });
                      }
                      await authApi.upsertProfile(profilePayload);
                      // Redeem referral code if provided (non-blocking — don't prevent onboarding)
                      if (referralCode) {
                        try {
                          await referralsApi.redeem({ code: referralCode });
                          localStorage.removeItem('referral_code');
                        } catch (err) {
                          console.error('OnboardingPage: failed to redeem referral code', err);
                          // Invalid/expired/already-redeemed — silently continue
                          localStorage.removeItem('referral_code');
                        }
                      }
                      await authApi.completeOnboarding();
                      trackEvent('signup_completed', {
                        intent,
                        has_work_history: entries.length > 0,
                        has_resume: !!resumeProfileData,
                      });
                      await refreshUser();
                      navigate(postWizardRoute);
                    } catch (err) {
                      setError(err.message);
                    } finally {
                      setSaving(false);
                    }
                  }}
                  disabled={workHistory.filter((e) => e.company.trim()).length === 0}
                  loading={saving}
                  className="flex-1"
                  size="lg"
                >
                  Save & Continue
                </Button>
              </div>
              {!saving && (
                <p className="text-center text-xs text-muted-foreground">
                  Work history is required to finish setup.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
