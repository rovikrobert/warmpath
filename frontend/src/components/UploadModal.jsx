import { useCallback, useEffect, useRef, useState } from 'react';
import { contacts as contactsApi } from '../api/client';
import Modal from './ui/Modal';
import Button from './ui/Button';
import KeevsAvatar from './KeevsAvatar';
import SourceTag from './ui/SourceTag';
import { SOURCES } from '../utils/sources';

const LINKEDIN_EXPORT_URL = 'https://www.linkedin.com/mypreferences/d/download-my-data';

const KEEVS_TRIVIA = [
  {
    text: `Cold applications convert at 1-3%. Referrals convert at ${SOURCES.COLD_VS_REFERRAL.claim}. The same resume, a completely different outcome.`,
    source: SOURCES.COLD_VS_REFERRAL,
  },
  {
    text: `${SOURCES.HIDDEN_JOB_MARKET.claim} of jobs are filled before they're ever posted publicly. Your network is the only way into that market.`,
    source: SOURCES.HIDDEN_JOB_MARKET,
  },
  {
    text: `Referred candidates get ${SOURCES.REFERRAL_INTERVIEW_MULTIPLIER.claim} more interviews than cold applicants — not because they're better, but because someone vouched.`,
    source: SOURCES.REFERRAL_INTERVIEW_MULTIPLIER,
  },
  {
    text: `Referral hires close in ${SOURCES.REFERRAL_HIRE_SPEED.claim} for non-referral hires. Fewer rounds, faster offer.`,
    source: SOURCES.REFERRAL_HIRE_SPEED,
  },
  {
    text: `${SOURCES.NETWORKING_HIRES.claim} of jobs are filled through networking. Most people know this. Few people have a system for it — until now.`,
    source: SOURCES.NETWORKING_HIRES,
  },
  {
    text: `${SOURCES.REFERRAL_RETENTION.claim} of referral hires stay over a year. They land better-fit roles because someone who knew the culture vouched for them.`,
    source: SOURCES.REFERRAL_RETENTION,
  },
  {
    text: `Your contacts at target companies may earn ${SOURCES.REFERRAL_BONUS_RANGE.claim} for referring you. Helping you is literally good for them.`,
    source: SOURCES.REFERRAL_BONUS_RANGE,
  },
  {
    text: 'WarmPath scores every contact on recency, relationship strength, and referral likelihood — so you lead with your best path, not your closest friend.',
    source: null,
  },
];

