import time
import os


class PerformanceLogger:
    def __init__(self):
        self.log_dir = os.path.join(os.path.dirname(
            os.path.dirname(__file__)), 'logs')
        os.makedirs(self.log_dir, exist_ok=True)

    def log(self, request_id: str, provider: str, duration: float, cache_hit: bool, fallback_chain: list, errors: list):
        fpath = os.path.join(self.log_dir, 'performance.log')
        data = {
            'timestamp': time.time(),
            'request_id': request_id,
            'provider': provider,
            'duration_ms': int(duration * 1000),
            'cache_hit': cache_hit,
            'fallback_chain': fallback_chain,
            'errors': errors
        }
        with open(fpath, 'a') as f:
            f.write(str(data) + '\n')
