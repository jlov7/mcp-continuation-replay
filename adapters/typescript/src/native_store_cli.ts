/** One JSON request per process, for hard-exit and concurrency cells. */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { NativeStore, type Identity } from './native_store.ts';

type Input = {
  db: string; backend: string; op: 'apply' | 'status'; identity: Identity;
  fingerprint?: string; title?: string; body?: string; now?: number;
  replayExpiresAt?: number; dropReply?: boolean;
  holdTransactionPath?: string; peerAttemptPath?: string; signalBeforeApplyPath?: string;
  readyPath?: string; startWhenPath?: string;
};

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function nonempty(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0;
}

function parseInput(value: unknown): Input {
  if (!record(value) || !nonempty(value.db) || !nonempty(value.backend) ||
      (value.op !== 'apply' && value.op !== 'status') || !record(value.identity) ||
      !nonempty(value.identity.operationId) || !nonempty(value.identity.principal) ||
      !nonempty(value.identity.backend)) throw new Error('invalid native store request');
  if (value.op === 'apply' &&
      (!nonempty(value.fingerprint) || !nonempty(value.title) ||
       typeof value.body !== 'string' || typeof value.now !== 'number' ||
       !Number.isFinite(value.now) || typeof value.replayExpiresAt !== 'number' ||
       !Number.isFinite(value.replayExpiresAt))) throw new Error('invalid apply request');
  if (value.dropReply !== undefined && typeof value.dropReply !== 'boolean')
    throw new Error('invalid dropReply');
  for (const name of ['holdTransactionPath', 'peerAttemptPath', 'signalBeforeApplyPath',
                      'readyPath', 'startWhenPath']) {
    if (value[name] !== undefined && !nonempty(value[name])) throw new Error(`invalid ${name}`);
  }
  if ((value.holdTransactionPath === undefined) !== (value.peerAttemptPath === undefined) ||
      (value.readyPath === undefined) !== (value.startWhenPath === undefined))
    throw new Error('incomplete native store barrier');
  return value as Input;
}

const input = parseInput(JSON.parse(readFileSync(0, 'utf8')));
const store = new NativeStore(input.db, input.backend);
try {
  if (input.readyPath && input.startWhenPath) {
    writeFileSync(input.readyPath, 'ready');
    const deadline = Date.now() + 8000;
    while (!existsSync(input.startWhenPath) && Date.now() < deadline) { /* wait for first writer */ }
    if (!existsSync(input.startWhenPath)) throw new Error('start barrier timed out');
  }
  if (input.signalBeforeApplyPath) writeFileSync(input.signalBeforeApplyPath, 'attempting');
  const afterBegin = input.holdTransactionPath && input.peerAttemptPath ? () => {
    writeFileSync(input.holdTransactionPath!, 'holding');
    const deadline = Date.now() + 3000;
    while (!existsSync(input.peerAttemptPath!) && Date.now() < deadline) { /* wait for contender */ }
    if (!existsSync(input.peerAttemptPath!)) throw new Error('concurrency barrier timed out');
    const releaseAt = Date.now() + 200;
    while (Date.now() < releaseAt) { /* contender attempts BEGIN while this writer holds */ }
  } : undefined;
  const result = input.op === 'status' ? store.status(input.identity) : store.apply(
    input.identity, input.fingerprint!, input.title!, input.body!, input.now!, input.replayExpiresAt!, afterBegin);
  if (input.dropReply) process.exit(70);
  process.stdout.write(JSON.stringify(result));
} catch (error) {
  process.stderr.write(String(error));
  process.exitCode = 1;
} finally {
  store.close();
}
