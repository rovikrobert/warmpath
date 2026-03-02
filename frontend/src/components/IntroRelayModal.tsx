import { useEffect, useState } from 'react';
import { getRateLimitMessage } from '../utils/errorCopy';
import Modal from './ui/Modal';
import Button from './ui/Button';
import type { ConfirmSentResult } from '../types/marketplace';

interface IntroRelayModalProps {
  isOpen: boolean;
  onClose: () => void;
  contactName?: string;
  linkedinUrl?: string;
  draftedMessage?: string;
  onConfirmSent: () => Promise<ConfirmSentResult>;
}

export default function IntroRelayModal({ isOpen, onClose, contactName, linkedinUrl, draftedMessage, onConfirmSent }: IntroRelayModalProps) {
  const [copied, setCopied] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [confirmResult, setConfirmResult] = useState<ConfirmSentResult | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (isOpen) {
      setCopied(false);
      setConfirming(false);
      setConfirmed(false);
      setConfirmResult(null);
      setError('');
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const copyMessage = () => {
    navigator.clipboard.writeText(draftedMessage || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const openLinkedIn = () => {
    copyMessage();
    if (linkedinUrl) {
      window.open(linkedinUrl, '_blank', 'noopener,noreferrer');
    }
  };

  const handleConfirmSent = async () => {
    setConfirming(true);
    setError('');
    try {
      const result = await onConfirmSent();
      setConfirmResult(result);
      setConfirmed(true);
    } catch (err) {
      setError(getRateLimitMessage(err, err.message || 'Failed to confirm. Please try again.'));
    } finally {
      setConfirming(false);
    }
  };

  return (
    <Modal open onClose={onClose} title="Send the Introduction" maxWidth="max-w-md">
      <div className="space-y-4">
        {confirmed ? (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4 text-center">
            <svg className="mx-auto mb-2 h-8 w-8 text-emerald-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
            <p className="text-sm font-semibold text-emerald-400">
              {confirmResult?.credits_awarded
                ? `Confirmed! ${confirmResult.credits_awarded} credits earned.`
                : 'Confirmed. Credits are pending review.'}
            </p>
            <p className="mt-1 text-xs text-emerald-400/70">
              {confirmResult?.credits_awarded
                ? 'Thank you for facilitating this introduction.'
                : 'Thanks for confirming the send. We will update your credit status after verification.'}
            </p>
            <Button variant="secondary" size="sm" onClick={onClose} className="mt-3">
              Close
            </Button>
          </div>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              We don't have an email address for <span className="font-medium text-foreground">{contactName || 'your contact'}</span>,
              so we'll need you to send the introduction yourself via LinkedIn or another channel.
            </p>

            {/* Drafted message preview */}
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Suggested message
              </label>
              <div className="rounded-lg border border-border bg-muted/50 p-3 text-sm text-secondary-foreground">
                {draftedMessage || 'No drafted message available.'}
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex gap-2">
              {linkedinUrl ? (
                <Button onClick={openLinkedIn} className="flex-1" aria-label={`Copy message and open LinkedIn profile for ${contactName || 'contact'}`}>
                  {copied ? 'Copied! Opening LinkedIn...' : 'Copy & Open LinkedIn'}
                </Button>
              ) : (
                <Button onClick={copyMessage} className="flex-1" aria-label="Copy drafted message to clipboard">
                  {copied ? 'Copied!' : 'Copy Message'}
                </Button>
              )}
              {linkedinUrl && (
                <Button variant="secondary" onClick={copyMessage} aria-label="Copy drafted message to clipboard">
                  {copied ? 'Copied!' : 'Copy Only'}
                </Button>
              )}
            </div>

            {/* Divider */}
            <div className="border-t border-border" />

            {/* Confirm sent */}
            <div className="text-center">
              <p className="mb-2 text-xs text-muted-foreground">
                After you've sent the introduction, confirm below.
              </p>
              {error && (
                <p className="mb-2 rounded-md bg-red-500/10 p-2 text-sm text-red-400">{error}</p>
              )}
              <Button
                variant="secondary"
                onClick={handleConfirmSent}
                loading={confirming}
                disabled={confirming}
                className="w-full"
                aria-label="Confirm that you have sent the introduction"
              >
                I've Sent It
              </Button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
