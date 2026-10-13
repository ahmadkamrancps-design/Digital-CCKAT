import { CircleAlert, CircleCheck, CloudOff, LoaderCircle } from 'lucide-react';
import type { SaveState } from '../types/exam';

const labels: Record<SaveState, string> = {
  idle: 'No answers saved yet',
  saving: 'Saving…',
  saved: 'Saved',
  offline: 'Offline / waiting to sync',
  error: 'Sync problem',
};

const icons = {
  idle: CircleAlert, saving: LoaderCircle, saved: CircleCheck,
  offline: CloudOff, error: CircleAlert,
};

/** Caller must use "saved" only after a successful backend acknowledgement. */
export function SaveStatus({ status }: { status: SaveState }) {
  const Icon = icons[status];
  return <span className={`save-status save-status-${status}`} role="status" aria-live="polite" aria-atomic="true">
    <Icon size={16} aria-hidden="true" /> {labels[status]}
  </span>;
}
