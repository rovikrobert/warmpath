import { useCallback, useEffect, useRef, useState } from 'react';
import { contacts as contactsApi } from '../api/client';
import Modal from './ui/Modal';
import Button from './ui/Button';

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
    const maxAttempts = 120;
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
