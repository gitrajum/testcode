"""
Patch agent_framework/observability.py for compatibility with
opentelemetry-semantic-conventions >= 0.50b0.

agent-framework-core==1.0.0b260107 accesses LLM_* attributes via the base
SpanAttributes class (opentelemetry.trace.SpanAttributes). These were injected by
opentelemetry-semantic-conventions-ai < 0.4.0; in >= 0.4.0 that monkey-patching
was removed, causing AttributeError at import time.

Strategy: build the KNOWN mapping by parsing source files of every installed
opentelemetry-related package with regex. This sidesteps all class-hierarchy /
metaclass issues that break vars() / dir() approaches. A hardcoded fallback
covers any values that regex misses.
"""

import importlib.metadata
import importlib.util
import os
import re
import sys

# ---------------------------------------------------------------------------
# Step 1: First find all attributes ACTUALLY USED in the target file so we
#         know exactly what we need to replace.
# ---------------------------------------------------------------------------
TARGET_PATH = "/usr/local/lib/python3.11/site-packages/agent_framework/observability.py"

with open(TARGET_PATH, "r") as f:
    content = f.read()

needed = set(re.findall(r"SpanAttributes\.(LLM_\w+)", content))
print("LLM_ attributes needed:", sorted(needed))

# ---------------------------------------------------------------------------
# Step 2: Parse source files of candidate packages to extract LLM_* = "..." .
#         We search any .py file under site-packages that looks relevant.
# ---------------------------------------------------------------------------
SEARCH_DIRS = [
    "/usr/local/lib/python3.11/site-packages/opentelemetry/semconv_ai",
    "/usr/local/lib/python3.11/site-packages/opentelemetry_semantic_conventions_ai",
    "/usr/local/lib/python3.11/site-packages/opentelemetry/semconv",
]
# Also try importlib to locate the semconv_ai package
try:
    spec = importlib.util.find_spec("opentelemetry.semconv_ai")
    if spec and spec.origin:
        SEARCH_DIRS.insert(0, os.path.dirname(spec.origin))
except Exception:
    pass

KNOWN = {}
for search_dir in SEARCH_DIRS:
    if not os.path.isdir(search_dir):
        continue
    for root, _dirs, files in os.walk(search_dir):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath) as f:
                    src = f.read()
            except Exception:
                continue
            for m in re.finditer(r'\b(LLM_\w+)\s*=\s*["\']([^"\']+)["\']', src):
                KNOWN.setdefault(m.group(1), m.group(2))

print("Attributes found by source scan:", sorted(KNOWN.keys()))

# ---------------------------------------------------------------------------
# Step 3: Hardcoded fallback for well-known OpenLLMetry semconv values.
#         These are the canonical string values used by traceloop/openllmetry
#         before the monkey-patching was removed.
# ---------------------------------------------------------------------------
FALLBACK = {
    "LLM_SYSTEM": "llm.system",
    "LLM_REQUEST_MODEL": "llm.request.model",
    "LLM_RESPONSE_MODEL": "llm.response.model",
    "LLM_REQUEST_MAX_TOKENS": "llm.request.max_tokens",
    "LLM_REQUEST_TEMPERATURE": "llm.request.temperature",
    "LLM_REQUEST_TOP_P": "llm.request.top_p",
    "LLM_REQUEST_FREQUENCY_PENALTY": "llm.request.frequency_penalty",
    "LLM_REQUEST_PRESENCE_PENALTY": "llm.request.presence_penalty",
    "LLM_REQUEST_STOP_SEQUENCES": "llm.request.stop_sequences",
    "LLM_REQUEST_FUNCTIONS": "llm.request.functions",
    "LLM_REQUEST_FUNCTION_CALL": "llm.request.function_call",
    "LLM_REQUEST_REPETITION_PENALTY": "llm.request.repetition_penalty",
    "LLM_RESPONSE_FINISH_REASON": "llm.response.finish_reason",
    "LLM_RESPONSE_STOP_REASON": "llm.response.stop_reason",
    "LLM_USAGE_PROMPT_TOKENS": "llm.usage.prompt_tokens",
    "LLM_USAGE_COMPLETION_TOKENS": "llm.usage.completion_tokens",
    "LLM_USAGE_TOTAL_TOKENS": "llm.usage.total_tokens",
    "LLM_USAGE_TOKEN_TYPE": "llm.usage.token_type",
    "LLM_TOKEN_TYPE": "llm.token_type",
    "LLM_COMPLETIONS": "llm.completions",
    "LLM_PROMPTS": "llm.prompts",
    "LLM_CHAT_STOP_SEQUENCES": "llm.chat.stop_sequences",
    "LLM_FREQUENCY_PENALTY": "llm.frequency_penalty",
    "LLM_PRESENCE_PENALTY": "llm.presence_penalty",
    "LLM_TOP_K": "llm.top_k",
    "LLM_IS_STREAMING": "llm.is_streaming",
    "LLM_OPENAI_API_BASE": "llm.openai.api_base",
    "LLM_OPENAI_API_TYPE": "llm.openai.api_type",
    "LLM_OPENAI_API_VERSION": "llm.openai.api_version",
    "LLM_OPENAI_RESPONSE_SYSTEM_FINGERPRINT": "llm.openai.system_fingerprint",
    "LLM_CONTENT_COMPLETION_CHUNK": "llm.content.completion.chunk",
    "LLM_REQUEST_REASONING_EFFORT": "llm.request.reasoning_effort",
    "LLM_USAGE_REASONING_TOKENS": "llm.usage.reasoning_tokens",
}

# Merge: source-scan wins over fallback (more accurate for installed version)
for k, v in FALLBACK.items():
    KNOWN.setdefault(k, v)

# ---------------------------------------------------------------------------
# Step 4: Check we have mappings for everything that is needed
# ---------------------------------------------------------------------------
still_missing = needed - set(KNOWN.keys())
if still_missing:
    print("ERROR: No mapping found for: " + str(sorted(still_missing)), file=sys.stderr)
    print("Add them to the FALLBACK dict in patch_observability.py", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Step 5: Apply replacements to the target file
# ---------------------------------------------------------------------------
patched = []
for attr in needed:
    val = KNOWN[attr]
    new = content.replace("SpanAttributes." + attr, repr(val))
    if new != content:
        patched.append(attr)
    content = new

# Verify nothing remains
remaining = re.findall(r"SpanAttributes\.(LLM_\w+)", content)
if remaining:
    print("ERROR: Replacements failed for: " + str(remaining), file=sys.stderr)
    sys.exit(1)

with open(TARGET_PATH, "w") as f:
    f.write(content)

print("Successfully patched: " + str(patched))
