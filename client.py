"""LLM client."""

import os
import time

from dotenv import load_dotenv
from openai import OpenAI
from logger import log


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
            timeout=300,
        )
        self.model = model
        self._app_title = "LLM Chess Arena"

    def name(self):
        return self.model

    def chat(self, messages):
        try:
            start = time.time()
            log.debug(f"Sending request to {self.model}...")
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "chess_move",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "rationale": {
                                    "type": "string",
                                    "description": "Reasoning for your move",
                                },
                                "move": {
                                    "type": "string",
                                    "description": "Exactly one move in UCI like 'e2e4' (or 'resign' if checkmated, 'pass' if stalemate)",
                                    "pattern": "^(?:[a-h][1-8][a-h][1-8][qrbn]?|resign|pass)$",
                                },
                            },
                            "required": ["rationale", "move"],
                            "additionalProperties": False,
                        },
                    },
                },
                extra_body={"usage": {"include": True}},
            )
            log.info(f"Received response from {self.model}.")
            latency = time.time() - start
            cost = 0
            # Print request cost
            try:
                cost = completion.usage.cost
                log.info(f"Request cost: {cost:.3f}€ | latency: {latency:.1f}s")
            except Exception as e:
                log.error(f"Error getting upstream inference cost: {e}")

            return {"completion": completion, "cost": cost, "latency": latency}
        except Exception as e:
            log.error(f"Error getting response from {self.model}: {e}")
            return None
