import { useCallback, useEffect, useRef, useState } from 'react';
import { contacts as contactsApi } from '../api/client';
import Modal from './ui/Modal';
import Button from './ui/Button';
import KeevsAvatar from './KeevsAvatar';
import KeevsTrivia from './KeevsTrivia';
import { KEEVS_TRIVIA, shuffleArray } from '../utils/keevs-trivia';

const LINKEDIN_EXPORT_URL = 'https://www.linkedin.com/mypreferences/d/download-my-data';

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
  const [etaSeconds, setEtaSeconds] = useState(null);

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
    let maxAttempts = 540;
    let pollInterval = 1000;
    let isBatchMode = false;

    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((r) => setTimeout(r, pollInterval));
      try {
        const poll = await contactsApi.getUploadStatus(uploadId);
        const s = poll.data;

        const total = s.total_chunks || 0;
        const cleaned = s.chunks_cleaned || 0;
        const imported = s.chunks_imported || 0;
        const rowCount = s.row_count || 0;
        const created = s.contacts_created || 0;
        const phase = s.progress_phase;
        const contactLabel = rowCount > 0 ? ` — ${rowCount.toLocaleString()} contacts` : '';

        // Detect batch mode and adjust polling
        if (phase && phase.startsWith('batch_') && !isBatchMode) {
          isBatchMode = true;
          pollInterval = 10000;
          maxAttempts = 360;
        }

        if (total > 0) {
          let pct;
          if (phase === 'scoring') {
            pct = 95;
          } else if (imported > 0) {
            pct = Math.min(60 + (imported / total) * 35, 94);
          } else if (phase === 'batch_submitted' || phase === 'batch_processing') {
            pct = Math.min(10 + (cleaned / total) * 50, 55);
            setProgressMsg(`Processing in background${contactLabel}...`);
          } else {
            pct = Math.min((cleaned / total) * 60, 59);
          }
          setProgressWidth(pct);

          if (phase === 'scoring') {
            setProgressMsg(`Scoring contacts... (${created.toLocaleString()} imported)`);
          } else if (imported > 0) {
            setProgressMsg(`Importing contacts${contactLabel} (${imported}/${total} batches)`);
          } else if (phase === 'batch_submitted') {
            setProgressMsg(`Processing in background${contactLabel}...`);
          } else if (phase === 'batch_processing') {
            setProgressMsg(`AI cleaning in background${contactLabel} (${cleaned}/${total} batches)`);
          } else if (cleaned > 0) {
            setProgressMsg(`AI cleaning${contactLabel} (${cleaned}/${total} batches)`);
          } else {
            setProgressMsg(`Parsing contacts...`);
          }
        } else if (phase) {
          if (phase === 'parsing') {
            setProgressMsg('Parsing contacts...');
            setProgressWidth(8);
          } else if (phase === 'batch_submitted') {
            setProgressMsg('Submitting to background processor...');
            setProgressWidth(12);
          } else {
            setProgressMsg(`Processing${contactLabel}...`);
          }
        }

        // Update ETA
        if (s.estimated_seconds_remaining != null) {
          setEtaSeconds(Math.round(s.estimated_seconds_remaining));
        } else if (isBatchMode) {
          setEtaSeconds(null);
        }

        if (s.status === 'completed') {
          setProgressWidth(100);
          setProgressMsg('Done!');
          setEtaSeconds(null);
          return s;
        }
        if (s.status === 'failed') throw new Error(s.error_message || 'CSV processing failed');

        // After 15 min of batch polling, stop and show background message
        if (isBatchMode && i > 90) {
          setProgressWidth(50);
          setProgressMsg("We'll email you when your contacts are ready.");
          setEtaSeconds(null);
          return s;
        }
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
    setProgressWidth(5);
    setProgressMsg('Uploading file...');
    setEtaSeconds(null);
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
      setEtaSeconds(null);
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

          {/* Heads-up callout */}
          <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2.5">
            <p className="text-xs text-amber-300/90">
              <span className="font-semibold">Heads up:</span> LinkedIn recently changed their export flow. You may need to download your <span className="font-medium text-amber-200">full data archive</span> first, then find the <span className="font-medium text-amber-200">Connections.csv</span> file inside the downloaded ZIP.
            </p>
          </div>

          <ol className="mb-4 space-y-2 text-sm text-slate-400">
            <li className="flex gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-500/10 text-xs font-medium text-amber-400">1</span>
              <span>Go to LinkedIn <span className="text-slate-300">Settings &rarr; Data Privacy &rarr; Get a copy of your data</span></span>
            </li>
            <li className="flex gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-500/10 text-xs font-medium text-amber-400">2</span>
              <span>Select <span className="text-slate-300">"Connections"</span> (if the option is available) or <span className="text-slate-300">"Download larger data archive"</span></span>
            </li>
            <li className="flex gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-500/10 text-xs font-medium text-amber-400">3</span>
              Click "Request archive" and wait for LinkedIn's email (can be instant or up to 24 hours for full archives)
            </li>
            <li className="flex gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-500/10 text-xs font-medium text-amber-400">4</span>
              Download the ZIP from the email link
            </li>
            <li className="flex gap-2">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-500/10 text-xs font-medium text-amber-400">5</span>
              <span>Unzip and find <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-xs text-amber-300">Connections.csv</span> inside</span>
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
              <div className="flex items-center justify-between">
                <p className="text-xs text-slate-500">{progressMsg}</p>
                {etaSeconds != null && etaSeconds > 0 && (
                  <p className="text-xs text-slate-500">
                    ~{etaSeconds >= 60 ? `${Math.floor(etaSeconds / 60)}m ${etaSeconds % 60}s` : `${etaSeconds}s`} remaining
                  </p>
                )}
              </div>

              {/* Keevs trivia */}
              <KeevsTrivia
                triviaIdx={triviaIdx}
                triviaFade={triviaFade}
                triviaPool={triviaPool}
                currentTrivia={currentTrivia}
              />
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
                onClick={() => { onComplete?.(result); onClose(); }}
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
                onClick={() => { onComplete?.(result); onClose(); }}
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
