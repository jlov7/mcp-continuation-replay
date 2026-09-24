"""Twelve-case conformance pre-sweep against `mcp==2.2.0`.

Passing property tests record what the pinned SDK boundary enforces. Tests marked
`pinned_finding` are exact witnesses of the deliberately unmediated server's
observed behavior. They pass only while the named mechanism remains exact; a
machinery error or changed result fails normally. Case 09 lives in the wire suite.

Transport: in-process `Client(mcp)`. NOT wire-level. See STATUS.md.
"""

from __future__ import annotations

from typing import Any, cast

import anyio
import pytest
from mcp import Client
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.request_state import RequestStateSecurity
from mcp.shared.exceptions import MCPError
from mcp_types import (
    CallToolResult,
    ElicitRequest,
    ElicitRequestFormParams,
    ElicitResult,
    InputRequiredResult,
)

from reference.backend import IssueStore, WatcherInsertFailed
from reference.readback import ReadBack

pytestmark = pytest.mark.anyio

_KEY = b"0123456789abcdef0123456789abcdef"
_TITLE = "sweep"


def _ask(title: str) -> ElicitRequest:
    return ElicitRequest(
        params=ElicitRequestFormParams(
            message=f"Body for {title}?",
            requested_schema={
                "type": "object",
                "properties": {"body": {"type": "string"}},
                "required": ["body"],
            },
        )
    )


def _accept(body: str) -> ElicitResult:
    return ElicitResult(action="accept", content={"body": body})


def _extract_body(responses: Any) -> str:
    resp = responses["body"]
    content = getattr(resp, "content", None)
    if content is None and isinstance(resp, dict):
        content = resp.get("content")
    return str(content.get("body", "")) if isinstance(content, dict) else ""


def _server(
    store: IssueStore,
    *,
    ttl: float = 600.0,
    bind_principal=None,
) -> MCPServer:
    mcp = MCPServer(
        "conformance-sweep",
        request_state_security=RequestStateSecurity(
            keys=[_KEY], ttl=ttl, bind_principal=bind_principal
        ),
    )

    @mcp.tool()
    async def create_issue(title: str, ctx: Context) -> str | InputRequiredResult:
        if ctx.input_responses is None:
            return InputRequiredResult(
                input_requests={"body": _ask(title)}, request_state="awaiting-body"
            )
        issue_id = store.create_issue(title, body=_extract_body(ctx.input_responses))
        return f"created {issue_id}"

    return mcp


async def _round_one(client: Client, title: str = _TITLE) -> str:
    first = await client.session.call_tool(
        "create_issue", {"title": title}, allow_input_required=True
    )
    assert isinstance(first, InputRequiredResult)
    assert first.request_state is not None
    return first.request_state


async def _commit(client: Client, token: str, body: str, title: str = _TITLE):
    return await client.session.call_tool(
        "create_issue",
        {"title": title},
        input_responses={"body": _accept(body)},
        request_state=token,
        allow_input_required=True,
    )


# --- Case 1 / Case 3 share a root cause: no consumed-token record ---------------------


@pytest.mark.pinned_finding(mechanism="duplicate_effect")
async def test_case_01_identical_retry_returns_the_same_logical_result(
    store: IssueStore, readback: ReadBack
) -> None:
    """PINNED WITNESS: the unmediated server dispatches two identical retries."""
    mcp = _server(store)
    async with Client(mcp) as client:
        token = await _round_one(client)
        await _commit(client, token, "alpha")
        await _commit(client, token, "alpha")
    observed = readback.observe_by_title(_TITLE, operation_id="case-01")
    assert observed.effects == 2 and observed.matching_ids == (1, 2)


@pytest.mark.pinned_finding(mechanism="duplicate_effect")
async def test_case_03_reply_lost_replay_does_not_create_a_second_record(
    store: IssueStore, readback: ReadBack
) -> None:
    """PINNED WITNESS: modelled reply loss plus replay dispatches twice."""
    mcp = _server(store)
    async with Client(mcp) as client:
        token = await _round_one(client)
        first = await _commit(client, token, "alpha")
        assert isinstance(first, CallToolResult)
        await _commit(client, token, "alpha")
    observed = readback.observe_by_title(_TITLE, operation_id="case-03")
    assert observed.effects == 2 and observed.matching_ids == (1, 2)


