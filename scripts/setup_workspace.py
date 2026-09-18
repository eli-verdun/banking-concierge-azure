"""Provision the Application grouping + feedback-review queue for the demo.

Run after the tracing project exists (i.e. after the first trace / load run) and
after the datasets are restored. It:

  1. Ensures the "Meridian National: Negative Feedback Review" annotation queue.
  2. Tags the tracing project, the three committed datasets, the datasets backing
     the online evaluators, the queue, and the Context Hub repos with the reserved
     ``Application`` tag value (``banking-concierge``), so they group under one
     application in the LangSmith UI.
  3. Ensures the "Negative Feedback" run rule: a server-side automation that routes
     any run scored ``user_feedback = 0`` into the review queue.

What the Application grouping covers, and what it does NOT:

  - **Experiments inherit the tag from their reference dataset** - they are tagged
    automatically, so nothing here needs to tag them. Keep the datasets tagged and
    every future experiment lands in the application too. An experiment is itself a
    session, so it also appears in the project listing; tagging it as a ``project``
    as well would put one resource in the application twice.
  - **The show-only skills are standalone Context Hub repos** in this demo (not
    files inside the agent repo), so each one is tagged separately.
  - **Deployments and dashboards cannot be enumerated from the public v1 API**, so
    they cannot be discovered and tagged automatically. Set
    ``APPLICATION_DEPLOYMENT_ID`` / ``APPLICATION_DASHBOARD_ID`` (copy the uuid out
    of the resource's URL in the UI) and this script will tag them; otherwise tag
    them once by hand in the UI.

The app's feedback route (``src/concierge/app.py``) writes the ``user_feedback``
key that the run rule filters on.

    uv run python -m scripts.setup_workspace

Requires ``LANGSMITH_API_KEY`` (and ``LANGSMITH_WORKSPACE_ID`` when the key's
default workspace differs). Tagging requires Plus/Enterprise; creating the
``Application`` tag value needs workspace-admin (the key itself exists by default).
"""

from __future__ import annotations

import os
import re
import sys

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

from langsmith import Client  # noqa: E402

from concierge.context import CONTEXT_HUB_REPO  # noqa: E402
from concierge.context_hub import DEMO_SKILL_NAMES  # noqa: E402
from concierge.governance import (  # noqa: E402
    APPLICATION_NAME,
    APPLICATION_TAG_KEY,
    FEEDBACK_RULE_FILTER,
    FEEDBACK_RULE_NAME,
    REVIEW_QUEUE_DESCRIPTION,
    REVIEW_QUEUE_NAME,
)

_API = "https://api.smith.langchain.com/api/v1"
PROJECT_NAME = os.getenv("LANGSMITH_PROJECT", "banking-concierge")
# The committed datasets (see evals/dataset_snapshot.py).
DATASET_NAMES = [
    "banking-concierge-golden",
    "banking-concierge-hallucinations",
    "banking-concierge-pii",
]

# Any secret-shaped token is scrubbed before an error body is printed. Error
# responses can echo request context back, and this script runs with the
# tracing key in its environment - so nothing reaches stdout unfiltered.
_SECRET_RE = re.compile(r"(lsv2_[a-z]{2}_[A-Za-z0-9]+|sk-[A-Za-z0-9_-]{20,})")


def _safe(text: str, limit: int = 150) -> str:
    """Truncate an HTTP response body and mask anything secret-shaped in it."""
    return _SECRET_RE.sub("<redacted>", text[:limit])


def _headers() -> dict:
    h = {"x-api-key": os.environ["LANGSMITH_API_KEY"], "Content-Type": "application/json"}
    if ws := os.getenv("LANGSMITH_WORKSPACE_ID", "").strip():
        h["X-Tenant-Id"] = ws
    return h


# ── Annotation queue ─────────────────────────────────────────────────────────

def ensure_review_queue(client: Client) -> str | None:
    """Create (or find) the negative-feedback review queue. Returns its id."""
    try:
        for q in client.list_annotation_queues():
            if getattr(q, "name", None) == REVIEW_QUEUE_NAME:
                print(f"  Review queue already exists: {q.id}")
                return str(q.id)
    except Exception as exc:  # noqa: BLE001
        print(f"  (could not list annotation queues: {exc})")

    try:
        queue = client.create_annotation_queue(
            name=REVIEW_QUEUE_NAME,
            description=REVIEW_QUEUE_DESCRIPTION,
            rubric_instructions=(
                "Review this thumbs-down interaction. Was the answer valid and grounded in a "
                "tool result or a knowledge-base document? Note any PII exposure (SSN, full "
                "card number, CVV, full account number) or transfer-policy error. Do not copy "
                "a sensitive value into your notes - say which field leaked."
            ),
            rubric_items=[
                {
                    "feedback_key": "resolution_valid",
                    "description": "Was the concierge's response valid and grounded?",
                    "value_descriptions": {
                        "Pass": "Valid, and every figure came from a tool or a document",
                        "Fail": "Wrong, ungrounded, or unsafe",
                    },
                    "is_required": True,
                },
                {
                    "feedback_key": "pii_exposed",
                    "description": "Did the response read back an SSN, full card number, CVV, or full account number?",
                    "value_descriptions": {
                        "Pass": "No sensitive value in the response",
                        "Fail": "A sensitive value was read back verbatim",
                    },
                    "is_required": True,
                },
                {
                    "feedback_key": "reviewer_notes",
                    "description": "Any additional observations (name the field, never the value)",
                    "is_required": False,
                },
            ],
        )
        print(f"  Created review queue: {queue.id}")
        return str(queue.id)
    except Exception as exc:  # noqa: BLE001
        print(f"  WARNING: could not create review queue ({exc}).")
        return None


