/**
 * CLI bridge for cross-language tests: read LogicalRequests on stdin (one
 * JSON per line), print `name<TAB>fingerprint` per line. The Python test
 * calls this to prove both languages agree on shared vectors.
 */

import { fingerprint, type LogicalRequest } from "./fingerprint.ts";

function fail(message: string): never {
  console.error(`fingerprint-cli: ${message}`);
  process.exit(2);
}

const lines: string[] = [];
const keyHex = process.env.CONTINUATION_REPLAY_FINGERPRINT_KEY_HEX;
if (keyHex === undefined || !/^[0-9a-fA-F]{64,}$/.test(keyHex) || keyHex.length % 2 !== 0) {
  fail("CONTINUATION_REPLAY_FINGERPRINT_KEY_HEX must be an even-length hex key of at least 32 bytes");
}
const key = Buffer.from(keyHex, "hex");
for await (const chunk of process.stdin) {
  lines.push(String(chunk));
}

for (const raw of lines.join("").split("\n")) {
  if (raw.trim() === "") continue;
  let entry: unknown;
  try {
    entry = JSON.parse(raw);
  } catch {
    fail(`unparseable JSON: ${raw.slice(0, 80)}`);
  }
  const { name, request } = entry as { name: string; request: LogicalRequest };
  if (typeof name !== "string" || typeof request !== "object" || request === null) {
    fail("each line must be {name, request}");
  }
  let digest: string;
  try {
    digest = fingerprint(request, key);
  } catch (error) {
    fail(error instanceof Error ? error.message : "fingerprint failed");
  }
  process.stdout.write(`${name}\t${digest}\n`);
}
