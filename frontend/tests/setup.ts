import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach } from 'vitest';
import { IDBFactory, IDBKeyRange } from 'fake-indexeddb';
import { TestLocks } from './browser-storage';

let locks: TestLocks;
beforeEach(() => {
  Object.defineProperty(globalThis, 'indexedDB', { configurable: true, writable: true, value: new IDBFactory() });
  Object.defineProperty(globalThis, 'IDBKeyRange', { configurable: true, writable: true, value: IDBKeyRange });
  locks = new TestLocks();
  Object.defineProperty(navigator, 'locks', { configurable: true, value: locks });
});
afterEach(async () => { cleanup(); await locks.idle(); });
