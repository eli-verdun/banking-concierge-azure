"""FastAPI custom routes for the LangGraph agent server.

Mounted at the deployment root via `langgraph.json`'s `http.app` key, so
this app extends the agent server (which already exposes `/threads`,
`/runs`, `/assistants`, etc.) with our own routes:

- `GET  /health`               - simple liveness probe
- `GET  /`                     - redirect to `/concierge/`
- `GET  /concierge/`           - the built React chat UI (Vite dist/)
- `POST /concierge-api/feedback` - record thumbs up/down on a run in LangSmith

If the frontend bundle hasn't been built yet, `/concierge/*` returns a
503 with a hint to run `npm install && npm run build` in `frontend/`.

The feedback route keeps `LANGSMITH_API_KEY` server-side: the browser
posts only `{run_id, score, comment}` and this app calls the LangSmith
SDK on its behalf, so the key is never shipped to the client.

NOTE: do NOT add `from __future__ import annotations` here. The custom app's
request models (e.g. FeedbackRequest) must resolve eagerly so the LangGraph
server can build the OpenAPI spec at startup; lazy string annotations raise
PydanticUserError("...is not fully defined").
"""

import pathlib
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from langsmith import Client
from pydantic import BaseModel, Field

app = FastAPI()

_langsmith_client = Client()


class FeedbackRequest(BaseModel):
    run_id: uuid.UUID
    score: float = Field(ge=0, le=1)
    comment: str | None = None


@app.post("/concierge-api/feedback")
def submit_feedback(body: FeedbackRequest) -> dict[str, str]:
    """Attach user thumbs up/down to the LangSmith run that produced a reply.

    `score` is 1 for thumbs-up and 0 for thumbs-down. Passing `trace_id`
    lets the SDK background the write so the request returns immediately.
    """
    try:
        _langsmith_client.create_feedback(
            body.run_id,
            key="user_feedback",
            score=body.score,
            trace_id=body.run_id,
            comment=body.comment,
        )
    except Exception as exc:  # noqa: BLE001 - surface a clean 502 to the client
        raise HTTPException(
            status_code=502, detail=f"Failed to record feedback: {exc}"
        ) from exc
    return {"status": "ok"}

FRONTEND_BUILD_DIR = (
    pathlib.Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/concierge/")


@app.get("/concierge")
def concierge_redirect() -> RedirectResponse:
    return RedirectResponse(url="/concierge/")


if FRONTEND_BUILD_DIR.is_dir() and (FRONTEND_BUILD_DIR / "index.html").is_file():
    app.mount(
        "/concierge",
        StaticFiles(directory=str(FRONTEND_BUILD_DIR), html=True),
        name="frontend",
    )
else:

    @app.get("/concierge/{path:path}")
    def frontend_not_built(path: str = "") -> PlainTextResponse:
        del path
        return PlainTextResponse(
            "Frontend not built. "
            "From the project root, run:\n\n"
            "  npm --prefix frontend install\n"
            "  npm --prefix frontend run build\n",
            status_code=503,
        )
