"""Minimal FastAPI proxy for a deployed A2A agent (Agent Runtime, agents-cli 1.1.0+).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the
browser). The proxy authenticates with Application Default Credentials and
forwards chat to the deployed agent over the A2A protocol, returning replies as
structured parts the chat UI knows how to show:

  * {"kind": "text", "text": ...}  -> a normal chat bubble
  * {"kind": "a2ui", "data": ...}  -> one A2UI message (beginRendering /
    surfaceUpdate); static/index.html renders these as a card.

Why A2A: agents-cli 1.1.0 (GA) deploys ADK agents to Agent Runtime as A2A agents
and no longer registers the reasoning-engine operation schema the old
`agent_engines.get(...).stream_query()` path relied on (operation_schemas() comes
back empty). The container serves the A2A protocol over the Agent Engine HTTP
passthrough, so this proxy fetches the agent's card and sends messages with the
a2a-sdk client (the same path `agents-cli run --mode a2a` uses). This works for
both A2A and plain ADK 1.1.0 deployments (the container serves A2A either way).

Run:
  pip install -r requirements.txt
  export AGENT_ENGINE_RESOURCE_NAME="projects/.../locations/.../reasoningEngines/..."
  export AGENT_DIRECTORY="app"   # your agent's app directory (agents-cli-manifest.yaml)
  python main.py                 # -> http://localhost:8080
"""

import os
import uuid

import google.auth
import google.auth.transport.requests
import httpx
from a2a.client import ClientConfig, ClientFactory
try:
    from a2a.types import (
        AgentCard,
        FilePart,
        Message,
        Part,
        Role,
        TaskArtifactUpdateEvent,
        TextPart,
        TransportProtocol,
    )
except ImportError:
    from a2a.types import AgentCard, Message, Part, Role

    try:
        from a2a.compat.v0_3.types import (
            FilePart,
            TaskArtifactUpdateEvent,
            TextPart,
            TransportProtocol,
        )
    except ImportError:
        FilePart = None
        TextPart = None
        TransportProtocol = None
        TaskArtifactUpdateEvent = None

SendMessageRequest = None
try:
    from a2a.types import SendMessageRequest
except ImportError:
    pass

IS_A2A_1X = not hasattr(Role, "user")
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

try:
    from dotenv import load_dotenv

    load_dotenv()
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except Exception:
    pass

RESOURCE = os.environ.get("AGENT_ENGINE_RESOURCE_NAME")
if not RESOURCE:
    import json
    meta_path = os.path.join(os.path.dirname(__file__), "..", "deployment_metadata.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path) as f:
                RESOURCE = json.load(f).get("remote_agent_runtime_id")
        except Exception:
            pass
    if not RESOURCE:
        RESOURCE = "projects/152515589043/locations/us-central1/reasoningEngines/9100287757439205376"

# The agent's app directory (matches agent_directory in agents-cli-manifest.yaml).
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
# Location is embedded in the resource name: projects/<p>/locations/<loc>/reasoningEngines/<id>.
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]

# A2A endpoint for an Agent Runtime deployment, via the Agent Engine HTTP
# passthrough. The card lives at the well-known path under this base.
A2A_BASE = (
    f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"

# The agent tags its A2UI data parts with this mime type.
_A2UI_MIME = "application/json+a2ui"

# One set of ADC credentials, refreshed per request (access tokens expire ~1h).
_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
    _creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {_creds.token}",
        "Content-Type": "application/json",
    }


app = FastAPI()


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    # Always return JSON so the browser never receives a plain-text 500 page
    # (which shows up in the chat as "Unexpected token 'I', "Internal S"... is
    # not valid JSON"). Any server-side failure now surfaces as a readable
    # message in the chat bubble instead.
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


# Reuse ONE A2A context per user so the agent remembers the conversation.
_contexts: dict[str, str] = {}
# Cache the agent card after the first fetch.
_card = None


async def _get_card(client: httpx.AsyncClient):
    global _card
    if _card is None:
        try:
            from a2a.client import A2ACardResolver

            resolver = A2ACardResolver(httpx_client=client, base_url=A2A_BASE)
            _card = await resolver.get_agent_card()
        except Exception:
            resp = await client.get(A2A_CARD_URL)
            resp.raise_for_status()
            card = AgentCard(**resp.json())
            card.url = A2A_BASE
            _card = card
    return _card


