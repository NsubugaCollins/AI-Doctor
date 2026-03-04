import os
import json
import logging
import time
from typing import List, Dict, Any, Optional
from openai import OpenAI, APIError, RateLimitError, APIStatusError
from groq import Groq
try:
    from openai import NotFoundError  # type: ignore
except Exception:  # pragma: no cover
    NotFoundError = None  # type: ignore
from django.conf import settings
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

class OpenAIService:
    """
    Centralized service for all LLM interactions (OpenAI or DeepSeek)
    with retry logic, token tracking, and proper DeepSeek support.
    """

    def __init__(self):
        groq_key = getattr(settings, "GROQ_API_KEY", os.getenv("GROQ_API_KEY"))
        deepseek_key = getattr(settings, "DEEPSEEK_API_KEY", os.getenv("DEEPSEEK_API_KEY"))

        if groq_key:
            self.provider = "groq"
            self.api_key = groq_key
            self.groq_client = Groq(api_key=self.api_key)
            self.client = None
            self.base_url = None
            self.model = getattr(
                settings,
                "GROQ_MODEL",
                os.getenv("GROQ_MODEL", "qwen-2.5-32b"),
            )
            logger.info(f"OpenAIService initialized with Groq model: {self.model}")

        elif deepseek_key:
            # DeepSeek OpenAI-compatible endpoint
            self.provider = "deepseek"
            self.api_key = deepseek_key
            self.base_url = getattr(
               settings,
                "DEEPSEEK_BASE_URL",
                os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            )
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            self.groq_client = None
           
            self.model = getattr(
                settings,
                "DEEPSEEK_MODEL",
                os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            )
            logger.info(f"OpenAIService initialized with DeepSeek model: {self.model}")
        else:
            # Default: OpenAI
            self.provider = "openai"
            self.api_key = getattr(settings, "OPENAI_API_KEY", os.getenv("OPENAI_API_KEY"))
            if not self.api_key:
                raise ValueError(
                    "No LLM API key configured. Set GROQ_API_KEY (preferred), "
                    "or DEEPSEEK_API_KEY, or OPENAI_API_KEY in your environment/.env."
                )
            self.client = OpenAI(api_key=self.api_key)
            self.groq_client = None
            self.base_url = None
            self.model = getattr(settings, "OPENAI_MODEL", "gpt-4o-mini")
            logger.info(f"OpenAIService initialized with OpenAI model: {self.model}")

        self.max_tokens = getattr(settings, "OPENAI_MAX_TOKENS", 4000)
        self.temperature = getattr(settings, "OPENAI_TEMPERATURE", 0.3)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((RateLimitError, APIError, APIStatusError)),
    )
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict] = None,
    ) -> str:
        """
        Send a chat completion request to OpenAI or DeepSeek with retry logic.
        """
        start_time = time.time()

        # Groq path
        if getattr(self, "provider", "") == "groq":
            msgs = list(messages)
            if response_format:
                msgs.append(
                    {
                        "role": "system",
                        "content": "Return ONLY a single valid JSON object. No markdown, no extra text.",
                    }
                )
            response = self.groq_client.chat.completions.create(
                model=self.model,
                messages=msgs,
                temperature=temperature or self.temperature,
            )
            return response.choices[0].message.content
        candidate_models: List[str] = []

        configured = self.model
        if configured:
            candidate_models.append(configured)

        # Add sensible fallbacks depending on provider
        if getattr(self, "provider", "") == "deepseek" or "deepseek" in (self.base_url or "") or "deepseek" in (configured or ""):
            for m in ("deepseek-chat", "deepseek-coder"):
                if m not in candidate_models:
                    candidate_models.append(m)
        else:
            for m in ("gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"):
                if m not in candidate_models:
                    candidate_models.append(m)

        logger.debug(f"LLM request messages: {json.dumps(messages)[:200]}...")

        last_exc: Exception | None = None
        for model in candidate_models:
            params: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature or self.temperature,
                "max_tokens": max_tokens or self.max_tokens,
            }

            if response_format:
                params["response_format"] = {"type": "json_object"}

            try:
                response = self.client.chat.completions.create(**params)
                result = response.choices[0].message.content

                if model != self.model:
                    logger.warning(f"Model fallback: {self.model} -> {model}")
                    self.model = model

                if hasattr(response, "usage"):
                    logger.info(
                        f"Tokens used: {response.usage.total_tokens} "
                        f"(prompt: {response.usage.prompt_tokens}, "
                        f"completion: {response.usage.completion_tokens}) "
                        f"in {time.time() - start_time:.2f}s"
                    )
                return result

            except APIStatusError as e:
                logger.error(f"APIStatusError (HTTP {e.status_code}): {e.response}")
                last_exc = e
            except Exception as e:
                last_exc = e
                msg = str(e)
                is_model_not_found = (
                    "model" in msg.lower() and ("does not exist" in msg.lower() or "model_not_found" in msg.lower())
                )
                if NotFoundError is not None and isinstance(e, NotFoundError):
                    is_model_not_found = True

                if is_model_not_found:
                    logger.error(f"Model not found for '{model}': {e}")
                    continue
                raise

        assert last_exc is not None
        raise last_exc

    def structured_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        response = self.chat_completion(
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )

        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw response: {response[:500]}")

            import re
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except Exception:
                    pass

            return {
                "error": "Failed to parse response",
                "raw_response": response[:500],
                "differential_diagnosis": [
                    {
                        "condition": "Unable to determine",
                        "probability": 0.5,
                        "supporting_evidence": ["Error parsing AI response"],
                        "ruling_out_factors": [],
                    }
                ],
            }

    def simple_completion(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> str:
        messages: List[Dict[str, str]] = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        return self.chat_completion(messages, temperature=temperature)

    def count_tokens(self, text: str) -> int:
        return len(text) // 4

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        prompt_cost = (prompt_tokens / 1000) * 0.03
        completion_cost = (completion_tokens / 1000) * 0.06
        return prompt_cost + completion_cost


# Singleton instance
_openai_service: Optional[OpenAIService] = None

def get_openai_service() -> OpenAIService:
    global _openai_service
    if _openai_service is None:
        _openai_service = OpenAIService()
    return _openai_service