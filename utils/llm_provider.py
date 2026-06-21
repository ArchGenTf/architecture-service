import os
import json
import logging
import aiohttp
import re
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger("llm_provider")

class AIProvider(ABC):
    provider_name = "Unknown"
    model_name = "unknown"

    @abstractmethod
    async def generate_json(self, system_prompt: str, user_prompt: str, schema: Optional[Any] = None) -> Dict[str, Any]:
        """Generates a JSON response from the underlying LLM."""
        pass


class OllamaProvider(AIProvider):
    def __init__(self):
        self.provider_name = "Ollama"
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = os.getenv("OLLAMA_MODEL", "deepseek-r1:8b")
        self.model_name = self.model
        logger.info(f"Initialized OllamaProvider using model: {self.model} at {self.base_url}")

    async def generate_json(self, system_prompt: str, user_prompt: str, schema: Optional[Any] = None) -> Dict[str, Any]:
        prompt = f"System:\n{system_prompt}\n\nUser:\n{user_prompt}\n\nOutput ONLY valid JSON. Do NOT include markdown code blocks or additional text."
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            # "format": "json",
            "options": {
                "temperature": 0.1
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/api/generate", json=payload, timeout=300) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"Ollama API error ({resp.status}): {error_text}")
                        raise Exception(f"Ollama failed with status {resp.status}")
                        
                    data = await resp.json()
                    response_text = data.get("response", "")
                    
                    return self._clean_and_parse_json(response_text)
        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            raise RuntimeError(f"Ollama request failed: {e}") from e

    def _clean_and_parse_json(self, text: str) -> Dict[str, Any]:
        # Strip <think>...</think> tags which DeepSeek outputs
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        
        # Strip markdown code block wrappers
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
            
        if text.endswith("```"):
            text = text[:-3]
            
        text = text.strip()
        
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Ollama output: {e}\nRaw Output: {text}")
            raise

class OpenAIProvider(AIProvider):
    def __init__(self):
        from utils.openai_client import OpenAIClient
        self.client = OpenAIClient()
        self.provider_name = "OpenAI"
        self.model_name = self.client.model
        logger.info("Initialized OpenAIProvider wrapper.")

    async def generate_json(self, system_prompt: str, user_prompt: str, schema: Optional[Any] = None) -> Dict[str, Any]:
        return await self.client.generate_json(system_prompt, user_prompt, schema)


class MockProvider(AIProvider):
    def __init__(self):
        self.provider_name = "Mock"
        self.model_name = "mock"

    async def generate_json(self, system_prompt: str, user_prompt: str, schema: Optional[Any] = None) -> Dict[str, Any]:
        from utils.openai_client import OpenAIClient
        return OpenAIClient._generate_mock_response(system_prompt, user_prompt)


class ResilientProvider(AIProvider):
    def __init__(self, primary: AIProvider, secondary: Optional[AIProvider] = None, fallback: Optional[AIProvider] = None):
        self.primary = primary
        self.secondary = secondary
        self.fallback = fallback
        self.provider_name = getattr(primary, "provider_name", "Resilient")
        self.model_name = getattr(primary, "model_name", "unknown")
        self.last_active_provider = getattr(primary, "provider_name", "Resilient")
        self.last_active_model = getattr(primary, "model_name", "unknown")
        self.last_fallback_trigger = "none"

    def _classify_reason(self, error: Exception, provider_name: str) -> str:
        error_text = str(error).lower()
        if provider_name.lower() == "openai":
            if "quota" in error_text or "insufficient_quota" in error_text or "rate_limit" in error_text:
                return f"OpenAI quota/rate-limit error: {error}"
            return f"OpenAI failure: {error}"
        if provider_name.lower() == "ollama":
            return f"Ollama failure: {error}"
        return f"{provider_name} failure: {error}"

    def _log_active(self, provider: AIProvider, fallback_reason: str) -> None:
        logger.info(
            "Active Provider: %s | Model Name: %s | Fallback Trigger Reason: %s",
            getattr(provider, "provider_name", provider.__class__.__name__),
            getattr(provider, "model_name", "unknown"),
            fallback_reason,
        )

    async def generate_json(self, system_prompt: str, user_prompt: str, schema: Optional[Any] = None) -> Dict[str, Any]:
        try:
            self.last_active_provider = getattr(self.primary, "provider_name", "Primary")
            self.last_active_model = getattr(self.primary, "model_name", "unknown")
            self.last_fallback_trigger = "none"
            self._log_active(self.primary, "none")
            return await self.primary.generate_json(system_prompt, user_prompt, schema)
        except Exception as primary_error:
            primary_reason = self._classify_reason(primary_error, getattr(self.primary, "provider_name", "primary"))
            logger.warning(primary_reason)

            if self.secondary is not None:
                try:
                    self.last_active_provider = getattr(self.secondary, "provider_name", "Secondary")
                    self.last_active_model = getattr(self.secondary, "model_name", "unknown")
                    self.last_fallback_trigger = primary_reason
                    self._log_active(self.secondary, primary_reason)
                    return await self.secondary.generate_json(system_prompt, user_prompt, schema)
                except Exception as secondary_error:
                    secondary_reason = self._classify_reason(secondary_error, getattr(self.secondary, "provider_name", "secondary"))
                    logger.warning(secondary_reason)
                    if self.fallback is not None:
                        self.last_active_provider = getattr(self.fallback, "provider_name", "Mock")
                        self.last_active_model = getattr(self.fallback, "model_name", "mock")
                        self.last_fallback_trigger = secondary_reason
                        self._log_active(self.fallback, secondary_reason)
                        return await self.fallback.generate_json(system_prompt, user_prompt, schema)
                    else:
                        raise RuntimeError(f"All providers failed. Primary: {primary_reason}. Secondary: {secondary_reason}") from secondary_error

            if self.fallback is not None:
                self.last_active_provider = getattr(self.fallback, "provider_name", "Mock")
                self.last_active_model = getattr(self.fallback, "model_name", "mock")
                self.last_fallback_trigger = primary_reason
                self._log_active(self.fallback, primary_reason)
                return await self.fallback.generate_json(system_prompt, user_prompt, schema)
            else:
                raise RuntimeError(f"Primary provider failed and no fallback configured. Error: {primary_reason}") from primary_error


def get_llm_provider() -> AIProvider:
    provider_name = os.getenv("AI_PROVIDER", "").lower()
    ollama_provider = OllamaProvider()
    openai_key = os.getenv("OPENAI_API_KEY", "")
    openai_available = bool(openai_key and not openai_key.startswith("your_") and len(openai_key) > 5)

    if provider_name == "ollama":
        return ResilientProvider(primary=ollama_provider, fallback=None)

    if provider_name == "openai" or openai_available:
        openai_provider = OpenAIProvider()
        return ResilientProvider(primary=openai_provider, secondary=ollama_provider, fallback=None)

    return ResilientProvider(primary=ollama_provider, fallback=None)
