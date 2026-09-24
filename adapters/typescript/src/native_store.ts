/** Independent bounded operation/effect store. Node SQLite; no Python bridge. */
import { DatabaseSync } from 'node:sqlite';

export type Identity = { operationId: string; principal: string; backend: string };
export type NativeResult = { state: 'applied'; effectId: number; result: string; replayed: boolean };
export type NativeStatus = {
  state: 'applied' | 'unknown';
  effectId: number | null;
  storedResult: string | null;
  freshWriteAuthorized: false;
};

export class NativeStore {
  private readonly db: DatabaseSync;
  readonly backend: string;

  constructor(path: string, backend: string) {
    if (!backend) throw new Error('backend required');
    this.db = new DatabaseSync(path, { timeout: 3000 });
    this.db.exec('PRAGMA journal_mode = WAL');
    this.db.exec(`CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS effects (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, body TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS operations (
        operation_id TEXT PRIMARY KEY, principal TEXT NOT NULL, backend TEXT NOT NULL,
        fingerprint TEXT NOT NULL, state TEXT NOT NULL, effect_id INTEGER NOT NULL,
        result TEXT NOT NULL, replay_expires_at REAL NOT NULL,
        FOREIGN KEY(effect_id) REFERENCES effects(id));`);
    this.db.prepare("INSERT OR IGNORE INTO metadata(key,value) VALUES ('backend',?)").run(backend);
    const row = this.db.prepare("SELECT value FROM metadata WHERE key='backend'").get() as { value: string };
    if (row.value !== backend) throw new Error('backend binding mismatch');
    this.backend = backend;
  }

  close(): void { this.db.close(); }

  status(identity: Identity): NativeStatus {
    if (identity.backend !== this.backend) throw new Error('backend binding mismatch');
    const row = this.db.prepare(`SELECT o.principal, o.backend, o.state, o.effect_id,
      o.result, e.id AS physical_id FROM operations o
      LEFT JOIN effects e ON e.id=o.effect_id WHERE o.operation_id=?`).get(identity.operationId) as
      | { principal: string; backend: string; state: string; effect_id: number; result: string; physical_id: number | null }
      | undefined;
    if (!row || row.principal !== identity.principal || row.backend !== identity.backend ||
        row.state !== 'applied' || row.physical_id !== row.effect_id) {
      return { state: 'unknown', effectId: null, storedResult: null, freshWriteAuthorized: false };
    }
    return { state: 'applied', effectId: row.effect_id, storedResult: row.result, freshWriteAuthorized: false };
  }

  apply(identity: Identity, fingerprint: string, title: string, body: string,
        now: number, replayExpiresAt: number, afterBegin?: () => void): NativeResult {
    if (!identity || typeof identity.operationId !== 'string' || !identity.operationId ||
        typeof identity.principal !== 'string' || !identity.principal ||
        identity.backend !== this.backend || typeof fingerprint !== 'string' || !fingerprint ||
        typeof title !== 'string' || !title || typeof body !== 'string' ||
        !Number.isFinite(now) || !Number.isFinite(replayExpiresAt)) {
      throw new Error('invalid operation');
    }
    this.db.exec('BEGIN IMMEDIATE');
    try {
      afterBegin?.();
      const existing = this.db.prepare('SELECT * FROM operations WHERE operation_id=?').get(identity.operationId) as
        | { principal: string; backend: string; fingerprint: string; state: string;
            effect_id: number; result: string; replay_expires_at: number }
        | undefined;
      if (existing) {
        if (existing.principal !== identity.principal || existing.backend !== identity.backend ||
            existing.fingerprint !== fingerprint) throw new Error('operation_conflict');
        // The fingerprint also binds continuation fields supplied by the caller. Check the
        // persisted effect inputs independently so a stale fingerprint cannot replay a
        // different title/body as if that request had succeeded.
        const effect = this.db.prepare('SELECT title, body FROM effects WHERE id=?').get(existing.effect_id) as
          | { title: string; body: string } | undefined;
        if (effect && (effect.title !== title || effect.body !== body)) throw new Error('operation_conflict');
        if (now >= existing.replay_expires_at) throw new Error('operation_retention_expired');
        if (existing.state !== 'applied') throw new Error('operation_in_progress');
        if (!effect) throw new Error('missing_effect');
        this.db.exec('COMMIT');
        return { state: 'applied', effectId: existing.effect_id, result: existing.result, replayed: true };
      }
      if (now >= replayExpiresAt) throw new Error('operation_retention_expired');
      const inserted = this.db.prepare('INSERT INTO effects(title,body) VALUES (?,?)').run(title, body);
      const effectId = Number(inserted.lastInsertRowid);
      const result = `created ${effectId}`;
      this.db.prepare(`INSERT INTO operations(operation_id,principal,backend,fingerprint,state,effect_id,result,replay_expires_at)
        VALUES (?,?,?,?,'applied',?,?,?)`).run(
          identity.operationId, identity.principal, identity.backend, fingerprint,
          effectId, result, replayExpiresAt);
      this.db.exec('COMMIT');
      return { state: 'applied', effectId, result, replayed: false };
    } catch (error) {
      this.db.exec('ROLLBACK');
      throw error;
    }
  }
}
