"""LLM client."""

import os

from dotenv import load_dotenv
from openai import OpenAI


class OpenRouterClient:
    """Simple OpenRouter-backed client using the OpenAI SDK"""

    def __init__(
        self,
        model,
        # referer_url=None,
        # app_title=None,
        # temperature=0.0,  # be deterministic if possible
        # max_tokens=8,  # we want just one token-like output (e2e4)
        # request_timeout_s=60,
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
        # self._referer_url = referer_url
        # self._temperature = temperature
        # self._max_tokens = max_tokens
        # self._timeout = request_timeout_s

    def name(self):
        return self.model

    def get_next_move(self, system_prompt, user_prompt):
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                # temperature=self._temperature,
                # max_tokens=self._max_tokens,
                # extra_headers=headers or None,
                # timeout=self._timeout,
            )
            response = completion.choices[0].message.content
            response_without_newlines = response.replace("\n", " ")
            print(f"{self.model} response: {response_without_newlines}")
            try:
                move = response.split("Move: ")[-1].strip()
                return move
            except Exception as e:
                print(f"Error getting next move: {e}")
                return None
        except Exception as e:
            print(f"Error getting next move: {e}")
            return None
