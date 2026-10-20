"""Optional active-model smoke test. Resolves the model from PostgreSQL, not .env."""

from __future__ import annotations

import sys

from langchain_core.messages import HumanMessage

from NoteAgent.AppBootstrap.AppSettings import Settings
from NoteAgentEvals.ModelResolver import build_active_chat


def main() -> int:
    """Send a one-shot ping using the active model configuration."""
    try:
        chat = build_active_chat(Settings())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    response = chat.client.invoke([HumanMessage(content="ping")])
    print(response.content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
