"""LLM client."""

import os
import time
import json
import httpx
import requests
from openai import OpenAI

from dotenv import load_dotenv
from logger import log
from prompts import JSON_SCHEMA

# Load API keys from environment variables
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise RuntimeError("OPENROUTER_API_KEY not found in environment variables")
GROK_API_KEY = os.getenv("GROK_API_KEY")
if not GROK_API_KEY:
    raise RuntimeError("GROK_API_KEY not found in environment variables")


class LLMClient:
    """Simple OpenRouter-backed client using OpenAI SDK over OpenRouter."""

    def __init__(
        self,
        model,
    ):
        self.model = model
        if model == "x-ai/grok-4":
            self.client = OpenAI(
                base_url="https://api.x.ai/v1",
                api_key=GROK_API_KEY,
                timeout=httpx.Timeout(
                    connect=10,  # max to establish the connection
                    read=120,  # max between different chunks
                    write=10,  # max to send data
                    pool=600,  # max lifetime of the connection
                ),
            )
        else:
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

    def get_providers(self, model_to_call):
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
        endpoints_url = f"https://openrouter.ai/api/v1/models/{model_to_call}/endpoints"
        response = requests.get(endpoints_url, headers=headers, timeout=20)
        if response.status_code == 200:
            data = response.json()
            providers = (data or {}).get("data", {}).get("endpoints", [])
            providers_with_format = [
                provider["provider_name"]
                for provider in providers
                if "response_format" in provider.get("supported_parameters", [])
            ]
            log.debug(
                f"Providers supporting response_format for {model_to_call}: {providers_with_format}"
            )
            return providers_with_format
        else:
            log.warning(
                f"Failed to request providers for {model_to_call} (status {response.status_code})."
            )
            return None

    def chat(self, messages):
        try:
            extra_body = {"usage": {"include": True}}
            if self.model == "openai/gpt-5-high":  # high reasoning effort
                model_to_call = "openai/gpt-5"
                extra_body["reasoning"] = {"effort": "high"}
            elif self.model == "x-ai/grok-4":
                model_to_call = "grok-4"
            else:
                model_to_call = self.model

            # Restrict to providers that support response_format for this model
            providers = self.get_providers(model_to_call)
            if providers:
                extra_body["provider"] = {"only": providers}
            else:
                log.warning(
                    f"No provider supports response_format for {model_to_call}. Proceeding without choosing a provider."
                )
            log.info(f"Sending request to {model_to_call}")
            log.debug(f"Detailed prompt sent to {model_to_call}: {messages}")
            start = time.time()
            stream = self.client.chat.completions.create(
                model=model_to_call,
                messages=messages,
                response_format={"type": "json_schema", "json_schema": JSON_SCHEMA},
                extra_body=extra_body,
                stream=True,
            )
            contents = []
            for i, chunk in enumerate(stream):
                if i < 3 or i % 1000 == 0:
                    log.debug(f"Chunk {i}: {chunk}")
                contents.append(chunk.choices[0].delta.content or "")
            log.debug(f"Chunk {i} (last one): {chunk}")
            content = "".join(contents)
            log.debug(f"Final content: {content}")
            latency = time.time() - start
            if content:
                try:
                    # Cost should be in the last chunk
                    cost = chunk.usage.cost
                    upstream_cost = (
                        chunk.usage.cost_details.get("upstream_inference_cost") or 0
                    )
                    total_cost = cost + upstream_cost
                except Exception as e:
                    log.warning(f"💰 Error getting cost from {self.model}: {e}")
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
                log.warning(
                    f"No content received from {self.model} - Latency: {latency:.1f}s"
                )
                return None
        except Exception as e:
            log.error(f"Error getting response from {self.model}: {e}")
            return None
