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

    def name(self):
        return self.model

    def chat(self, messages):
        try:
            start = time.time()
            extra_body = {"usage": {"include": True}}
            if self.model == "openai/gpt-5-high":
                model_to_call = "openai/gpt-5"
                # Add high reasoning effort
                extra_body["reasoning"] = {"effort": "high"}
            else:
                model_to_call = self.model
            log.debug(f"Sending request to {model_to_call}...")
            completion = self.client.chat.completions.create(
                model=model_to_call,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "chess_move",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "analysis": {
                                    "type": "string",
                                    "description": "First, think step-by-step about the position and document your thoughts here. This is your internal monologue.",
                                },
                                "breakdown": {
                                    "type": "string",
                                    "description": "Second, summarize your thinking in a short, one or two-sentence explanation for your final move choice.",
                                },
                                "choice": {
                                    "type": "string",
                                    "description": "Third, return exactly one move in UCI format from the list of legal moves.",
                                    "pattern": "^(?:[a-h][1-8][a-h][1-8][qrbn]?|resign|pass)$",
                                },
                            },
                            "required": ["analysis", "breakdown", "choice"],
                            "additionalProperties": False,
                        },
                    },
                },
                extra_body=extra_body,
            )
            log.debug(f"Received response from {self.model}: {completion}")
            latency = time.time() - start
            cost = 0
            # Log request cost
            try:
                cost = completion.usage.cost or 0
                upstream = (
                    completion.usage.cost_details.get("upstream_inference_cost") or 0
                )
                cost += upstream
                log.debug(
                    f"Request cost: {cost:.3f}€ (including {upstream:.3f}€ upstream) | latency: {latency:.1f}s"
                )
            except Exception as e:
                log.error(f"Error getting cost info: {e}")

            return {"completion": completion, "cost": cost, "latency": latency}
        except Exception as e:
            log.error(
                f"Error getting response from {self.model}: {type(e).__name__} - {e}"
            )
            return None
