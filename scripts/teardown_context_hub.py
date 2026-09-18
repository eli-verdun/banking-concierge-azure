"""Delete the banking-concierge artifacts from LangSmith Context Hub.

The inverse of ``scripts/setup_context_hub.py``. Removes the repos this demo
creates:

  - ``banking-concierge-agent``        — the agent repo (AGENTS.md)
  - ``banking-concierge-*-skill``      — the show-only demo skill repos

Deleting a repo removes all of its commits, tags (including ``production``),
and files. This is permanent and cannot be undone.

Usage:
    # Safe dry run — list which artifacts exist and would be deleted:
    uv run python -m scripts.teardown_context_hub

    # Actually delete them:
    uv run python -m scripts.teardown_context_hub --yes
"""

from dotenv import load_dotenv

load_dotenv(override=True)

import argparse
import os
import sys

from langsmith import Client

from concierge.context import CONTEXT_HUB_REPO
from concierge.context_hub import _DEMO_SKILLS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually delete the repos. Without this flag the script only "
        "lists what exists (dry run).",
    )
    args = parser.parse_args()

    if not os.getenv("LANGSMITH_API_KEY"):
        print("Error: LANGSMITH_API_KEY not set.")
        sys.exit(1)

    client = Client()

    # (kind, handle, exists_fn, delete_fn)
    targets = [("agent", CONTEXT_HUB_REPO, client.agent_exists, client.delete_agent)]
    targets += [
        ("skill", handle, client.skill_exists, client.delete_skill)
        for handle in _DEMO_SKILLS
    ]

    print(f"Context Hub artifacts for '{CONTEXT_HUB_REPO}':\n")
    present = []
    for kind, handle, exists_fn, delete_fn in targets:
        try:
            exists = bool(exists_fn(handle))
        except Exception as exc:  # noqa: BLE001
            print(f"  [error  ] {kind:5} {handle}  ({exc})")
            continue
        print(f"  [{'present' if exists else 'absent '}] {kind:5} {handle}")
        if exists:
            present.append((kind, handle, delete_fn))

    if not present:
        print("\nNothing to delete.")
        return

    if not args.yes:
        print(
            f"\nDry run — {len(present)} repo(s) would be deleted. "
            "Re-run with --yes to delete them permanently."
        )
        return

    print()
    failed = 0
    for kind, handle, delete_fn in present:
        try:
            delete_fn(handle)
            print(f"  deleted {kind} {handle}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAILED  {kind} {handle}: {exc}")

    print(f"\nDeleted {len(present) - failed}/{len(present)} repo(s).")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
