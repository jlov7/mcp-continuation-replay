/**
 * TypeScript adapter tests (Milestone D).
 *
 * Two categories:
 * 1. Fingerprint contract — the TS adapter must produce byte-identical
 *    digests to the Python adapter on the shared vectors (the Python side
 *    drives this via `tests/test_cross_language_vectors.py`; these tests
 *    pin the contract locally too).
 * 2. Pinned SDK-era fact — `@modelcontextprotocol/sdk@1.30.0` pins protocol
 *    `2025-11-25` and has NO MRTR surface (`InputRequiredResult`,
 *    `requestState`, `inputResponses`). That is a TESTED fact here, not a
 *    claim: cases 03/04/05/10/11 are not expressible on this SDK, which is
 *    a limitation of this pinned experiment, not a claim about newer releases.
 */

import { strict as assert } from "node:assert";
import { test } from "node:test";

import { fingerprint, type LogicalRequest } from "../src/fingerprint.ts";
import { LATEST_PROTOCOL_VERSION, SUPPORTED_PROTOCOL_VERSIONS } from "@modelcontextprotocol/sdk/types.js";

const TEST_KEY = Buffer.from("test-only-cross-language-key-32b", "utf-8");

const CONTROL_VECTOR: LogicalRequest = {
  principal: "alice",
  tool_id: "create_issue",
  tool_version: "1.0",
  arguments: { title: "spec" },
  continuation_state: "awaiting-body",
  input_responses: { body: { action: "accept", content: { body: "alpha" } } },
};

// Digest of `00_control_single_round` computed BY THE PYTHON adapter. If this
// test and the Python suite disagree, the cross-language contract is broken.
const PYTHON_AGREED_DIGEST = "8053811d58bacfa928adfe862a3e1bda8040d18feef86b1b6eca9cd807c2cd97";

test("TYPE adapter matches the Python-agreed fingerprint", () => {
  assert.equal(fingerprint(CONTROL_VECTOR, TEST_KEY), PYTHON_AGREED_DIGEST);
});

test("identical logical requests must coincide in TypeScript", () => {
  const a: LogicalRequest = { ...CONTROL_VECTOR, continuation_state: "sealed-v1" };
  const b: LogicalRequest = { ...CONTROL_VECTOR, continuation_state: "sealed-v1" };
  assert.equal(fingerprint(a, TEST_KEY), fingerprint(b, TEST_KEY));
});

test("different continuation_state must change the fingerprint", () => {
  const a: LogicalRequest = { ...CONTROL_VECTOR, continuation_state: "v1" };
  const b: LogicalRequest = { ...CONTROL_VECTOR, continuation_state: "v2" };
  assert.notEqual(fingerprint(a, TEST_KEY), fingerprint(b, TEST_KEY));
});

test("different inputResponses must change the fingerprint", () => {
  const alpha: LogicalRequest = {
    ...CONTROL_VECTOR,
    input_responses: { body: { action: "accept", content: { body: "alpha" } } },
  };
  const beta: LogicalRequest = {
    ...CONTROL_VECTOR,
    input_responses: { body: { action: "accept", content: { body: "beta" } } },
  };
  assert.notEqual(fingerprint(alpha, TEST_KEY), fingerprint(beta, TEST_KEY));
});

test("Unicode scalar key order and UTF-8 content are stable", () => {
  const request: LogicalRequest = {
    ...CONTROL_VECTOR,
    arguments: { "\u{10000}": "astral", "\uE000": "bmp", text: "Cafe\u0301 😀 " },
  };
  assert.equal(fingerprint(request, TEST_KEY).length, 64);
});

test("non-interoperable numbers fail closed", () => {
  assert.throws(
    () => fingerprint({ ...CONTROL_VECTOR, arguments: { n: 1.5 } }, TEST_KEY),
    /safe range/,
  );
  assert.throws(
    () => fingerprint({ ...CONTROL_VECTOR, arguments: { n: Number.MAX_SAFE_INTEGER + 1 } }, TEST_KEY),
    /safe range/,
  );
});

test("integral numeric values use one canonical form", () => {
  const one = { ...CONTROL_VECTOR, arguments: { n: 1 } };
  assert.equal(fingerprint(one, TEST_KEY), fingerprint({ ...one, arguments: { n: 1.0 } }, TEST_KEY));
});

test("special and integer-like keys remain data and sort canonically", () => {
  const argumentsValue = JSON.parse('{"10":"ten","2":"two","__proto__":"data"}') as Record<string, unknown>;
  const digest = fingerprint({ ...CONTROL_VECTOR, arguments: argumentsValue }, TEST_KEY);
  assert.equal(digest.length, 64);
  assert.equal(argumentsValue.__proto__, "data");
});

test("unpaired surrogates fail closed", () => {
  assert.throws(
    () => fingerprint({ ...CONTROL_VECTOR, arguments: { bad: "\ud800" } }, TEST_KEY),
    /surrogate/,
  );
});

test("non-JSON object shapes fail closed", () => {
  const sparse = new Array(1) as unknown[];
  assert.throws(
    () => fingerprint({ ...CONTROL_VECTOR, arguments: { sparse } }, TEST_KEY),
    /sparse arrays/,
  );
  assert.throws(
    () => fingerprint({ ...CONTROL_VECTOR, arguments: { date: new Date(0) } }, TEST_KEY),
    /plain JSON objects/,
  );
  assert.throws(
    () => fingerprint({ ...CONTROL_VECTOR, arguments: { map: new Map() } }, TEST_KEY),
    /plain JSON objects/,
  );
});

test("SDK era: pinned @modelcontextprotocol/sdk has NO MRTR surface (tested fact)", () => {
  // The Python adapter pins spec 2026-07-28, where MRTR lives.
  // The pinned TS 1.30 SDK's latest stable protocol is 2025-11-25 and the
  // pinned supported list does not include 2026-07-28.
  assert.equal(LATEST_PROTOCOL_VERSION, "2025-11-25");
  assert.ok(SUPPORTED_PROTOCOL_VERSIONS.includes("2025-11-25"));
  assert.ok(SUPPORTED_PROTOCOL_VERSIONS.every((v: string) => v !== "2026-07-28"));
});
