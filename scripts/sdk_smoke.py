"""Optional DeepSeek API smoke test. Reads credentials from the environment only."""

from __future__ import annotations

import os
import sys

from openai import OpenAI


def main() -> int:
    """Send a one-shot ping to DeepSeek using env credentials."""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("DEEPSEEK_API_KEY is not set", file=sys.stderr)
        return 1
    base_url = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=os.environ.get("CHAT_MODEL", "deepseek-v4-flash"),
        messages=[{"role": "user", "content": "ping"}],
        stream=False,
    )
    print(response.choices[0].message.content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
