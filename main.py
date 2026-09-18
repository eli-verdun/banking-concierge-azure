"""Quick smoke-test entry point.

For the full chat experience, run:

    uv run langgraph dev

and open Studio at http://localhost:2024.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv

load_dotenv(override=True)

from concierge.graph import graph  # noqa: E402


def main() -> None:
    question = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "What is the monthly fee on Everyday Checking?"
    )
    result = graph.invoke({"messages": [{"role": "user", "content": question}]})
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
