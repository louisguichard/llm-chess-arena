"""LLM client."""

import os
import time
import requests

from dotenv import load_dotenv
from logger import log

# Load OpenRouter API key from environment variables
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY not found in environment variables")


# Global HTTP session and default timeouts
SESSION = requests.Session()
CONNECT_TIMEOUT_SECONDS = 10
READ_TIMEOUT_SECONDS = 300


class OpenRouterClient:
    """Simple OpenRouter-backed client using direct HTTP requests."""

    def __init__(
        self,
        model,
    ):
        self.model = model

    def name(self):
        return self.model

    def chat(self, messages):
        try:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            }
            start = time.time()
            if self.model == "openai/gpt-5-high":
                model_to_call = "openai/gpt-5"
            else:
                model_to_call = self.model
            payload = {
                "model": model_to_call,
                "messages": messages,
                "response_format": {
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
                                },
                            },
                            "required": ["analysis", "breakdown", "choice"],
                            "additionalProperties": False,
                        },
                    },
                },
                "usage": {"include": True},
            }
            if self.model == "openai/gpt-5-high":  # high reasoning effort
                payload["reasoning"] = {"effort": "high"}

            log.info(f"Sending request to {model_to_call} - Payload: {payload}")
            resp = SESSION.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            )
            latency = time.time() - start

            resp.raise_for_status()
            data = resp.json()
            try:
                content = data["choices"][0]["message"]["content"]
            except Exception:
                content = None

            cost = data.get("usage", {}).get("cost") or 0
            upstream_cost = (
                data.get("usage", {}).get("cost_details", {}).get("upstream_cost") or 0
            )
            total_cost = cost + upstream_cost
            log.info(
                f"Received response from {self.model} - Cost: {total_cost:.3f}€ (including {upstream_cost:.3f}€ upstream) - Latency: {latency:.1f}s - Content: {content}"
            )

            return {"completion": data, "cost": total_cost, "latency": latency}
        except Exception as e:
            log.error(
                f"Error getting response from {self.model}: {type(e).__name__} - {e}"
            )
            return None