/** Fisher-Yates shuffle (returns new array). */
function shuffleArray(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export default function UploadModal({ onClose, onComplete, hasContacts }) {
  const [step, setStep] = useState(hasContacts ? 2 : 1);
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);
  const [progressWidth, setProgressWidth] = useState(0);
  const [progressMsg, setProgressMsg] = useState('');

  const PROGRESS_STEPS = [
    'Uploading file...',
    'Parsing contacts...',
    'Normalizing names...',
    'Matching companies...',
    'Scoring connections...',
    'Calculating warm scores...',
    'Analyzing network strength...',
    'Finalizing import...',
  ];


  useEffect(() => {
    if (!uploading) {
      setProgressWidth(0);
      return;
    }
    let frame;
    let start = Date.now();
    const tick = () => {
      const elapsed = (Date.now() - start) / 1000;
      let w;
      if (elapsed < 2) w = elapsed * 10;
      else if (elapsed < 30) w = 20 + (elapsed - 2) * 2;
      else if (elapsed < 90) w = 76 + (elapsed - 30) * 0.3;
      else w = 94 + Math.min(elapsed - 90, 60) * 0.01;
      setProgressWidth(Math.min(w, 95));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [uploading]);

  useEffect(() => {
    if (!uploading) return;
    let idx = 0;
    setProgressMsg(PROGRESS_STEPS[0]);
    const interval = setInterval(() => {
      idx = Math.min(idx + 1, PROGRESS_STEPS.length - 1);
      setProgressMsg(PROGRESS_STEPS[idx]);
    }, 5000);
    return () => clearInterval(interval);
  }, [uploading]);

  // Keevs trivia rotation — greeting first, then shuffled trivia at 8s intervals
  const [triviaPool, setTriviaPool] = useState([]);
  const [triviaIdx, setTriviaIdx] = useState(-1); // -1 = greeting
  const [triviaFade, setTriviaFade] = useState(true);

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
    const f = e.dataTransfer.files[0];
    handleFile(f);
  }, []);

  const pollUploadStatus = async (uploadId) => {
    const maxAttempts = 540; // up to ~9 minutes (matches backend soft_time_limit)
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      try {
        const poll = await contactsApi.getUploadStatus(uploadId);
        const s = poll.data;
        if (s.status === 'completed') return s;
        if (s.status === 'failed') throw new Error(s.error_message || 'CSV processing failed');
      } catch (err) {
        if (err.message?.includes('failed')) throw err;
      }
    }
    throw new Error('Upload timed out — please refresh and check your contacts');
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError('');
    try {
      const res = await contactsApi.upload(file);
      let data = res.data;

      if (data.status === 'queued' || data.status === 'processing') {
        const final = await pollUploadStatus(data.id);
        if (final) data = final;
      }

      setResult(data);
      setStep(3);
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <Modal open onClose={onClose} title="Upload Contacts" maxWidth="max-w-lg">
      {/* Steps indicator */}
      <div className="flex items-center gap-2 mb-4">
        {[1, 2, 3].map((s) => (
          <div
            key={s}
            className={`h-1.5 flex-1 rounded-full ${
              s <= step ? 'bg-amber-500' : 'bg-slate-700'
            }`}
          />
        ))}
      </div>

      {/* Step 1: Instructions */}
      {step === 1 && (
        <div>
          <h3 className="mb-3 text-base font-medium text-slate-50">
            Export your LinkedIn connections
          </h3>
          <ol className="mb-4 space-y-2 text-sm text-slate-400">
            <li className="flex gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-500/10 text-xs font-medium text-amber-400">1</span>
              Go to LinkedIn's data export page
            </li>
            <li className="flex gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-500/10 text-xs font-medium text-amber-400">2</span>
              Select "Connections" only
            </li>
            <li className="flex gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-500/10 text-xs font-medium text-amber-400">3</span>
              Click "Request archive"
            </li>
            <li className="flex gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-500/10 text-xs font-medium text-amber-400">4</span>
              Wait for LinkedIn's email (usually 5-10 minutes)
            </li>
            <li className="flex gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-500/10 text-xs font-medium text-amber-400">5</span>
              Download the ZIP and extract Connections.csv
            </li>
          </ol>
          <a
            href={LINKEDIN_EXPORT_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="mb-3 inline-flex w-full items-center justify-center rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-amber-400"
          >
            Open LinkedIn Export Page
            <span className="ml-1">{"\u2197"}</span>
          </a>
          <button
            onClick={() => setStep(2)}
            className="w-full text-center text-sm text-slate-500 hover:text-amber-400"
          >
            I already have my CSV
          </button>
        </div>
      )}

      {/* Step 2: Upload */}
      {step === 2 && (
        <div>
          <h3 className="mb-3 text-base font-medium text-slate-50">
            Upload your file
          </h3>
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`mb-4 cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition ${
              dragOver
                ? 'border-amber-500 bg-amber-500/10'
                : 'border-slate-600 hover:border-amber-500 hover:bg-slate-800/50'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => handleFile(e.target.files[0])}
            />
            {file ? (
              <div>
                <p className="text-sm font-medium text-slate-50">{file.name}</p>
                <p className="text-xs text-slate-500">
                  {(file.size / 1024).toFixed(1)} KB
                </p>
              </div>
            ) : (
              <div>
                <p className="text-sm text-slate-400">
                  Drag and drop your CSV here, or click to browse
                </p>
                <p className="mt-1 text-xs text-slate-500">.csv files only</p>
              </div>
            )}
          </div>

          {error && (
            <p className="mb-3 text-sm text-red-400">{error}</p>
          )}

          {uploading && (
            <div className="mb-3">
              <div className="mb-1 h-2 overflow-hidden rounded-full bg-slate-700">
                <div
                  className="h-full rounded-full bg-amber-500 transition-[width] duration-300 ease-out"
                  style={{ width: `${progressWidth}%` }}
                />
              </div>
              <p className="text-xs text-slate-500">{progressMsg}</p>

              {/* Keevs trivia */}
              <div className="mt-3 flex min-h-[72px] items-start gap-3" aria-live="polite">
                <KeevsAvatar size="sm" pulse={currentTrivia.isGreeting} className="mt-0.5 shrink-0" />
                <div
                  key={triviaIdx}
                  className={`min-w-0 flex-1 transition-opacity duration-300 ${triviaFade ? 'opacity-100' : 'opacity-0'}`}
                >
                  <span className="text-xs font-medium text-amber-400">Keevs:</span>
                  <p className="mt-0.5 text-sm leading-snug text-slate-300">{currentTrivia.text}</p>
                  {currentTrivia.source && (
                    <div className="mt-1">
                      <SourceTag source={currentTrivia.source.source} label={currentTrivia.source.label} />
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          <Button
            onClick={handleUpload}
            disabled={!file || uploading}
            loading={uploading}
            className="w-full"
          >
            Upload
          </Button>
        </div>
      )}

      {/* Step 3: Done */}
      {step === 3 && result && (
        <div className="text-center">
          {!hasContacts ? (
            <>
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/10">
                <svg className="h-8 w-8 text-emerald-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 0 0-2.455 2.456Z" />
                </svg>
              </div>
              <h3 className="mb-1 text-lg font-semibold text-slate-50">
                {result.status === 'queued' || result.status === 'processing'
                  ? 'Upload received!'
                  : 'Your network is live!'}
              </h3>
              <p className="mb-2 text-sm text-slate-400">
                {result.status === 'queued' || result.status === 'processing'
                  ? 'Your contacts are being imported in the background. They\'ll be ready shortly.'
                  : <>
                      {result.processed_count ?? result.row_count ?? 0} contacts imported
                      {result.company_count ? ` across ${result.company_count} companies` : ''}
                    </>}
              </p>
              {!(result.status === 'queued' || result.status === 'processing') && (
                <p className="mx-auto mb-4 max-w-xs text-xs text-slate-500">
                  You earned 100 credits for your first upload. Your contacts are now scored and ready to search.
                </p>
              )}
              <div className="mx-auto mb-4 flex max-w-xs items-center gap-2 rounded-lg bg-slate-800/60 px-3 py-2">
                <KeevsAvatar size="sm" className="shrink-0" />
                <p className="text-left text-xs text-slate-400">
                  <span className="font-medium text-amber-400">Keevs:</span>{' '}
                  Your network is scored and ready. Let's find your fastest path in.
                </p>
              </div>
              <Button
                onClick={() => { onComplete?.(); onClose(); }}
                className="w-full"
              >
                Start searching
              </Button>
            </>
          ) : (
            <>
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/10">
                <span className="text-xl text-emerald-400">&#10003;</span>
              </div>
              <h3 className="mb-1 text-base font-medium text-slate-50">
                {result.status === 'queued' || result.status === 'processing'
                  ? 'Upload received!'
                  : "You're all set!"}
              </h3>
              <p className="mb-4 text-sm text-slate-400">
                {result.status === 'queued' || result.status === 'processing'
                  ? 'Your contacts are being imported in the background. They\'ll be ready shortly.'
                  : <>
                      {result.processed_count ?? result.row_count ?? 0} contacts imported
                      {result.company_count ? ` across ${result.company_count} companies` : ''}
                    </>}
              </p>
              <Button
                onClick={() => { onComplete?.(); onClose(); }}
                className="w-full"
              >
                Start searching
              </Button>
            </>
          )}
        </div>
      )}
    </Modal>
  );
}
