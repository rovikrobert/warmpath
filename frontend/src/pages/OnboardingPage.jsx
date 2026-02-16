import { useCallback, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { auth as authApi, contacts as contactsApi, preferences, marketplace } from '../api/client';
import TagInput from '../components/TagInput';

const SENIORITY_OPTIONS = ['Entry Level', 'Mid Level', 'Senior', 'Staff / Principal', 'Manager', 'Director', 'VP', 'C-Suite'];

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

  // Step 3: Upload
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [optInMarketplace, setOptInMarketplace] = useState(false);
  const [error, setError] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

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

  // Step 2 -> 3
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

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-12">
      <div className="w-full max-w-lg">
        {/* Logo */}
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-bold text-slate-900">
            <span className="text-amber-500">~</span> WarmPath
          </h1>
        </div>

        {/* Progress */}
        <div className="mb-6 flex items-center gap-2">
          {[1, 2, 3].map((s) => (
            <div key={s} className={`h-1.5 flex-1 rounded-full ${s <= step ? 'bg-amber-500' : 'bg-slate-200'}`} />
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
                <label className="mb-1 block text-sm font-medium text-slate-700">Target Role</label>
                <input type="text" value={prefs.target_role} onChange={setPref('target_role')} className={inputClass} placeholder="e.g. Software Engineer, Product Manager" />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">Seniority Level</label>
                <select value={prefs.target_seniority} onChange={setPref('target_seniority')} className={inputClass}>
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

              {error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}

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

              {error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}

              <button
                onClick={handleUserType}
                disabled={!userType || saving}
                className="w-full rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Continue'}
              </button>
            </div>
          )}

          {/* Step 3: Upload CSV */}
          {step === 3 && !uploadResult && (
            <div className="space-y-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">Upload your LinkedIn connections</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Export your connections from LinkedIn (Settings &rarr; Data Privacy &rarr; Get a copy of your data &rarr; Connections).
                </p>
              </div>

              <div
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition ${
                  dragOver ? 'border-amber-500 bg-amber-50' : 'border-slate-300 hover:border-amber-400 hover:bg-amber-50/50'
                }`}
              >
                <input ref={fileInputRef} type="file" accept=".csv" className="hidden" onChange={(e) => handleFile(e.target.files[0])} />
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

              {error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}

              {uploading && (
                <div>
                  <div className="mb-1 h-2 overflow-hidden rounded-full bg-slate-200">
                    <div className="h-full animate-pulse rounded-full bg-amber-500" style={{ width: '60%' }} />
                  </div>
                  <p className="text-xs text-slate-500">Parsing contacts...</p>
                </div>
              )}

              <div className="flex gap-3">
                <button onClick={finish} className="flex-1 rounded-lg border border-slate-300 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50">
                  Skip for now
                </button>
                <button onClick={handleUpload} disabled={!file || uploading} className="flex-1 rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50">
                  {uploading ? 'Uploading...' : 'Upload'}
                </button>
              </div>
            </div>
          )}

          {/* Step 3 done */}
          {step === 3 && uploadResult && (
            <div className="space-y-4 text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-100">
                <span className="text-xl text-green-600">&#10003;</span>
              </div>
              <h2 className="text-lg font-semibold text-slate-900">You're all set!</h2>
              <p className="text-sm text-slate-600">
                {uploadResult.processed_count ?? uploadResult.row_count ?? 0} contacts imported
                {uploadResult.company_count ? ` across ${uploadResult.company_count} companies` : ''}
              </p>
              <button onClick={finish} className="w-full rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600">
                Go to Dashboard
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
