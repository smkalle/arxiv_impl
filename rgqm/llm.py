import os
import json
import hashlib
from collections import OrderedDict

MODEL = "gemini-3.5-flash"
THINKING_META = "medium"
THINKING_EVAL = "low"

_token_log = {"input": 0, "output": 0}
_reviewer_cache = OrderedDict()
_reviewer_cache_maxsize = 256
_reviewer_cache_stats = {"hits": 0, "misses": 0}

try:
    import google.generativeai as genai  # noqa: F401
    _HAS_GENAI = True
except Exception:
    genai = None
    _HAS_GENAI = False


def reset_token_log():
    global _token_log
    _token_log = {"input": 0, "output": 0}


def reset_reviewer_cache():
    _reviewer_cache.clear()
    _reviewer_cache_stats["hits"] = 0
    _reviewer_cache_stats["misses"] = 0


def cache_reviewer_key(solution_hash, reviewer_fn_hash):
    if not solution_hash or not reviewer_fn_hash:
        return None
    return f"{solution_hash}:{reviewer_fn_hash}"


def _hash_text(value):
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def cache_reviewer_get(cache_key):
    if cache_key is None:
        return None
    if cache_key in _reviewer_cache:
        _reviewer_cache.move_to_end(cache_key)
        _reviewer_cache_stats["hits"] += 1
        return _reviewer_cache[cache_key]
    return None


def cache_reviewer_set(cache_key, value):
    if cache_key is None:
        return
    _reviewer_cache[cache_key] = value
    _reviewer_cache.move_to_end(cache_key)
    if len(_reviewer_cache) > _reviewer_cache_maxsize:
        _reviewer_cache.popitem(last=False)


def cache_reviewer_stats():
    return dict(_reviewer_cache_stats)


def preload_reviewer_cache(utility_records):
    if not utility_records:
        return
    for rec in utility_records:
        if rec.get("role") != "reviewer":
            continue
        cache_key = cache_reviewer_key(rec.get("solution_hash"), rec.get("reviewer_fn_hash"))
        if cache_key is None:
            continue
        cached = rec.get("reviewer_output_cache")
        if cached is None:
            continue
        cache_reviewer_set(cache_key, str(cached))


def _stub_response(prompt):
    s = (prompt or "").lower()
    if "reviewer" in s and ("score" in s or "accept" in s or "pass" in s):
        return json.dumps({"score": 1, "rationale": "stub accept"})
    if "meta" in s or "diff" in s or "patch" in s or "coder_fn" in s:
        return json.dumps({
            "coder_fn": "def solve(task):\n    return ''\n",
            "reviewer_fn": "def review(solution, task):\n    return 1\n",
        })
    return "def solve(task):\n    return ''\n"


def _raw_call(prompt, system=None, thinking=THINKING_EVAL):
    global _token_log
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if key and _HAS_GENAI:
        try:
            import google.generativeai as genai
            genai.configure(api_key=key)
            model = genai.GenerativeModel(
                model_name=MODEL,
                system_instruction=system,
                generation_config={"thinking_level": thinking},
            )
            resp = model.generate_content(prompt)
            _token_log["input"] += resp.usage_metadata.prompt_token_count
            _token_log["output"] += resp.usage_metadata.candidates_token_count
            return resp.text
        except Exception as exc:
            raise RuntimeError(f"genai call failed: {exc}") from exc
    _token_log["input"] += len((prompt or "").split()) + len((system or "").split())
    _token_log["output"] += 16
    return _stub_response(prompt)


def call(prompt, system=None, thinking=THINKING_EVAL, cache_key=None):
    if cache_key is not None:
        hit = cache_reviewer_get(cache_key)
        if hit is not None:
            return hit
        _reviewer_cache_stats["misses"] += 1
    resp = _raw_call(prompt, system=system, thinking=thinking)
    if cache_key is not None:
        cache_reviewer_set(cache_key, resp)
    return resp


def blended_tokens():
    return _token_log["input"] + 5 * _token_log["output"]


def blended_cost_usd():
    return _token_log["input"] / 1e6 * 1.50 + _token_log["output"] / 1e6 * 9.00