# ── Application tag ──────────────────────────────────────────────────────────

def ensure_application_value(headers: dict) -> str | None:
    """Resolve the ``Application`` tag value id for APPLICATION_NAME, creating it if needed."""
    resp = requests.get(f"{_API}/workspaces/current/tags", headers=headers, timeout=30)
    if resp.status_code != 200:
        print(f"  WARNING: could not list tags ({resp.status_code} {_safe(resp.text)}).")
        return None
    body = resp.json()
    keys = body.get("items", body) if isinstance(body, dict) else body

    app_key = next((k for k in keys if k.get("key") == APPLICATION_TAG_KEY), None)
    if app_key is None:
        # The Application key exists by default; create only as a fallback.
        r = requests.post(
            f"{_API}/workspaces/current/tag-keys",
            headers=headers,
            json={"key": APPLICATION_TAG_KEY, "description": "Application grouping"},
            timeout=30,
        )
        if r.status_code not in (200, 201):
            print(f"  WARNING: could not create '{APPLICATION_TAG_KEY}' key ({r.status_code} {_safe(r.text)}).")
            return None
        app_key = {"id": r.json()["id"], "values": []}

    for v in app_key.get("values", []) or []:
        if v.get("value") == APPLICATION_NAME:
            return v["id"]

    r = requests.post(
        f"{_API}/workspaces/current/tag-keys/{app_key['id']}/tag-values",
        headers=headers,
        json={"value": APPLICATION_NAME},
        timeout=30,
    )
    if r.status_code not in (200, 201):
        print(f"  WARNING: could not create tag value '{APPLICATION_NAME}' ({r.status_code} {_safe(r.text)}).")
        return None
    return r.json()["id"]


def tag_resource(
    headers: dict, tag_value_id: str, resource_type: str, resource_id: str, label: str
) -> bool:
    resp = requests.post(
        f"{_API}/workspaces/current/taggings",
        headers=headers,
        json={
            "tag_value_id": tag_value_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
        },
        timeout=30,
    )
    if resp.status_code in (200, 201):
        print(f"  ✅ tagged {resource_type}: {label}")
        return True
    if resp.status_code == 409 or "exist" in resp.text.lower():
        print(f"  • already tagged {resource_type}: {label}")
        return True
    print(f"  ❌ {resource_type} {label}: {resp.status_code} {_safe(resp.text)}")
    return False


def _repo_id(headers: dict, handle: str) -> str | None:
    """Resolve a Context Hub repo's uuid from its handle."""
    r = requests.get(f"{_API}/repos/-/{handle}", headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"  - Context Hub repo '{handle}' not found ({r.status_code}); seed it first.")
        return None
    body = r.json()
    return (body.get("repo") or body).get("id")


def tag_evaluator_datasets(client: Client, headers: dict, tag_value_id: str) -> int:
    """Tag the datasets backing the online evaluators (scripts/setup_online_evals.py).

    LangSmith creates one dataset per online evaluator, named
    ``Evaluator: <project>:<feedback_key> (<hash>) - <feedback_key>``. The hash means
    they can't be looked up by exact name, so they are discovered by prefix. Those
    rules are created *after* this script usually runs, which is why they need their
    own pass. ``startswith`` anchors the match, so a sibling application's evaluator
    datasets in the same workspace are left alone.
    """
    prefix = f"Evaluator: {PROJECT_NAME}:"
    found = 0
    try:
        for ds in client.list_datasets(dataset_name_contains=prefix):
            if not str(ds.name).startswith(prefix):
                continue  # substring match can span other projects; anchor it
            found += 1
            tag_resource(headers, tag_value_id, "dataset", str(ds.id), str(ds.name))
    except Exception as exc:  # noqa: BLE001
        print(f"  (could not list evaluator datasets: {exc})")
    if not found:
        print("  - no online-evaluator datasets yet; run scripts.setup_online_evals first.")
    return found


# ── Feedback automation ──────────────────────────────────────────────────────

