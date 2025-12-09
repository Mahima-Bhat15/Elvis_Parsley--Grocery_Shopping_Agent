# app/utils/llm.py
from typing import Optional, Any
from .settings import settings

try:
    # OpenAI python client v1.x
    from openai import OpenAI
except Exception:
    OpenAI = None


class LLM:
    def __init__(self):
        self.model = settings.OPENAI_MODEL
        self.client: Optional[Any] = None
        if OpenAI and settings.OPENAI_API_KEY:
            try:
                self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
            except Exception:
                self.client = None

    def complete(self, system: str, user: str) -> str:
        """Return a completion. Falls back to echoing the user text."""
        if not self.client:
            return user
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
            )
            return resp.choices[0].message.content or ""
        except Exception:
            return user


# IMPORTANT: this instance name is what other modules import
llm = LLM()