def _extract_parts(parts: list) -> list[dict]:
    """Turn A2A response parts into structured parts for the chat UI."""
    out: list[dict] = []
    for p in parts:
        # Protobuf Part (a2a-sdk 1.x)
        if hasattr(p, "DESCRIPTOR"):
            from google.protobuf.json_format import MessageToDict

            p_dict = MessageToDict(p)
            if text := p_dict.get("text"):
                out.append({"kind": "text", "text": text})
            elif "data" in p_dict:
                d = p_dict["data"]
                meta = (
                    p_dict.get("metadata")
                    or (d.get("metadata") if isinstance(d, dict) else {})
                    or {}
                )
                mime = meta.get("mimeType")
                if mime == _A2UI_MIME:
                    a2ui_msg = d.get("data", d)
                    out.append({"kind": "a2ui", "data": a2ui_msg})
                elif isinstance(d, dict) and any(
                    k in d for k in ("beginRendering", "surfaceUpdate", "deleteSurface")
                ):
                    out.append({"kind": "a2ui", "data": d})
                else:
                    out.append({"kind": "text", "text": str(d)})
            elif file_obj := p_dict.get("file"):
                if uri := file_obj.get("uri"):
                    out.append({"kind": "text", "text": uri})
            continue

        # Pydantic Part (a2a-sdk 0.3.x)
        root = getattr(p, "root", p)
        if TextPart is not None and isinstance(root, TextPart) and getattr(root, "text", None):
            out.append({"kind": "text", "text": root.text})
        elif getattr(root, "data", None) is not None:
            meta = getattr(root, "metadata", None) or {}
            mime = meta.get("mimeType") if isinstance(meta, dict) else None
            if mime == _A2UI_MIME:
                out.append({"kind": "a2ui", "data": root.data})
            elif isinstance(root.data, dict) and any(
                k in root.data for k in ("beginRendering", "surfaceUpdate")
            ):
                out.append({"kind": "a2ui", "data": root.data})
        elif FilePart is not None and isinstance(root, FilePart):
            uri = getattr(getattr(root, "file", None), "uri", None)
            if uri:
                out.append({"kind": "text", "text": uri})
    return out


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    parts: list[dict] = []

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as client:
        if IS_A2A_1X:
            card = await _get_card(client)
            factory = ClientFactory(ClientConfig(httpx_client=client))
            a2a_client = factory.create(card)

            msg = Message(
                message_id=str(uuid.uuid4()),
                role=getattr(Role, "ROLE_USER", 1),
                parts=[Part(text=message)],
                context_id=_contexts.get(user_id, ""),
            )
            req_msg = SendMessageRequest(message=msg)

            async for event in a2a_client.send_message(req_msg):
                if event.HasField("task"):
                    if event.task.context_id:
                        _contexts[user_id] = event.task.context_id
                    if event.task.artifacts:
                        for art in event.task.artifacts:
                            parts.extend(_extract_parts(art.parts))
                if event.HasField("status_update"):
                    su = event.status_update
                    if su.context_id:
                        _contexts[user_id] = su.context_id
                    if su.HasField("status") and su.status.HasField("message"):
                        parts.extend(_extract_parts(su.status.message.parts))
                if event.HasField("artifact_update"):
                    parts.extend(_extract_parts(event.artifact_update.artifact.parts))
                if event.HasField("message"):
                    parts.extend(_extract_parts(event.message.parts))
        else:
            card = await _get_card(client)
            try:
                config = ClientConfig(
                    supported_transports=[
                        TransportProtocol.jsonrpc,
                        TransportProtocol.http_json,
                    ],
                    httpx_client=client,
                )
            except TypeError:
                config = ClientConfig(httpx_client=client)
            factory = ClientFactory(config)
            a2a_client = factory.create(card)

            msg = Message(
                message_id=str(uuid.uuid4()),
                role=Role.user,
                parts=[Part(root=TextPart(text=message))],
                context_id=_contexts.get(user_id),
            )

            last_task = None
            got_artifact_update = False
            async for event in a2a_client.send_message(msg):
                if not isinstance(event, tuple):
                    continue
                task, update = event
                if task is not None:
                    last_task = task
                    if getattr(task, "context_id", None):
                        _contexts[user_id] = task.context_id
                if isinstance(update, TaskArtifactUpdateEvent):
                    got_artifact_update = True
                    parts.extend(_extract_parts(update.artifact.parts))

            # Non-streaming fallback: pull parts from the final task's artifacts.
            if not got_artifact_update and last_task is not None:
                for artifact in getattr(last_task, "artifacts", None) or []:
                    parts.extend(_extract_parts(artifact.parts))

    if not parts:
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]
    return JSONResponse({"parts": parts})


# Serve the chat UI (keep this mount last so /chat wins).
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
