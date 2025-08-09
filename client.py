"""LLM client."""

import os

from dotenv import load_dotenv
from openai import OpenAI


class OpenRouterClient:
    """Simple OpenRouter-backed client using the OpenAI SDK"""

    def __init__(
        self,
        model,
    ):
        # Load OpenRouter API key from environment variables
        load_dotenv()
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY not found in environment variables")

        # Configure the client to talk to OpenRouter
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        self.model = model
        self._app_title = "LLM Chess Arena"

    def name(self):
        return self.model

    def chat(self, messages):
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"Error getting response from {self.model}: {e}")
            return None
