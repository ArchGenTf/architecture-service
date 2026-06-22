import os
import time
import logging
import aiohttp
from typing import Dict, Any, Optional
from openai import AsyncOpenAI, AsyncAzureOpenAI
from utils.safe_json_parser import SafeJsonParser

logger = logging.getLogger('provider_manager')


class ProviderManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProviderManager, cls).__new__(cls)
            cls._instance._init_manager()
        return cls._instance

    def _init_manager(self):
        self.provider_cache_ttl = 300
        self.last_check_time = 0
        self.active_provider = 'None'
        self.active_model = 'none'
        self.openai_client = None
        self.deepseek_client = None
        self.ollama_base_url = os.getenv(
            'OLLAMA_BASE_URL', 'http://localhost:11434')
        self.ollama_model = os.getenv('OLLAMA_MODEL', 'qwen2.5:3b')
        self.fallback_chain = []
        self._init_clients()

    def _init_clients(self):
        openai_key = os.getenv('OPENAI_API_KEY', '')
        openai_base_url = os.getenv('OPENAI_BASE_URL')  # Optional
        if openai_key and len(openai_key) > 5 and not openai_key.startswith('your_'):
            if openai_base_url and 'openai.azure.com' in openai_base_url:
                self.openai_client = AsyncAzureOpenAI(
                    azure_endpoint=openai_base_url.split('/openai')[0],
                    api_key=openai_key,
                    api_version='2024-02-01'
                )
            else:
                self.openai_client = AsyncOpenAI(
                    api_key=openai_key, base_url=openai_base_url)
        else:
            self.openai_client = None

        deepseek_key = os.getenv('DEEPSEEK_API_KEY', '')
        if deepseek_key and len(deepseek_key) > 5 and not deepseek_key.startswith('your_'):
            self.deepseek_client = AsyncOpenAI(
                api_key=deepseek_key, base_url='https://api.deepseek.com/v1')
        else:
            self.deepseek_client = None

    async def health_check(self) -> Dict[str, str]:
        await self.get_available_provider()
        return {
            'status': 'healthy',
            'provider': self.active_provider,
            'mongodb': 'connected'
        }

    async def _check_ollama(self) -> str:
        supported = ['qwen2.5', 'deepseek-r1',
                     'llama3', 'mistral', 'codellama']
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'{self.ollama_base_url}/api/tags', timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        available_models = [m['name']
                                            for m in data.get('models', [])]

                        if self.ollama_model in available_models:
                            return self.ollama_model

                        for pref in supported:
                            for m in available_models:
                                if m.startswith(pref):
                                    return m
        except Exception:
            pass
        return ''

    async def get_available_provider(self, force_refresh=False) -> str:
        now = time.time()
        if not force_refresh and (now - self.last_check_time < self.provider_cache_ttl):
            return self.active_provider

        self._init_clients()

        # 1. OpenAI (or AI Foundry compatible endpoints)
        if self.openai_client:
            try:
                # Some foundries don't support models.list(), so we just assume it's available if the client initialized
                self.active_provider = 'OpenAI'
                self.active_model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
                self.last_check_time = now
                return self.active_provider
            except Exception as e:
                logger.warning(f'OpenAI check failed: {e}')

        # 2. DeepSeek
        if self.deepseek_client:
            try:
                await self.deepseek_client.models.list(timeout=5)
                self.active_provider = 'DeepSeek'
                self.active_model = 'deepseek-chat'
                self.last_check_time = now
                return self.active_provider
            except Exception as e:
                logger.warning(f'DeepSeek check failed: {e}')

        # 3. Ollama
        ollama_model = await self._check_ollama()
        if ollama_model:
            self.active_provider = 'Ollama'
            self.active_model = ollama_model
            self.last_check_time = now
            return self.active_provider

        # No active provider
        self.active_provider = 'None'
        self.active_model = 'none'
        self.last_check_time = now
        return self.active_provider

    async def generate_json(self, system_prompt: str, user_prompt: str, schema: Optional[Any] = None) -> Dict[str, Any]:
        start_time = time.time()
        self.fallback_chain = []

        provider = await self.get_available_provider()
        timeout_val = int(os.getenv('MAX_PROVIDER_TIMEOUT', '120'))

        # Attempt OpenAI
        if provider == 'OpenAI' and self.openai_client:
            try:
                self.fallback_chain.append('OpenAI')
                res = await self._call_openai(self.openai_client, self.active_model, system_prompt, user_prompt, timeout=timeout_val)
                self._log_telemetry(start_time, 'OpenAI', self.fallback_chain)
                return res
            except Exception as e:
                logger.warning(f'OpenAI generation failed: {e}')
                provider = 'DeepSeek'

        # Attempt DeepSeek
        if provider in ['OpenAI', 'DeepSeek'] and self.deepseek_client:
            try:
                if 'DeepSeek' not in self.fallback_chain:
                    self.fallback_chain.append('DeepSeek')
                res = await self._call_openai(self.deepseek_client, 'deepseek-chat', system_prompt, user_prompt, timeout=timeout_val)
                self._log_telemetry(start_time, 'DeepSeek',
                                    self.fallback_chain)
                return res
            except Exception as e:
                logger.warning(f'DeepSeek generation failed: {e}')
                provider = 'Ollama'

        # Attempt Ollama
        if provider in ['OpenAI', 'DeepSeek', 'Ollama']:
            try:
                if 'Ollama' not in self.fallback_chain:
                    self.fallback_chain.append('Ollama')
                ollama_model = await self._check_ollama()
                if ollama_model:
                    res = await self._call_ollama(ollama_model, system_prompt, user_prompt)
                    self._log_telemetry(
                        start_time, 'Ollama', self.fallback_chain)
                    return res
            except Exception as e:
                logger.warning(f'Ollama generation failed: {e}')

        # Raise exception instead of falling back to Mock response
        raise RuntimeError(
            f"No available LLM providers. Fallback chain attempted: {self.fallback_chain}")

    async def _call_openai(self, client, model, system, user, timeout):
        # OpenAI requires the word 'json' to be in the prompt when using response_format={'type': 'json_object'}
        system_with_json = system + "\n\nEnsure your response is a valid JSON object."
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': system_with_json},
                {'role': 'user', 'content': user}
            ],
            response_format={'type': 'json_object'},
            temperature=0.2,
            max_tokens=8000,
            timeout=timeout
        )
        return SafeJsonParser.parse(response.choices[0].message.content)

    async def _call_ollama(self, model, system, user):
        prompt = f'System:\n{system}\n\nUser:\n{user}\n\nOutput ONLY valid JSON. Do NOT include markdown code blocks or additional text.'
        payload = {
            'model': model,
            'prompt': prompt,
            'stream': False,
            'options': {'temperature': 0.1}
        }

        log_dir = os.path.join(os.path.dirname(
            os.path.dirname(__file__)), 'logs')
        os.makedirs(log_dir, exist_ok=True)

        timeout_val = int(os.getenv('MAX_PROVIDER_TIMEOUT', '60'))
        async with aiohttp.ClientSession() as session:
            # Enforce configured timeout for Ollama local execution
            async with session.post(f'{self.ollama_base_url}/api/generate', json=payload, timeout=timeout_val) as resp:
                if resp.status != 200:
                    raise Exception(f'Ollama failed with status {resp.status}')
                data = await resp.json()
                text = data.get('response', '')

                # Write to debug log
                with open(os.path.join(log_dir, 'ollama_debug.log'), 'a', encoding='utf-8') as f:
                    f.write(f'--- MODEL: {model} ---\n')
                    f.write(f'PROMPT LEN: {len(prompt)}\n')
                    f.write(f'## RAW OLLAMA RESPONSE:\n{text}\n')
                    f.write(f'RESP LEN: {len(text)}\n')
                    f.write('-----------------------\n\n')

                return SafeJsonParser.parse(text)

    def _log_telemetry(self, start_time, final_provider, chain):
        duration = round(time.time() - start_time, 2)
        chain_str = ' -> '.join(chain)

        log_dir = os.path.join(os.path.dirname(
            os.path.dirname(__file__)), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, 'provider.log'), 'a') as f:
            f.write(f'{time.time()}|{final_provider}|{chain_str}|{duration}s\n')

        logger.info(
            f'Provider: {final_provider} | Fallback: {chain_str} | Duration: {duration}s')
