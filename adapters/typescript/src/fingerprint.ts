/**
 * The operation fingerprint — the cross-language equivalence contract.
 *
 * Protocol §1 binds an operation by five components:
 *
 *     principal  ⊗  tool_id/version  ⊗  canonical(arguments)
 *                ⊗  continuation_state
 *                ⊗  input_responses
 *
 * This file MUST produce byte-identical digests to
 * `src/continuation_replay/fingerprint.py` for every logical request. The
 * canonicalization is declared and shared; there is no language-specific
 * wiggle room:
 * - objects use Unicode scalar-value key order, compact separators, UTF-8;
 * - numbers must be integral and within JavaScript's safe range;
 * - opaque/stateful fields (`continuation_state`, `input_responses`) are
 *   bound through HMAC-SHA256 with a caller-supplied deployment key;
 * - the SHA-256 of the canonical payload is the fingerprint digest.
 *
 * NOTE ON THE SDK ERA: `@modelcontextprotocol/sdk@1.30.0` pins protocol
 * `2025-11-25` — there is NO `InputRequiredResult`, `requestState`, or
 * `inputResponses` surface in it. The fingerprint here is OUR contract (it
 * canonicalizes a logical request), independent of what the SDK ships. See
 * `research/` for the SDK-era finding.
 */

import { createHash, createHmac } from "node:crypto";

const OPAQUE_FIELDS = ["continuation_state", "input_responses"] as const;

export interface LogicalRequest {
  principal: string | null;
  tool_id: string;
  tool_version: string;
  arguments: Record<string, unknown>;
  continuation_state?: string | null;
  input_responses?: Record<string, unknown>;
}

function compareUnicodeScalars(a: string, b: string): number {
  const aa = Array.from(a, (c) => c.codePointAt(0)!);
  const bb = Array.from(b, (c) => c.codePointAt(0)!);
  for (let i = 0; i < Math.min(aa.length, bb.length); i += 1) {
    if (aa[i]! !== bb[i]!) return aa[i]! - bb[i]!;
  }
  return aa.length - bb.length;
}

function validateString(value: string, path: string): void {
  for (let i = 0; i < value.length; i += 1) {
    const unit = value.charCodeAt(i);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = value.charCodeAt(i + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) {
        throw new Error(`${path}: unpaired UTF-16 surrogate is not valid Unicode`);
      }
      i += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      throw new Error(`${path}: unpaired UTF-16 surrogate is not valid Unicode`);
    }
  }
}

function canonicalText(value: unknown, path = "$"): string {
  if (value === null) return "null";
  if (value === true) return "true";
  if (value === false) return "false";
  if (typeof value === "string") {
    validateString(value, path);
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) {
      throw new Error(`${path}: number must be an integer in the interoperable safe range`);
    }
    return String(value);
  }
  if (Array.isArray(value)) {
    for (let index = 0; index < value.length; index += 1) {
      if (!(index in value)) throw new Error(`${path}[${index}]: sparse arrays are not JSON`);
    }
    return `[${value.map((item, index) => canonicalText(item, `${path}[${index}]`)).join(",")}]`;
  }
  if (typeof value === "object") {
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) {
      throw new Error(`${path}: only plain JSON objects are supported`);
    }
    const source = value as Record<string, unknown>;
    const entries = Object.keys(source)
      .sort(compareUnicodeScalars)
      .map((key) => {
        validateString(key, `${path}.<key>`);
        const item = source[key];
        if (item === undefined) throw new Error(`${path}.${key}: undefined is not JSON`);
        return `${JSON.stringify(key)}:${canonicalText(item, `${path}.${key}`)}`;
      });
    return `{${entries.join(",")}}`;
  }
  throw new Error(`${path}: unsupported JSON value ${typeof value}`);
}

/** UTF-8 canonical bytes: sorted keys, compact separators. Matches Python. */
function canonicalBytes(value: unknown): Buffer {
  return Buffer.from(canonicalText(value), "utf-8");
}

/** Keyed digest of an opaque field — leaks equality, not the state bytes. */
function bindOpaque(fieldName: string, value: unknown, key: Buffer): string {
  const msg = Buffer.concat([
    Buffer.from(fieldName, "utf-8"),
    Buffer.from([0x00]),
    canonicalBytes(value),
  ]);
  return createHmac("sha256", key).update(msg).digest("hex");
}

/** Canonical SHA-256 over the five bound components. Must match Python. */
export function fingerprint(request: LogicalRequest, key: Buffer): string {
  if (key.byteLength < 32) throw new Error("fingerprint key must contain at least 32 bytes");
  const payload: Record<string, unknown> = {
    principal: request.principal,
    tool_id: request.tool_id,
    tool_version: request.tool_version,
    arguments: request.arguments,
  };
  for (const f of OPAQUE_FIELDS) {
    const value = (request as unknown as Record<string, unknown>)[f];
    payload[f] = bindOpaque(f, value ?? null, key);
  }
  return createHash("sha256").update(canonicalBytes(payload)).digest("hex");
}
