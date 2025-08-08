"""LLM client."""

import os
import json

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

    def get_next_move(self, system_prompt, user_prompt):
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            # response_without_newlines = response.replace("\n", " ")
            # print(f"{self.model} response: {response_without_newlines}")
            # try:
            #     move = response.split("Move: ")[-1].strip()
            #     return move
            # except Exception as e:
            #     print(f"Error getting next move: {e}")
            #     return None
            response = json.loads(completion.choices[0].message.content.strip())
            print(f"{self.model} response: {response}")
            move = response["move"].strip()
            return move
        except Exception as e:
            print(f"Error getting next move: {e}")
            return None
