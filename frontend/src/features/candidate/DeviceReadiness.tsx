import { useEffect, useState } from 'react';
import { api } from '../../services/api';

interface Check { label: string; passed: boolean; detail: string }

async function probeStorage(): Promise<void> {
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    let blocked = false;
    const request = indexedDB.open('cck-device-readiness', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('probe');
    request.onerror = () => reject(new Error('Storage is unavailable.'));
    request.onblocked = () => { blocked = true; reject(new Error('Storage is blocked by another window.')); };
    request.onsuccess = () => { if (blocked) request.result.close(); else resolve(request.result); };
  });
  try {
    const key = crypto.randomUUID();
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction('probe', 'readwrite');
      const store = transaction.objectStore('probe');
      store.put('ready', key);
      const read = store.get(key);
      read.onsuccess = () => {
        if (read.result !== 'ready') transaction.abort();
        else store.delete(key);
      };
      transaction.oncomplete = () => resolve();
      transaction.onerror = transaction.onabort = () => reject(new Error('Recovery storage is not writable.'));
    });
  } finally { db.close(); }
}

/** Readiness guidance only. No candidate data, exam clocks, or permissions are changed. */
export function DeviceReadiness() {
  const [checks, setChecks] = useState<Check[] | null>(null);
  const [pending, setPending] = useState(false);
  const [run, setRun] = useState(0);
  useEffect(() => {
    let active = true;
    setPending(true);
    const timer = window.setTimeout(() => {
      if (active) { setChecks([{ label: 'Device checks', passed: false, detail: 'Checks timed out. Close other test tabs and retry.' }]); setPending(false); }
      active = false;
    }, 8000);
    void (async () => {
      const hasLocks = typeof navigator.locks?.request === 'function';
      const results: Check[] = [
        { label: 'Secure browser context', passed: window.isSecureContext, detail: window.isSecureContext ? 'Secure context available.' : 'Open the official HTTPS test address in a supported browser.' },
        { label: 'Single-tab protection', passed: hasLocks, detail: hasLocks ? 'Browser supports safe exam-tab coordination.' : 'Use an updated supported desktop browser with Web Locks.' },
      ];
      try { await probeStorage(); results.push({ label: 'Answer recovery storage', passed: true, detail: 'Browser storage can save and read recovery data.' }); }
      catch { results.push({ label: 'Answer recovery storage', passed: false, detail: 'Enable site storage and leave private browsing. Ask your proctor for help before starting.' }); }
      try { const health = await api<{ status: string }>('/health/ready'); if (health.status !== 'ready') throw new Error(); results.push({ label: 'Exam service connection', passed: true, detail: 'The server is reachable and ready.' }); }
      catch { results.push({ label: 'Exam service connection', passed: false, detail: 'Cannot reach a ready exam service. Check your connection and ask your proctor before starting.' }); }
      if (active) { window.clearTimeout(timer); setChecks(results); setPending(false); }
    })();
    return () => { active = false; window.clearTimeout(timer); };
  }, [run]);
  const ready = !pending && !!checks?.every((check) => check.passed);
  return <section aria-labelledby="readiness-heading" aria-busy={pending}>
    <h2 id="readiness-heading">Device and connection readiness</h2>
    <p>Use an updated desktop browser. Keep one exam tab open and connect your laptop to power.</p>
    {pending ? <p role="status">Checking this browser and the exam service…</p> : <>
      <p role="status">{ready ? 'Checks passed. Wait for your proctor before starting.' : 'Resolve the checks below before starting your test.'}</p>
      <dl>{checks?.map((check) => <div key={check.label}><dt><strong>{check.label}: {check.passed ? 'Passed' : 'Needs attention'}</strong></dt><dd>{check.detail}</dd></div>)}</dl>
    </>}
    <button type="button" className="secondary-button" disabled={pending} onClick={() => setRun((value) => value + 1)}>Run checks again</button>
    <p>These checks confirm current browser capabilities and server contact. They cannot guarantee continuous connectivity or recover work after the server deadline.</p>
  </section>;
}