def ensure_feedback_rule(headers: dict, project_id: str, queue_id: str) -> None:
    """Create the run rule that auto-routes user_feedback=0 traces to the review queue.

    This is the server-side LangSmith automation (equivalent to setting it up in the
    project's Rules UI): any run scored ``user_feedback = 0`` is added to the queue.
    It is a routing rule only - no model, no credential in the body. Idempotent:
    skips if a rule with FEEDBACK_RULE_NAME already exists on the project.
    """
    resp = requests.get(
        f"{_API}/runs/rules", headers=headers, params={"session_id": project_id}, timeout=30
    )
    if resp.status_code == 200 and any(
        r.get("display_name") == FEEDBACK_RULE_NAME for r in resp.json()
    ):
        print(f"  • rule already exists: {FEEDBACK_RULE_NAME}")
        return

    resp = requests.post(
        f"{_API}/runs/rules",
        headers=headers,
        json={
            "display_name": FEEDBACK_RULE_NAME,
            "session_id": project_id,
            "sampling_rate": 1.0,
            "filter": FEEDBACK_RULE_FILTER,
            "add_to_annotation_queue_id": queue_id,
        },
        timeout=30,
    )
    if resp.status_code in (200, 201):
        print(f"  ✅ created rule: {FEEDBACK_RULE_NAME} -> {REVIEW_QUEUE_NAME}")
    else:
        print(f"  ❌ rule {FEEDBACK_RULE_NAME}: {resp.status_code} {_safe(resp.text)}")


def main() -> None:
    if not os.getenv("LANGSMITH_API_KEY"):
        print("Error: LANGSMITH_API_KEY not set.")
        sys.exit(1)

    client = Client()
    headers = _headers()

    print(f"\n[1/4] Ensuring review queue '{REVIEW_QUEUE_NAME}'...")
    queue_id = ensure_review_queue(client)

    # Resolve the project once - needed for both tagging and the feedback rule.
    try:
        project_id = str(client.read_project(project_name=PROJECT_NAME).id)
    except Exception as exc:  # noqa: BLE001
        project_id = None
        print(f"  WARNING: project '{PROJECT_NAME}' not found ({exc}). Send a trace first.")

    print(f"\n[2/4] Resolving '{APPLICATION_TAG_KEY}' = '{APPLICATION_NAME}'...")
    tag_value_id = ensure_application_value(headers)
    if not tag_value_id:
        print("  Skipping tagging (no tag value). Resolve permissions/plan and re-run.")
    else:
        print("\n[3/4] Tagging resources into the application...")

        if project_id:
            tag_resource(headers, tag_value_id, "project", project_id, PROJECT_NAME)

        for name in DATASET_NAMES:
            try:
                ds = client.read_dataset(dataset_name=name)
                tag_resource(headers, tag_value_id, "dataset", str(ds.id), name)
            except Exception:
                print(f"  • dataset '{name}' not found (restore it first); skipping.")

        # Datasets backing the online evaluators - created later, by
        # scripts.setup_online_evals, so they are discovered by prefix.
        tag_evaluator_datasets(client, headers, tag_value_id)

        if queue_id:
            tag_resource(headers, tag_value_id, "queue", queue_id, REVIEW_QUEUE_NAME)

        # Context Hub agent repo (AGENTS.md) - resource_type 'agent'. This is what
        # groups the agent under the application in the Context Hub UI.
        if aid := _repo_id(headers, CONTEXT_HUB_REPO):
            tag_resource(headers, tag_value_id, "agent", aid, CONTEXT_HUB_REPO)

        # The show-only skills are standalone repos here, so each needs its own
        # tagging. 'skill' is the resource type for a Context Hub skill repo.
        for handle in DEMO_SKILL_NAMES:
            if sid := _repo_id(headers, handle):
                tag_resource(headers, tag_value_id, "skill", sid, handle)

        # Deployment / dashboard: the public v1 API has no listing endpoint for
        # these, so they can't be discovered by name. Supply the uuid from the
        # resource's URL in the UI to have them tagged here instead of by hand.
        for env_var, resource_type in (
            ("APPLICATION_DEPLOYMENT_ID", "deployment"),
            ("APPLICATION_DASHBOARD_ID", "dashboard"),
        ):
            rid = os.getenv(env_var, "").strip()
            if rid:
                tag_resource(headers, tag_value_id, resource_type, rid, rid)
            else:
                print(f"  - no {env_var} set; tag the {resource_type} in the UI (one-off).")

    print(f"\n[4/4] Ensuring feedback automation '{FEEDBACK_RULE_NAME}'...")
    if project_id and queue_id:
        ensure_feedback_rule(headers, project_id, queue_id)
    else:
        print("  Skipping: need both the project and the review queue to exist.")

    print(f"\nDone. Resources grouped under application '{APPLICATION_NAME}'.")


if __name__ == "__main__":
    main()
