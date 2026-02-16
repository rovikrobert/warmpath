import { useCallback, useRef, useState } from 'react';
import { contacts as contactsApi } from '../api/client';

const LINKEDIN_EXPORT_URL = 'https://www.linkedin.com/mypreferences/d/download-my-data';

export default function UploadModal({ onClose, onComplete, hasContacts }) {
  const [step, setStep] = useState(hasContacts ? 2 : 1);
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const fileInputRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);

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

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError('');
    try {
      setProgress('Parsing contacts...');
      const res = await contactsApi.upload(file);
      setProgress('');
      setResult(res.data);
      setStep(3);
    } catch (err) {
      setError(err.message);
      setProgress('');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-lg rounded-xl bg-white shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-slate-900">Upload Contacts</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">
            &times;
          </button>
        </div>

        {/* Steps indicator */}
        <div className="flex items-center gap-2 px-6 pt-4">
          {[1, 2, 3].map((s) => (
            <div
              key={s}
              className={`h-1.5 flex-1 rounded-full ${
                s <= step ? 'bg-amber-500' : 'bg-slate-200'
              }`}
            />
          ))}
        </div>

        <div className="px-6 py-5">
          {/* Step 1: Instructions */}
          {step === 1 && (
            <div>
              <h3 className="mb-3 text-base font-medium text-slate-900">
                Export your LinkedIn connections
              </h3>
              <ol className="mb-4 space-y-2 text-sm text-slate-600">
                <li className="flex gap-2">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-100 text-xs font-medium text-amber-700">1</span>
                  Go to LinkedIn's data export page
                </li>
                <li className="flex gap-2">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-100 text-xs font-medium text-amber-700">2</span>
                  Select "Connections" only
                </li>
                <li className="flex gap-2">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-100 text-xs font-medium text-amber-700">3</span>
                  Click "Request archive"
                </li>
                <li className="flex gap-2">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-100 text-xs font-medium text-amber-700">4</span>
                  Wait for LinkedIn's email (usually 5-10 minutes)
                </li>
                <li className="flex gap-2">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-100 text-xs font-medium text-amber-700">5</span>
                  Download the ZIP and extract Connections.csv
                </li>
              </ol>
              <a
                href={LINKEDIN_EXPORT_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="mb-3 inline-flex w-full items-center justify-center rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-amber-600"
              >
                Open LinkedIn Export Page
                <span className="ml-1">&nearr;</span>
              </a>
              <button
                onClick={() => setStep(2)}
                className="w-full text-center text-sm text-slate-500 hover:text-amber-600"
              >
                I already have my CSV
              </button>
            </div>
          )}

          {/* Step 2: Upload */}
          {step === 2 && (
            <div>
              <h3 className="mb-3 text-base font-medium text-slate-900">
                Upload your file
              </h3>
              <div
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`mb-4 cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition ${
                  dragOver
                    ? 'border-amber-500 bg-amber-50'
                    : 'border-slate-300 hover:border-amber-400 hover:bg-amber-50/50'
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
                    <p className="text-sm font-medium text-slate-900">{file.name}</p>
                    <p className="text-xs text-slate-500">
                      {(file.size / 1024).toFixed(1)} KB
                    </p>
                  </div>
                ) : (
                  <div>
                    <p className="text-sm text-slate-600">
                      Drag and drop your CSV here, or click to browse
                    </p>
                    <p className="mt-1 text-xs text-slate-400">.csv files only</p>
                  </div>
                )}
              </div>

              {error && (
                <p className="mb-3 text-sm text-red-600">{error}</p>
              )}

              {progress && (
                <div className="mb-3">
                  <div className="mb-1 h-2 overflow-hidden rounded-full bg-slate-200">
                    <div className="h-full animate-pulse rounded-full bg-amber-500" style={{ width: '60%' }} />
                  </div>
                  <p className="text-xs text-slate-500">{progress}</p>
                </div>
              )}

              <button
                onClick={handleUpload}
                disabled={!file || uploading}
                className="w-full rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {uploading ? 'Uploading...' : 'Upload'}
              </button>
            </div>
          )}

          {/* Step 3: Done */}
          {step === 3 && result && (
            <div className="text-center">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-green-100">
                <span className="text-xl text-green-600">&#10003;</span>
              </div>
              <h3 className="mb-1 text-base font-medium text-slate-900">
                You're all set!
              </h3>
              <p className="mb-4 text-sm text-slate-600">
                {result.processed_count ?? result.row_count ?? 0} contacts imported
                {result.company_count ? ` across ${result.company_count} companies` : ''}
              </p>
              <button
                onClick={() => { onComplete?.(); onClose(); }}
                className="w-full rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-amber-600"
              >
                Start searching
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
