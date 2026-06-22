import json
import re
import logging
from typing import Dict, Any

logger = logging.getLogger("safe_json_parser")


class SafeJsonParser:
    @staticmethod
    def repair_truncated_json(s: str) -> str:
        stack = []
        in_string = False
        escape = False
        last_good_pos = 0

        for i, c in enumerate(s):
            if in_string:
                if escape:
                    escape = False
                elif c == '\\':
                    escape = True
                elif c == '"':
                    in_string = False
            else:
                if c == '"':
                    in_string = True
                elif c in ['{', '[']:
                    stack.append((c, i))
                elif c in ['}', ']']:
                    if stack:
                        stack.pop()
                        if len(stack) <= 2:
                            last_good_pos = i + 1
                elif c == ',' and len(stack) <= 2:
                    last_good_pos = i

        if not stack:
            return s

        if last_good_pos > 0:
            repaired = s[:last_good_pos]
            stack_at_good = []
            in_string = False
            escape = False
            for c in repaired:
                if in_string:
                    if escape:
                        escape = False
                    elif c == '\\':
                        escape = True
                    elif c == '"':
                        in_string = False
                else:
                    if c == '"':
                        in_string = True
                    elif c in ['{', '[']:
                        stack_at_good.append(c)
                    elif c in ['}', ']']:
                        if stack_at_good:
                            stack_at_good.pop()

            closers = []
            for sym in reversed(stack_at_good):
                if sym == '{':
                    closers.append('}')
                elif sym == '[':
                    closers.append(']')
            return repaired + "".join(closers)
        return s

    @staticmethod
    def parse(raw_text: str) -> Dict[str, Any]:
        """
        Safely parses JSON out of a noisy LLM response.
        Strips <think> blocks and markdown formatting.
        """
        # 1. Remove <think>...</think> blocks completely
        text = re.sub(r'<think>.*?</think>', '', raw_text, flags=re.DOTALL)

        # 2. Extract JSON from markdown fences if present
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```',
                               text, re.DOTALL | re.IGNORECASE)
        if json_match:
            text = json_match.group(1)
        else:
            # 3. If no fences, find the first '{' and last '}'
            start_idx = text.find('{')
            end_idx = text.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                text = text[start_idx:end_idx + 1]

        # 4. Attempt basic JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Initial JSON parse failed: {e}")
            # Try to repair trailing commas first
            repaired = re.sub(r',\s*}', '}', text)
            repaired = re.sub(r',\s*]', ']', repaired)
            try:
                return json.loads(repaired)
            except Exception:
                # If still fails, try healing truncation
                try:
                    healed = SafeJsonParser.repair_truncated_json(text)
                    healed = re.sub(r',\s*}', '}', healed)
                    healed = re.sub(r',\s*]', ']', healed)
                    return json.loads(healed)
                except Exception as e2:
                    logger.error(f"Healed JSON parse also failed: {e2}")
                    raise ValueError(
                        "Could not parse JSON from LLM response") from e2