@pytest.mark.pinned_finding(mechanism="changed_input_dispatched")
async def test_case_04_changed_input_responses_conflicts_before_dispatch(
    store: IssueStore, readback: ReadBack
) -> None:
    """PINNED WITNESS: changed inputResponses reaches the unmediated handler."""
    mcp = _server(store)
    async with Client(mcp) as client:
        token = await _round_one(client)
        await _commit(client, token, "alpha")
        conflicted = False
        try:
            await _commit(client, token, "beta")
        except MCPError:
            conflicted = True
    beta = readback.observe_by_body("beta", operation_id="case-04")
    assert not conflicted
    assert beta.effects == 1 and readback.total() == 2


# --- Cases the SDK appears to enforce -------------------------------------------------


async def test_case_02_continuation_never_admitted_leaves_no_effect(
    store: IssueStore, readback: ReadBack
) -> None:
    """SAFE: if the continuation is never sent, nothing is applied."""
    mcp = _server(store)
    async with Client(mcp) as client:
        await _round_one(client)
    assert readback.total() == 0


async def test_case_05_tampered_request_state_is_rejected(
    store: IssueStore, readback: ReadBack
) -> None:
    """SAFE: a tampered token must be rejected before dispatch."""
    mcp = _server(store)
    async with Client(mcp) as client:
        token = await _round_one(client)
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        rejected = False
        try:
            await _commit(client, tampered, "alpha")
        except MCPError:
            rejected = True
    assert rejected and readback.total() == 0, "case 05: tampered token dispatched"


async def test_case_05b_changed_arguments_are_rejected(
    store: IssueStore, readback: ReadBack
) -> None:
    """SAFE: same token replayed against different args is rejected."""
    mcp = _server(store)
    async with Client(mcp) as client:
        token = await _round_one(client, "sweep-a")
        rejected = False
        try:
            await _commit(client, token, "alpha", title="sweep-b")
        except MCPError:
            rejected = True
    assert rejected and readback.total() == 0, "case 05b: token replayed across arguments"


async def test_case_07_expired_request_state_cannot_become_fresh_write_authority(
    store: IssueStore, readback: ReadBack
) -> None:
    """SAFE: after TTL expiry the token is refused; read-back cannot become write authority."""
    mcp = _server(store, ttl=0.15)
    async with Client(mcp) as client:
        token = await _round_one(client)
        await anyio.sleep(0.25)
        rejected = False
        try:
            await _commit(client, token, "alpha")
        except MCPError:
            rejected = True
    assert rejected and readback.total() == 0, "case 07: expired token dispatched"


async def test_case_10_expired_token_does_not_silently_extend_the_guarantee(
    store: IssueStore, readback: ReadBack
) -> None:
    """SAFE: a stale key must not create a new effect under a safe-replay appearance.

    Also records the *visibility* question: the wire error is a frozen generic
    `invalid_request_state` with the real reason log-only, so a consumer cannot
    distinguish "expired" from "tampered" from the wire alone.
    """
    mcp = _server(store, ttl=0.15)
    async with Client(mcp) as client:
        token = await _round_one(client)
        await anyio.sleep(0.25)
        try:
            await _commit(client, token, "alpha")
        except MCPError as exc:
            reasons = {getattr(exc, "message", ""), str(getattr(exc, "data", ""))}
            assert "invalid_request_state" in " ".join(reasons) or "Invalid or expired" in " ".join(
                reasons
            )
    assert readback.total() == 0


@pytest.mark.pinned_finding(mechanism="stripped_state_dispatched")
async def test_case_11_stripped_metadata_is_not_false_conformance(
    store: IssueStore, readback: ReadBack
) -> None:
    """PINNED WITNESS: stripped requestState reaches the unmediated handler.

    `RequestStateBoundary.__call__` treats an absent requestState as "nothing to
    verify" and passes through. So a stripped token should dispatch again.
    """
    mcp = _server(store)
    async with Client(mcp) as client:
        await _round_one(client)
        # Metadata stripped in transit: the retry arrives with no request_state.
        await client.session.call_tool(
            "create_issue",
            {"title": _TITLE},
            input_responses={"body": _accept("alpha")},
            allow_input_required=True,
        )
    observed = readback.observe_by_title(_TITLE, operation_id="case-11")
    assert observed.effects == 1 and observed.matching_ids == (1,)


# --- Cases that needed infrastructure — now swept -------------------------------------


