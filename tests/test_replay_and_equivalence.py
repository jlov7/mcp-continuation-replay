"""The two central hypotheses of Milestone A.

Both tests assert the **safe** property. A failure is the finding, not a mistake
in the test. Read `research/CURRENT-FINDINGS.md` for the current interpretation.

H1 (test_changed_input_responses_...) — a live token plus *different*
   `inputResponses` is accepted, because the boundary's `(target, args-digest)`
   binding for `tools/call` covers `name` + `arguments` only.

H2 (test_replayed_token_...) — a sealed token is not single-use, because the
   boundary keeps no consumed-token record. This is the lost-reply case.

Neither has been executed at the time of writing. These tests are how we find out.
"""

from __future__ import annotations

from typing import Any

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

from reference.backend import IssueStore
from reference.readback import ReadBack

pytestmark = pytest.mark.anyio

_KEY = b"0123456789abcdef0123456789abcdef"  # 32 bytes, as the SDK's own suite uses
_TITLE = "spec-replay"


def _ask_body(title: str) -> ElicitRequest:
    """Elicitation asking for the issue body — the continuation's payload."""
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


def _accept_body(body: str) -> ElicitResult:
    return ElicitResult(action="accept", content={"body": body})


def _extract_body(responses: Any) -> str:
    """Pull the body out of `ctx.input_responses`, tolerating object or mapping."""
    resp = responses["body"]
    content = getattr(resp, "content", None)
    if content is None and isinstance(resp, dict):
        content = resp.get("content")
    if isinstance(content, dict):
        return str(content.get("body", ""))
    return ""


def _server(store: IssueStore) -> MCPServer:
    """One MRTR tool: round 1 asks for the body, the retry commits the effect.

    The created body comes from the continuation's `inputResponses`, so two
    differing responses are two semantically different operations.
    """
    mcp = MCPServer(
        "continuation-replay-spec", request_state_security=RequestStateSecurity(keys=[_KEY])
    )

    @mcp.tool()
    async def create_issue(title: str, ctx: Context) -> str | InputRequiredResult:
        if ctx.input_responses is None:
            return InputRequiredResult(
                input_requests={"body": _ask_body(title)},
                request_state="awaiting-body",
            )
        body = _extract_body(ctx.input_responses)
        issue_id = store.create_issue(title, body=body)
        return f"created {issue_id}"

    return mcp


async def _first_round(client: Client, args: dict[str, Any]) -> str:
    first = await client.session.call_tool("create_issue", args, allow_input_required=True)
    assert isinstance(first, InputRequiredResult), f"expected MRTR, got {type(first).__name__}"
    assert first.request_state is not None, "server minted no request_state"
    return first.request_state


async def _retry(
    client: Client, args: dict[str, Any], token: str, body: str
) -> CallToolResult | InputRequiredResult:
    return await client.session.call_tool(
        "create_issue",
        args,
        input_responses={"body": _accept_body(body)},
        request_state=token,
        allow_input_required=True,
    )


# --- H2: a sealed token is not single-use ---------------------------------------------


@pytest.mark.pinned_finding(mechanism="duplicate_effect")
async def test_replayed_token_must_not_duplicate_the_effect(
    store: IssueStore, readback: ReadBack
) -> None:
    """PINNED WITNESS: replaying one continuation dispatches two effects.

    This is the lost-reply scenario. The first retry commits; the client never
    sees the reply; it retries the same logical operation. A protocol able to
    identify the operation would return the stored result. Nothing here marks a
    token consumed, so the second retry should dispatch again.
    """
    mcp = _server(store)

    async with Client(mcp) as client:
        token = await _first_round(client, {"title": _TITLE})
        first = await _retry(client, {"title": _TITLE}, token, body="alpha")
        assert isinstance(first, CallToolResult), "first retry should have terminated"
        assert readback.observe_by_title(_TITLE, operation_id="replay-h2").effects == 1

        # Reply "lost". The client retries the same logical continuation.
        second = await _retry(client, {"title": _TITLE}, token, body="alpha")
        assert isinstance(second, CallToolResult), "second retry should have terminated"

    observed = readback.observe_by_title(_TITLE, operation_id="replay-h2")
    assert observed.effects == 2 and observed.matching_ids == (1, 2)


# --- H1: changed inputResponses under a live token ------------------------------------


@pytest.mark.pinned_finding(mechanism="changed_input_dispatched")
async def test_changed_input_responses_must_conflict_before_dispatch(
    store: IssueStore, readback: ReadBack
) -> None:
    """PINNED WITNESS: changed `inputResponses` reaches the handler.

    The boundary binds `(target, args-digest, principal)` and never reads
    `inputResponses`. So a token minted for one continuation should be accepted
    when replayed with a different one, dispatching a second, different effect.
    """
    mcp = _server(store)

    async with Client(mcp) as client:
        token = await _first_round(client, {"title": _TITLE})
        await _retry(client, {"title": _TITLE}, token, body="alpha")
        assert readback.observe_by_body("alpha", operation_id="replay-h1").effects == 1

        # Same token, same args, DIFFERENT continuation input.
        conflicted = False
        try:
            await _retry(client, {"title": _TITLE}, token, body="beta")
        except MCPError:
            conflicted = True

    beta = readback.observe_by_body("beta", operation_id="replay-h1")
    assert not conflicted
    assert beta.effects == 1 and readback.total() == 2


# --- Controls: confirm the harness can reach the happy path ---------------------------


async def test_identical_continuation_with_a_fresh_round_completes_once(
    store: IssueStore, readback: ReadBack
) -> None:
    """Control: the machinery can perform a legitimate single MRTR exchange."""
    mcp = _server(store)

    async with Client(mcp) as client:
        token = await _first_round(client, {"title": _TITLE})
        result = await _retry(client, {"title": _TITLE}, token, body="alpha")

    assert isinstance(result, CallToolResult)
    observed = readback.observe_by_body("alpha", operation_id="replay-control")
    assert observed.effects == 1
