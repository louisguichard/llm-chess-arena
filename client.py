"""LLM client."""

import os
import time
import json
import httpx
from openai import OpenAI

from dotenv import load_dotenv
from logger import log
from prompts import JSON_SCHEMA

# Load OpenRouter API key from environment variables
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY not found in environment variables")


# Default timeouts
FIRST_CHUNK_TIMEOUT = 120
NEXT_CHUNK_TIMEOUT = 60


class OpenRouterClient:
    """Simple OpenRouter-backed client using OpenAI SDK over OpenRouter."""

    def __init__(
        self,
        model,
    ):
        self.model = model
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
            timeout=httpx.Timeout(
                connect=10,  # max to establish the connection
                read=120,  # max between different chunks
                write=10,  # max to send data
                pool=600,  # max lifetime of the connection
            ),
        )

    def name(self):
        return self.model

    def chat(self, messages):
        try:
            extra_body = {
                "usage": {"include": True},
                # "provider": {"require_parameters": True},
            }
            if self.model == "openai/gpt-5-high":  # high reasoning effort
                model_to_call = "openai/gpt-5"
                extra_body["reasoning"] = {"effort": "high"}
            else:
                model_to_call = self.model

            log.info(f"Sending request to {model_to_call}")
            log.debug(f"Detailed prompt sent to {model_to_call}: {messages}")
            completion = None
            content = None
            start = time.time()
            with self.client.beta.chat.completions.stream(
                model=model_to_call,
                messages=messages,
                response_format={"type": "json_schema", "json_schema": JSON_SCHEMA},
                extra_body=extra_body,
            ) as stream:
                try:
                    # for _ in stream:
                    #     pass
                    completion = stream.get_final_completion()
                except Exception as e:
                    log.error(f"Error while streaming {self.model} response: {e}")
            latency = time.time() - start
            if completion:
                try:
                    content = completion.choices[0].message.content
                except Exception as e:
                    log.error(
                        f"Error parsing response from {self.model}: {e} - Completion: {completion}"
                    )
                if content:
                    try:
                        cost = completion.usage.cost
                        upstream_cost = (
                            completion.usage.cost_details.get("upstream_inference_cost")
                            or 0
                        )
                        total_cost = cost + upstream_cost
                    except Exception as e:
                        log.error(f"Error getting cost from {self.model}: {e}")
                        total_cost, upstream_cost = 0, 0
                    move = json.loads(content).get("choice")
                    log.info(
                        f"Received response from {self.model} - Cost: {total_cost:.3f}€ (including {upstream_cost:.3f}€ upstream) - Latency: {latency:.1f}s - Move: {move}"
                    )
                    log.debug(f"Detailed response from {self.model}: {content}")
                    return {
                        "completion": content,
                        "cost": total_cost,
                        "latency": latency,
                    }
                else:
                    log.warning(f"No content received from {self.model}")
                    log.debug(f"Completion: {completion}")
                    return None
        except Exception as e:
            log.error(f"Error getting response from {self.model}: {e}")
            return None