async def test_case_06_different_principal_is_not_an_equivalent_retry(
    store: IssueStore, readback: ReadBack
) -> None:
    """SAFE: a sealed token is bound to the principal that minted it.

    The reference transport (stdio) is unauthenticated, so the default binder
    yields `None` on every request and case 06 is vacuous there — proven
    separately in `test_case_06b_principal_binding_is_none_on_stdio`. This
    test exercises the mechanism itself with a principal present: when the
    binding principal changes between rounds, the sealed token must be
    rejected as principal drift BEFORE dispatch.
    """
    holder: dict[str, str | None] = {"principal": "alice"}

    def bind_principal(ctx: Any) -> str | None:
        return holder["principal"]

    mcp = _server(store, bind_principal=bind_principal)
    async with Client(mcp) as client:
        token = await _round_one(client)
        holder["principal"] = "bob"
        rejected = False
        try:
            await _commit(client, token, "alpha")
        except MCPError:
            rejected = True
    assert rejected and readback.total() == 0, (
        "case 06: token minted by alice was honored by bob — principal drift did not conflict"
    )


def test_case_06b_principal_binding_is_none_on_stdio() -> None:
    """Case 06 on the reference transport is vacuous — AND tested, not assumed.

    `authenticated_principal` reads an auth contextvar that only auth
    middleware populates. Stdio carries no OAuth middleware, so every request
    binds principal `None`. Two requests therefore present identical principal
    claims on the reference transport, which is exactly why case 06 cannot be
    exercised there.
    """
    from typing import Any

    from mcp.server.auth.middleware.auth_context import get_access_token
    from mcp.server.request_state import authenticated_principal

    assert get_access_token() is None
    # The SDK's default binder reads ONLY the auth contextvar (verified in
    # request_state.py:80-92); the ctx argument is unused, so a cast is safe.
    assert authenticated_principal(cast(Any, object())) is None


@pytest.mark.pinned_finding(mechanism="duplicate_effect")
async def test_case_08_concurrent_identical_attempts_yield_one_effect(
    store: IssueStore, readback: ReadBack
) -> None:
    """PINNED WITNESS: concurrent continuations dispatch two backend effects.

    Declared waiter semantics: both attempts are issued concurrently and both
    settle before observation — there is no polling loop. The read-back oracle
    then counts effects. On the pinned SDK this FAILS (two effects), a finding
    sharing the cases 01/03 root cause: no consumed-token record.
    """
    mcp = _server(store)
    async with Client(mcp) as client:
        token = await _round_one(client)
        tasks = [
            client.session.call_tool(
                "create_issue",
                {"title": _TITLE},
                input_responses={"body": _accept("alpha")},
                request_state=token,
                allow_input_required=True,
            )
            for _ in range(2)
        ]
        results = await anyio.gather(*tasks)
        assert all(r is not None for r in results)
    observed = readback.observe_by_title(_TITLE, operation_id="case-08")
    assert observed.effects == 2 and observed.matching_ids == (1, 2)


async def test_case_12_partial_effect_and_failed_compensation_preserve_both_records(
    store: IssueStore, readback: ReadBack
) -> None:
    """SAFE: a partial effect stays visible, and its failed compensation is
    preserved as a SEPARATE identity — the original is never rewritten.

    `create_issue_with_watcher(fail_watcher=True)` commits the issue then
    raises, modelling a partial effect. The compensation then fails too. Both
    records must survive; the unresolved state must read back as `partial`.
    """
    title = "sweep-partial"
    watcher = "audit@example.test"
    try:
        store.create_issue_with_watcher(title, "alpha", watcher, fail_watcher=True)
        raise AssertionError("case 12: WatcherInsertFailed was expected")
    except WatcherInsertFailed:
        pass

    observed = readback.observe_issue_with_watcher(title, watcher, operation_id="case-12")
    assert observed.state == "partial", f"case 12: expected partial, got {observed.state}"
    assert observed.effects == 1

    issue_id = observed.matching_ids[0]
    comp_id = store.record_compensation(issue_id, kind="manual-correction", outcome="failed")
    comps = readback.compensations_for(issue_id)
    assert len(comps) == 1, "case 12: compensation record lost"
    assert comps[0].id == comp_id and comps[0].outcome == "failed"

    original = store.get_issue(issue_id)
    assert original is not None and original.body == "alpha", (
        "case 12: the original operation was rewritten by the compensation"
    )
    assert (
        readback.observe_issue_with_watcher(title, watcher, operation_id="case-12").state
        == "partial"
    ), "case 12: unresolved state was not preserved"
