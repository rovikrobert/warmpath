import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { auth as authApi, contacts as contactsApi, preferences, marketplace } from '../api/client';
import TagInput from '../components/TagInput';

function ResumePreviewModal({ data, onApply, onClose }) {
  if (!data) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" role="dialog" aria-modal="true" aria-labelledby="resume-preview-title">
      <div className="mx-4 w-full max-w-lg max-h-[80vh] overflow-y-auto rounded-xl bg-white p-6 shadow-xl">
        <h3 id="resume-preview-title" className="text-lg font-bold text-slate-900">Resume Preview</h3>
        <p className="mt-1 text-sm text-slate-500">Review parsed data before applying.</p>
        <div className="mt-4 space-y-3 text-sm">
          {data.headline && <div><span className="font-medium text-slate-700">Headline:</span> {data.headline}</div>}
          {data.current_title && <div><span className="font-medium text-slate-700">Title:</span> {data.current_title}</div>}
          {data.current_company && <div><span className="font-medium text-slate-700">Company:</span> {data.current_company}</div>}
          {data.industry && <div><span className="font-medium text-slate-700">Industry:</span> {data.industry}</div>}
          {data.location && <div><span className="font-medium text-slate-700">Location:</span> {data.location}</div>}
          {data.bio_summary && <div><span className="font-medium text-slate-700">Summary:</span> {data.bio_summary}</div>}
          {data.work_history?.length > 0 && (
            <div>
              <span className="font-medium text-slate-700">Work History:</span>
              <ul className="mt-1 space-y-1 pl-4">
                {data.work_history.map((w, i) => (
                  <li key={i} className="text-slate-600">
                    {w.title} at {w.company} ({w.start_date || '?'} - {w.end_date || 'Present'})
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div className="mt-5 flex gap-3">
          <button onClick={onClose} className="flex-1 rounded-lg border border-slate-300 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
            Cancel
          </button>
          <button onClick={() => onApply(data)} className="flex-1 rounded-lg bg-amber-500 py-2 text-sm font-medium text-white hover:bg-amber-600">
            Apply
          </button>
        </div>
      </div>
    </div>
  );
}

const EMPTY_WORK = { company: '', title: '', start_date: '', end_date: '', is_current: false };

const SENIORITY_OPTIONS = ['Staff / Principal', 'Manager', 'Director', 'VP', 'C-Suite'];

const TOTAL_STEPS = 8;

// Privacy step data (steps 3-6)
const PRIVACY_STEPS = [
  {
    step: 3,
    title: 'Your Data Stays Private',
    text: 'Everything you upload lives in your Private Vault \u2014 encrypted and visible only to you. Your full contact data is never shared with other users.',
    icon: (
      <svg className="h-10 w-10 text-amber-600" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
      </svg>
    ),
    bgColor: 'bg-amber-50',
    borderColor: 'border-amber-200',
  },
  {
    step: 4,
    title: 'Contacts Are Protected',
    text: 'If you share contacts on the marketplace, only anonymised info is shown (company + role level). Names and emails are never revealed without your explicit approval.',
    icon: (
      <svg className="h-10 w-10 text-green-600" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" />
      </svg>
    ),
    bgColor: 'bg-green-50',
    borderColor: 'border-green-200',
  },
  {
    step: 5,
    title: "Your Employer Can't See You",
    text: 'Your job search activity is completely invisible. No employer \u2014 including yours \u2014 can discover you\'re looking for new opportunities.',
    icon: (
      <svg className="h-10 w-10 text-purple-600" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 0 0 1.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.451 10.451 0 0 1 12 4.5c4.756 0 8.773 3.162 10.065 7.498a10.522 10.522 0 0 1-4.293 5.774M6.228 6.228 3 3m3.228 3.228 3.65 3.65m7.894 7.894L21 21m-3.228-3.228-3.65-3.65m0 0a3 3 0 1 0-4.243-4.243m4.242 4.242L9.88 9.88" />
      </svg>
    ),
    bgColor: 'bg-purple-50',
    borderColor: 'border-purple-200',
  },
  {
    step: 6,
    title: 'Anyone Can Opt Out',
    text: 'Any person can request removal from WarmPath at any time, even if they don\'t have an account. We maintain a permanent suppression list.',
    icon: (
      <svg className="h-10 w-10 text-blue-600" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6a2.25 2.25 0 0 0-2.25 2.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15m3 0 3-3m0 0-3-3m3 3H9" />
      </svg>
    ),
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-200',
  },
];

export default function OnboardingPage() {
  const { refreshUser, setJustSignedUp } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);

  // Step 1: Job preferences
  const [prefs, setPrefs] = useState({
    target_role: '',
    target_seniority: '',
    target_industries: [],
    target_locations: [],
    open_to_remote: true,
  });

  // Step 2: User type
  const [userType, setUserType] = useState('');

  // Step 7: Upload
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [optInMarketplace, setOptInMarketplace] = useState(false);
  const [error, setError] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);
  const [uploadProgressWidth, setUploadProgressWidth] = useState(0);
  const [uploadProgressMsg, setUploadProgressMsg] = useState('');

  const UPLOAD_STEPS = [
    'Reading file...',
    'Parsing contacts...',
    'Normalizing names...',
    'Matching companies...',
    'Calculating warm scores...',
    'Almost done...',
  ];

  useEffect(() => {
    if (!uploading) { setUploadProgressWidth(0); return; }
    let frame;
    const start = Date.now();
    const tick = () => {
      const elapsed = (Date.now() - start) / 1000;
      let w;
      if (elapsed < 1) w = elapsed * 30;
      else if (elapsed < 8) w = 30 + (elapsed - 1) * 8.5;
      else w = 90 + Math.min(elapsed - 8, 10) * 0.5;
      setUploadProgressWidth(Math.min(w, 95));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [uploading]);

  useEffect(() => {
    if (!uploading) return;
    let idx = 0;
    setUploadProgressMsg(UPLOAD_STEPS[0]);
    const interval = setInterval(() => {
      idx = Math.min(idx + 1, UPLOAD_STEPS.length - 1);
      setUploadProgressMsg(UPLOAD_STEPS[idx]);
    }, 1500);
    return () => clearInterval(interval);
  }, [uploading]);

  // Step 8: Work history + resume import
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

  // Step 1 -> 2
  const handlePrefs = async () => {
    setSaving(true);
    setError('');
    try {
      if (prefs.target_role.trim()) {
        await preferences.upsertJob({
          target_role: prefs.target_role,
          target_seniority: prefs.target_seniority || null,
          target_industries: prefs.target_industries.length ? prefs.target_industries : null,
          target_locations: prefs.target_locations.length ? prefs.target_locations : null,
          open_to_remote: prefs.open_to_remote,
        });
      }
      setStep(2);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // Step 2 -> 3 (privacy steps)
  const handleUserType = async () => {
    if (!userType) return;
    setSaving(true);
    setError('');
    try {
      await authApi.updateUserType(userType);
      await refreshUser();
      setStep(3);
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

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError('');
    try {
      const res = await contactsApi.upload(file);
      setUploadResult(res.data);
      if (optInMarketplace) {
        await marketplace.updateSharingPrefs({ opt_in_marketplace: true });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const finish = () => {
    setJustSignedUp(false);
    navigate('/dashboard');
  };

  const isHolder = userType === 'network_holder' || userType === 'both';

  const inputClass = 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500';

  // Check if current step is a privacy step
  const privacyStep = PRIVACY_STEPS.find((ps) => ps.step === step);

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-12" role="main">
      <div className="w-full max-w-lg">
        {/* Logo */}
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-bold text-slate-900">
            <span className="text-amber-500">~</span> WarmPath
          </h1>
        </div>

        {/* Progress — clickable segments to jump back */}
        <div className="mb-6 flex items-center gap-1" role="progressbar" aria-valuenow={step} aria-valuemin={1} aria-valuemax={TOTAL_STEPS} aria-label={`Onboarding step ${step} of ${TOTAL_STEPS}`}>
          {Array.from({ length: TOTAL_STEPS }, (_, i) => i + 1).map((s) => (
            <button
              key={s}
              type="button"
              aria-label={`Go to step ${s}`}
              onClick={() => { if (s < step) { setError(''); setStep(s); } }}
              disabled={s >= step}
              className={`h-1.5 flex-1 rounded-full transition ${s <= step ? 'bg-amber-500' : 'bg-slate-200'} ${s < step ? 'cursor-pointer hover:bg-amber-400' : ''}`}
            />
          ))}
        </div>

        <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          {/* Step 1: Job Preferences */}
          {step === 1 && (
            <div className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">What are you looking for?</h2>
                <p className="mt-1 text-sm text-slate-500">Help us find the best referral paths for you.</p>
              </div>

              <div>
                <label htmlFor="onboard-target-role" className="mb-1 block text-sm font-medium text-slate-700">Target Role</label>
                <input id="onboard-target-role" type="text" value={prefs.target_role} onChange={setPref('target_role')} className={inputClass} placeholder="e.g. Software Engineer, Product Manager" />
              </div>

              <div>
                <label htmlFor="onboard-seniority" className="mb-1 block text-sm font-medium text-slate-700">Seniority Level</label>
                <select id="onboard-seniority" value={prefs.target_seniority} onChange={setPref('target_seniority')} className={inputClass}>
                  <option value="">Select level</option>
                  {SENIORITY_OPTIONS.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>

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

              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={prefs.open_to_remote}
                  onChange={(e) => setPrefs({ ...prefs, open_to_remote: e.target.checked })}
                  className="h-4 w-4 rounded border-slate-300 text-amber-500 focus:ring-amber-500"
                />
                Open to remote roles
              </label>

              {error && <p role="alert" aria-live="polite" className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}

              <div className="flex gap-3">
                <button onClick={() => setStep(2)} className="flex-1 rounded-lg border border-slate-300 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50">
                  Skip for now
                </button>
                <button onClick={handlePrefs} disabled={saving} className="flex-1 rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50">
                  {saving ? 'Saving...' : 'Continue'}
                </button>
              </div>
            </div>
          )}

          {/* Step 2: User Type */}
          {step === 2 && (
            <div className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">How do you want to use WarmPath?</h2>
                <p className="mt-1 text-sm text-slate-500">You can change this anytime.</p>
              </div>

              <div className="space-y-3">
                {[
                  { value: 'job_seeker', title: "I'm job hunting", desc: 'Search networks, find referral paths, and get introduced to people at your target companies.' },
                  { value: 'network_holder', title: 'I want to help others get referred', desc: 'Share your network anonymously and earn credits + referral bonuses when your contacts hire someone you referred.' },
                  { value: 'both', title: 'Both!', desc: 'Search for referrals AND share your network. Most members choose this.' },
                ].map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setUserType(opt.value)}
                    className={`w-full rounded-lg border-2 p-4 text-left transition ${
                      userType === opt.value
                        ? 'border-amber-500 bg-amber-50'
                        : 'border-slate-200 hover:border-slate-300'
                    }`}
                  >
                    <p className="font-medium text-slate-900">{opt.title}</p>
                    <p className="mt-1 text-sm text-slate-500">{opt.desc}</p>
                  </button>
                ))}
              </div>

              {error && <p role="alert" aria-live="polite" className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}

              <div className="flex gap-3">
                <button onClick={() => { setError(''); setStep(1); }} className="flex-1 rounded-lg border border-slate-300 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50">
                  Back
                </button>
                <button
                  onClick={handleUserType}
                  disabled={!userType || saving}
                  className="flex-1 rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
                >
                  {saving ? 'Saving...' : 'Continue'}
                </button>
              </div>
            </div>
          )}

          {/* Steps 3-6: Privacy Explainer */}
          {privacyStep && (
            <div className="space-y-5">
              <div className="text-center">
                <p className="mb-1 text-xs font-medium uppercase tracking-wider text-slate-400">How we protect your data</p>
                <h2 className="text-lg font-semibold text-slate-900">{privacyStep.title}</h2>
              </div>

              <div className={`flex flex-col items-center rounded-xl border ${privacyStep.borderColor} ${privacyStep.bgColor} p-8`}>
                {privacyStep.icon}
                <p className="mt-4 text-center text-sm leading-relaxed text-slate-700">
                  {privacyStep.text}
                </p>
              </div>

              {/* Show privacy policy link on last privacy step */}
              {step === 6 && (
                <p className="text-center text-sm text-slate-500">
                  Learn more in our{' '}
                  <Link to="/privacy" className="font-medium text-amber-600 hover:text-amber-700 hover:underline">
                    Privacy Policy
                  </Link>
                </p>
              )}

              <div className="flex gap-3">
                <button onClick={() => { setError(''); setStep(step - 1); }} className="flex-1 rounded-lg border border-slate-300 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50">
                  Back
                </button>
                <button
                  onClick={() => setStep(step + 1)}
                  className="flex-1 rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600"
                >
                  Next
                </button>
              </div>
            </div>
          )}

          {/* Step 7: Upload CSV */}
          {step === 7 && !uploadResult && (
            <div className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">Upload your LinkedIn connections</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Export your connections from LinkedIn (Settings &rarr; Data Privacy &rarr; Get a copy of your data &rarr; Connections).
                </p>
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
                  dragOver ? 'border-amber-500 bg-amber-50' : 'border-slate-300 hover:border-amber-400 hover:bg-amber-50/50'
                }`}
              >
                <input ref={fileInputRef} type="file" accept=".csv" aria-label="Select CSV file" className="hidden" onChange={(e) => handleFile(e.target.files[0])} />
                {file ? (
                  <div>
                    <p className="text-sm font-medium text-slate-900">{file.name}</p>
                    <p className="text-xs text-slate-500">{(file.size / 1024).toFixed(1)} KB</p>
                  </div>
                ) : (
                  <div>
                    <p className="text-sm text-slate-600">Drag and drop your CSV here, or click to browse</p>
                    <p className="mt-1 text-xs text-slate-400">.csv files only</p>
                  </div>
                )}
              </div>

              {isHolder && (
                <label className="flex items-start gap-3 rounded-lg border border-slate-200 p-3">
                  <input
                    type="checkbox"
                    checked={optInMarketplace}
                    onChange={(e) => setOptInMarketplace(e.target.checked)}
                    className="mt-0.5 h-4 w-4 rounded border-slate-300 text-amber-500 focus:ring-amber-500"
                  />
                  <div>
                    <p className="text-sm font-medium text-slate-700">Share my network on the marketplace</p>
                    <p className="text-xs text-slate-500">Job seekers see anonymized listings only (company + role level). You approve every intro request before any identity is revealed.</p>
                  </div>
                </label>
              )}

              {error && <p role="alert" aria-live="polite" className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}

              {uploading && (
                <div aria-live="polite">
                  <div className="mb-1 h-2 overflow-hidden rounded-full bg-slate-200" role="progressbar" aria-valuenow={Math.round(uploadProgressWidth)} aria-valuemin={0} aria-valuemax={100} aria-label="Upload progress">
                    <div
                      className="h-full rounded-full bg-amber-500 transition-[width] duration-300 ease-out"
                      style={{ width: `${uploadProgressWidth}%` }}
                    />
                  </div>
                  <p className="text-xs text-slate-500">{uploadProgressMsg}</p>
                </div>
              )}

              <div className="flex gap-3">
                <button onClick={() => { setError(''); setStep(6); }} className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50">
                  Back
                </button>
                <button onClick={finish} className="flex-1 rounded-lg border border-slate-300 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50">
                  Skip for now
                </button>
                <button onClick={handleUpload} disabled={!file || uploading} className="flex-1 rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50">
                  {uploading ? 'Uploading...' : 'Upload'}
                </button>
              </div>
            </div>
          )}

          {/* Step 7 done — prompt for work history */}
          {step === 7 && uploadResult && (
            <div className="space-y-4 text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-100">
                <span className="text-xl text-green-600">&#10003;</span>
              </div>
              <h2 className="text-lg font-semibold text-slate-900">
                {uploadResult.processed_count ?? uploadResult.row_count ?? 0} contacts imported!
              </h2>
              <p className="text-sm text-slate-600">
                Add your work history to improve referral matching — contacts at your former companies get boosted scores.
              </p>
              <div className="flex gap-3">
                <button onClick={() => { setError(''); setStep(6); }} className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50">
                  Back
                </button>
                <button onClick={finish} className="flex-1 rounded-lg border border-slate-300 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50">
                  Skip for now
                </button>
                <button onClick={() => setStep(8)} className="flex-1 rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600">
                  Add Work History
                </button>
              </div>
            </div>
          )}

          {/* Step 8: Work History */}
          {step === 8 && (
            <div className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">Your work history</h2>
                <p className="mt-1 text-sm text-slate-500">Contacts at your former companies will get boosted referral scores.</p>
              </div>

              <input ref={resumeInputRef} type="file" accept=".pdf" aria-label="Upload resume PDF" onChange={handleResumeUpload} className="hidden" />
              <ResumePreviewModal data={resumePreview} onApply={applyResumeData} onClose={() => setResumePreview(null)} />

              {workHistory.length === 0 && (
                <div className="rounded-lg border border-dashed border-slate-300 p-4 text-center">
                  <p className="text-sm text-slate-500">No entries yet.</p>
                  <div className="mt-3 flex items-center justify-center gap-3">
                    <button
                      type="button"
                      onClick={() => resumeInputRef.current?.click()}
                      disabled={resumeImporting}
                      className="rounded-lg border border-amber-500 px-4 py-2 text-sm font-medium text-amber-600 hover:bg-amber-50 disabled:opacity-50"
                    >
                      {resumeImporting ? 'Parsing...' : 'Import from Resume (PDF)'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setWorkHistory([{ ...EMPTY_WORK }])}
                      className="text-sm font-medium text-amber-600 hover:text-amber-700"
                    >
                      Add manually
                    </button>
                  </div>
                </div>
              )}

              <div className="space-y-3">
                {workHistory.map((entry, i) => (
                  <div key={i} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label htmlFor={`wh-company-${i}`} className="mb-1 block text-xs font-medium text-slate-700">Company</label>
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
                        <label htmlFor={`wh-title-${i}`} className="mb-1 block text-xs font-medium text-slate-700">Title / Role</label>
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
                    <div className="mt-2 grid grid-cols-2 gap-3">
                      <div>
                        <label htmlFor={`wh-start-${i}`} className="mb-1 block text-xs font-medium text-slate-700">Start</label>
                        <input
                          id={`wh-start-${i}`}
                          type="month"
                          value={entry.start_date}
                          onChange={(e) => setWorkHistory((wh) => wh.map((en, j) => j === i ? { ...en, start_date: e.target.value } : en))}
                          className={inputClass}
                        />
                      </div>
                      <div>
                        <label htmlFor={`wh-end-${i}`} className="mb-1 block text-xs font-medium text-slate-700">End</label>
                        {entry.is_current ? (
                          <p className="py-2 text-sm text-slate-500">Present</p>
                        ) : (
                          <input
                            id={`wh-end-${i}`}
                            type="month"
                            value={entry.end_date}
                            onChange={(e) => setWorkHistory((wh) => wh.map((en, j) => j === i ? { ...en, end_date: e.target.value } : en))}
                            className={inputClass}
                          />
                        )}
                      </div>
                    </div>
                    <div className="mt-2 flex items-center justify-between">
                      <label className="flex items-center gap-2 text-xs text-slate-600">
                        <input
                          type="checkbox"
                          checked={entry.is_current}
                          onChange={(e) => setWorkHistory((wh) => wh.map((en, j) => j === i ? { ...en, is_current: e.target.checked } : en))}
                          className="h-3.5 w-3.5 rounded border-slate-300 text-amber-500 focus:ring-amber-500"
                        />
                        I currently work here
                      </label>
                      <button
                        type="button"
                        aria-label={`Remove work history entry ${i + 1}`}
                        onClick={() => setWorkHistory((wh) => wh.filter((_, j) => j !== i))}
                        className="text-xs text-red-500 hover:text-red-600"
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
                  className="text-sm font-medium text-amber-600 hover:text-amber-700"
                >
                  + Add another role
                </button>
              )}

              {error && <p role="alert" aria-live="polite" className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}

              <div className="flex gap-3">
                <button onClick={() => { setError(''); setStep(7); }} className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50">
                  Back
                </button>
                <button onClick={finish} className="flex-1 rounded-lg border border-slate-300 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50">
                  Skip for now
                </button>
                <button
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
                      const profilePayload = { work_history: entries.length > 0 ? entries : undefined };
                      // Include resume profile fields if imported from resume
                      if (resumeProfileData) {
                        Object.entries(resumeProfileData).forEach(([k, v]) => {
                          if (v) profilePayload[k] = v;
                        });
                      }
                      await authApi.upsertProfile(profilePayload);
                      finish();
                    } catch (err) {
                      setError(err.message);
                    } finally {
                      setSaving(false);
                    }
                  }}
                  disabled={saving}
                  className="flex-1 rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
                >
                  {saving ? 'Saving...' : 'Save & Continue'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
