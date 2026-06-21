import hashlib
import json
import os
import time
from typing import Optional, Dict, Any

class CacheManager:
    def __init__(self):
        self.cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cache')
        os.makedirs(self.cache_dir, exist_ok=True)
        self.enabled = os.getenv('CACHE_ENABLED', 'true').lower() == 'true'
        self.ttl = int(os.getenv('CACHE_TTL', '86400'))

    def _hash(self, req_dict: Dict[str, Any]) -> str:
        s = json.dumps(req_dict, sort_keys=True)
        return hashlib.sha256(s.encode('utf-8')).hexdigest()

    def get(self, requirements: Any) -> Optional[Dict[str, Any]]:
        if not self.enabled: return None
        h = self._hash(requirements.model_dump())
        fpath = os.path.join(self.cache_dir, f'{h}.json')
        if os.path.exists(fpath):
            if time.time() - os.path.getmtime(fpath) < self.ttl:
                with open(fpath, 'r') as f:
                    return json.load(f)
        return None

    def set(self, requirements: Any, response: Dict[str, Any]):
        if not self.enabled: return
        os.makedirs(self.cache_dir, exist_ok=True)
        h = self._hash(requirements.model_dump())
        fpath = os.path.join(self.cache_dir, f'{h}.json')
        with open(fpath, 'w') as f:
            json.dump(response, f)
