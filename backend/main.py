"""
AI Arena — FastAPI Backend v4.1
Fixes:
  - Keep-alive /api/ping endpoint (use with UptimeRobot to prevent Render sleep)
  - NVIDIA_API_KEY_2 gracefully falls back to primary key
  - Judge model ID updated to verified NIM endpoint
  - Better error messages surfaced to frontend
  - Startup key validation with clear console warnings
"""

import os, asyncio, json
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import httpx

load_dotenv()

app = FastAPI(title="AI Arena API", version="4.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ENV_FILE   = os.path.join(os.path.dirname(__file__), ".env")
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"

# ── Judge model (separate, never competes) ─────────────────────────────────────
# Verified NIM model ID as of 2025 — update if NVIDIA changes the slug
JUDGE_MODEL = {
    "name":        "Gemma 7B (Judge)",
    "model_id":    "google/gemma-7b",
    "temperature": 0.2,
    "top_p":       0.7,
}

# ── Competitor models ──────────────────────────────────────────────────────────
MODELS = {
    "gpt_oss": {
        "name":        "GPT-OSS 120B",
        "model_id":    "openai/gpt-oss-120b",
        "provider":    "nvidia",
        "color":       "#e8ff47",
        "persona":     "You are GPT-OSS, a highly capable and precise AI. Be structured, thorough, and evidence-based.",
        "temperature": 1.0,
        "top_p":       1.0,
    },
    "deepseek": {
        "name":        "DeepSeek R1 Distill",
        "model_id":    "deepseek-ai/deepseek-r1-distill-llama-8b",
        "provider":    "nvidia",
        "color":       "#47c5ff",
        "persona":     "You are DeepSeek, a reasoning-focused AI. Think step by step and explore problems deeply.",
        "temperature": 0.6,
        "top_p":       0.7,
    },
    "gemma": {
        "name":        "Phi-3 Mini 128K",
        "model_id":    "microsoft/phi-3-mini-128k-instruct",
        "provider":    "nvidia",
        "color":       "#ff9f47",
        "persona":     "You are Gemma, a creative and insightful AI. Explore novel angles and make answers engaging.",
        "temperature": 0.2,
        "top_p":       0.7,
    },
    "groq_llama": {
        "name":        "Llama 3.3 70B",
        "model_id":    "llama-3.3-70b-versatile",
        "provider":    "groq",
        "color":       "#c47fff",
        "persona":     "You are Llama, a deep-thinking AI. Explore nuance, consider multiple viewpoints, and give comprehensive insightful answers.",
        "temperature": 0.7,
        "top_p":       1.0,
    },
}

JUDGE_SYSTEM = """You are a STRICT and UNBIASED judge evaluating 4 anonymous AI responses.

CRITICAL RULES:
- You do NOT know which model wrote which response. Treat them all as anonymous.
- You MUST NOT give any response an unfair advantage. Judge purely on content quality.
- Scores MUST vary significantly across responses — do NOT give everyone similar scores.
- The best response should score 8-10, average ones 5-7, weak ones 2-5.
- You MUST find genuine differences. If you give 3+ responses the same score in any category, you are not judging carefully enough.
- Actively look for flaws: vagueness, inaccuracy, poor structure, lack of depth.

Criteria definitions:
- accuracy: Is it factually correct and directly relevant to the prompt?
- clarity: Is it well-structured, easy to follow, free of waffle?
- depth: Does it go beyond surface level with real insight?
- creativity: Does it offer unique angles, examples, or thinking?

Return ONLY valid JSON, no markdown, no extra text:
{
  "gpt_oss":   {"accuracy":8.5,"clarity":9.0,"depth":7.5,"creativity":6.0},
  "deepseek":  {"accuracy":7.0,"clarity":8.0,"depth":8.5,"creativity":9.0},
  "gemma":     {"accuracy":9.0,"clarity":9.5,"depth":6.0,"creativity":7.0},
  "groq_llama":{"accuracy":8.0,"clarity":7.5,"depth":9.5,"creativity":8.0}
}"""

SYNTH_SYSTEM = """You are a synthesis AI. Combine the strongest insights from multiple ranked AI responses into the single best possible answer.
Do NOT mention model names. Be clear, comprehensive, and direct. Just answer the prompt brilliantly."""

# ── Schemas ────────────────────────────────────────────────────────────────────
class PromptRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    prompt: str

class KeysUpdateRequest(BaseModel):
    admin_password:  str
    nvidia_api_key:  Optional[str] = None
    nvidia_api_key_2: Optional[str] = None
    groq_api_key:    Optional[str] = None

class ScoreDetail(BaseModel):
    model_config = {"protected_namespaces": ()}
    accuracy:   float
    clarity:    float
    depth:      float
    creativity: float
    total:      float

class RankedModel(BaseModel):
    model_config = {"protected_namespaces": ()}
    id:       str
    name:     str
    model_id: str
    provider: str
    color:    str
    response: str
    error:    Optional[str] = None
    scores:   ScoreDetail
    rank:     int

class ArenaResponse(BaseModel):
    models:    list[RankedModel]
    synthesis: str
    winner:    str

# ── API callers ────────────────────────────────────────────────────────────────
def _get_nvidia_key(secondary: bool = False) -> str:
    """Return the appropriate NVIDIA key. Falls back to primary if secondary not set."""
    if secondary:
        k = os.getenv("NVIDIA_API_KEY_2", "").strip()
        if k and not k.startswith("nvapi-xxx"):
            return k
    k = os.getenv("NVIDIA_API_KEY", "").strip()
    if not k or k.startswith("nvapi-xxx"):
        raise ValueError(
            "NVIDIA_API_KEY is not configured. "
            "Set it in Render → Environment or backend/.env"
        )
    return k

def _get_groq_key() -> str:
    k = os.getenv("GROQ_API_KEY", "").strip()
    if not k or k.startswith("gsk_xxx"):
        raise ValueError(
            "GROQ_API_KEY is not configured. "
            "Set it in Render → Environment or backend/.env"
        )
    return k

async def call_nvidia(mid: str, system: str, user_msg: str, max_tokens: int = 1024) -> str:
    key = _get_nvidia_key()
    m   = MODELS[mid]
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model":    m["model_id"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user_msg},
        ],
        "temperature": m.get("temperature", 0.7),
        "top_p":       m.get("top_p", 1.0),
        "max_tokens":  max_tokens,
        "stream":      False,
    }
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(NVIDIA_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise ValueError(data["error"].get("message", "NVIDIA error"))
        return data["choices"][0]["message"]["content"] or ""

async def call_groq(model_id: str, system: str, user_msg: str, max_tokens: int = 1024) -> str:
    key     = _get_groq_key()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model":      model_id,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user_msg},
        ],
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(GROQ_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise ValueError(data["error"].get("message", "Groq error"))
        return data["choices"][0]["message"]["content"] or ""

async def call_judge(system: str, user_msg: str, max_tokens: int = 600) -> str:
    """Dedicated Gemma 7B judge call — uses NVIDIA_API_KEY_2 if set, else primary."""
    key     = _get_nvidia_key(secondary=True)
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model":    JUDGE_MODEL["model_id"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user_msg},
        ],
        "temperature": JUDGE_MODEL["temperature"],
        "top_p":       JUDGE_MODEL["top_p"],
        "max_tokens":  max_tokens,
        "stream":      False,
    }
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(NVIDIA_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise ValueError(data["error"].get("message", "Judge error"))
        return data["choices"][0]["message"]["content"] or ""

async def call_model(mid: str, system: str, user_msg: str, max_tokens: int = 1024) -> str:
    m = MODELS[mid]
    if m["provider"] == "groq":
        return await call_groq(m["model_id"], system, user_msg, max_tokens)
    return await call_nvidia(mid, system, user_msg, max_tokens)

# ── Arena helpers ──────────────────────────────────────────────────────────────
async def get_response(mid: str, prompt: str) -> dict:
    try:
        text = await call_model(mid, MODELS[mid]["persona"], prompt)
        return {"id": mid, "response": text, "error": None}
    except Exception as e:
        print(f"[{mid}] error: {e}")
        return {"id": mid, "response": "", "error": str(e)}

def parse_scores(raw: str) -> dict:
    cleaned = raw.strip()
    start   = cleaned.find("{")
    end     = cleaned.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(cleaned[start:end])
    return {}

def average_scores(all_judge_scores: list) -> dict:
    combined, counts = {}, {}
    for judge_scores in all_judge_scores:
        for mid, scores in judge_scores.items():
            if mid not in combined:
                combined[mid] = {"accuracy": 0, "clarity": 0, "depth": 0, "creativity": 0}
                counts[mid]   = 0
            for crit in ["accuracy", "clarity", "depth", "creativity"]:
                combined[mid][crit] += scores.get(crit, 0)
            counts[mid] += 1
    for mid in combined:
        if counts[mid] > 0:
            for crit in combined[mid]:
                combined[mid][crit] = round(combined[mid][crit] / counts[mid], 1)
    return combined

async def judge_all(prompt: str, responses: dict) -> dict:
    working = [mid for mid in MODELS if responses.get(mid, {}).get("response")]
    if not working:
        return {mid: {"accuracy": 7.0, "clarity": 7.0, "depth": 7.0, "creativity": 7.0} for mid in MODELS}

    all_text = "\n\n".join(
        f"=== RESPONSE {i+1} (id:{mid}) ===\n{responses[mid]['response']}"
        for i, mid in enumerate(working)
    )
    user_msg = (
        f'Original prompt: "{prompt}"\n\n'
        f"Here are the {len(working)} responses to judge (labeled by id):\n\n{all_text}\n\n"
        f"Score each response id on all 4 criteria. Be harsh — find real differences. "
        f"The best should score 8-10, weak ones 3-6."
    )

    # Primary: dedicated Gemma 7B judge
    try:
        raw    = await call_judge(JUDGE_SYSTEM, user_msg)
        scores = parse_scores(raw)
        if scores:
            return scores
        print("Judge returned unparseable output, falling back to consensus")
    except Exception as e:
        print(f"Judge failed ({e}), falling back to model consensus")

    # Fallback: all models judge and average (cancels self-bias)
    judge_tasks  = [call_model(mid, JUDGE_SYSTEM, user_msg, max_tokens=600) for mid in working]
    raw_results  = await asyncio.gather(*judge_tasks, return_exceptions=True)
    all_scores   = []
    for raw in raw_results:
        if isinstance(raw, Exception):
            continue
        try:
            s = parse_scores(raw)
            if s:
                all_scores.append(s)
        except Exception:
            continue
    if all_scores:
        return average_scores(all_scores)
    return {mid: {"accuracy": 7.0, "clarity": 7.0, "depth": 7.0, "creativity": 7.0} for mid in MODELS}

async def synthesize(prompt: str, ranked: list, responses: dict) -> str:
    ordered = "\n\n---\n\n".join(
        f"[Rank #{i+1} | Score {m['score']:.1f}/10]\n{responses[m['id']]['response']}"
        for i, m in enumerate(ranked)
        if responses[m["id"]]["response"]
    )
    user_msg = f'Prompt: "{prompt}"\n\nRanked responses (best first):\n\n{ordered}\n\nSynthesize the definitive best answer.'
    for mid in ["groq_llama", "gpt_oss", "deepseek"]:
        if not responses.get(mid, {}).get("response"):
            continue
        try:
            return await call_model(mid, SYNTH_SYSTEM, user_msg, max_tokens=1500)
        except Exception:
            continue
    return responses[ranked[0]["id"]]["response"]

# ── Routes ─────────────────────────────────────────────────────────────────────

from fastapi import Request

@app.api_route("/api/ping", methods=["GET", "HEAD"])
async def ping(request: Request):
    return {"pong": True}

@app.get("/api/status")
async def status():
    nv_key  = os.getenv("NVIDIA_API_KEY",   "").strip()
    nv_key2 = os.getenv("NVIDIA_API_KEY_2", "").strip()
    gr_key  = os.getenv("GROQ_API_KEY",     "").strip()
    nvidia_ok       = bool(nv_key  and not nv_key.startswith("nvapi-xxx"))
    nvidia_judge_ok = bool(nv_key2 and not nv_key2.startswith("nvapi-xxx"))
    groq_ok         = bool(gr_key  and not gr_key.startswith("gsk_xxx"))

    missing = []
    if not nvidia_ok:       missing.append("NVIDIA_API_KEY")
    if not groq_ok:         missing.append("GROQ_API_KEY")

    return {
        "nvidia":        nvidia_ok,
        "nvidia_judge":  nvidia_judge_ok,
        "groq":          groq_ok,
        "ready":         nvidia_ok and groq_ok,
        "missing_keys":  missing,
        "judge_model":   JUDGE_MODEL["name"],
        "models":        {mid: MODELS[mid]["name"] for mid in MODELS},
    }

@app.post("/api/arena", response_model=ArenaResponse)
async def run_arena(req: PromptRequest):
    if not req.prompt.strip():
        raise HTTPException(400, "Prompt cannot be empty")

    # Quick key check before spending time on requests
    nv = os.getenv("NVIDIA_API_KEY", "").strip()
    gk = os.getenv("GROQ_API_KEY",   "").strip()
    if not nv or nv.startswith("nvapi-xxx"):
        raise HTTPException(
            503,
            "NVIDIA_API_KEY not configured. "
            "Go to Render Dashboard → Environment and add your nvapi-... key, then redeploy."
        )
    if not gk or gk.startswith("gsk_xxx"):
        raise HTTPException(
            503,
            "GROQ_API_KEY not configured. "
            "Go to Render Dashboard → Environment and add your gsk_... key, then redeploy."
        )

    results   = await asyncio.gather(*[get_response(mid, req.prompt) for mid in MODELS])
    responses = {r["id"]: r for r in results}

    working = [r for r in results if r["response"]]
    if len(working) < 2:
        errors = "; ".join(
            f"{MODELS[r['id']]['name']}: {r['error']}"
            for r in results if r["error"]
        )
        raise HTTPException(503, f"Not enough models responded. Errors: {errors}")

    raw_scores = await judge_all(req.prompt, responses)

    model_scores = []
    for mid in MODELS:
        s     = raw_scores.get(mid, {"accuracy": 0, "clarity": 0, "depth": 0, "creativity": 0})
        total = (s.get("accuracy", 0) + s.get("clarity", 0) + s.get("depth", 0) + s.get("creativity", 0)) / 4
        model_scores.append({"id": mid, "score": total, "raw": s})
    model_scores.sort(key=lambda x: x["score"], reverse=True)

    synthesis     = await synthesize(req.prompt, model_scores, responses)
    ranked_models = []
    for rank, ms in enumerate(model_scores):
        mid, s, m = ms["id"], ms["raw"], MODELS[ms["id"]]
        ranked_models.append(RankedModel(
            id=mid, name=m["name"], model_id=m["model_id"],
            provider=m["provider"], color=m["color"],
            response=responses[mid]["response"] or f"[Error: {responses[mid]['error']}]",
            error=responses[mid]["error"],
            scores=ScoreDetail(
                accuracy=round(s.get("accuracy", 0), 1),
                clarity=round(s.get("clarity",  0), 1),
                depth=round(s.get("depth",    0), 1),
                creativity=round(s.get("creativity", 0), 1),
                total=round(ms["score"], 1),
            ),
            rank=rank + 1,
        ))
    return ArenaResponse(models=ranked_models, synthesis=synthesis, winner=model_scores[0]["id"])

@app.post("/api/admin/keys")
async def update_keys(req: KeysUpdateRequest):
    if req.admin_password != os.getenv("ADMIN_PASSWORD", "changeme123"):
        raise HTTPException(401, "Invalid admin password")
    mapping = {
        "NVIDIA_API_KEY":   req.nvidia_api_key,
        "NVIDIA_API_KEY_2": req.nvidia_api_key_2,
        "GROQ_API_KEY":     req.groq_api_key,
    }
    lines    = open(ENV_FILE).readlines() if os.path.exists(ENV_FILE) else []
    updated, new_lines = set(), []
    for line in lines:
        matched = False
        for k, v in mapping.items():
            if line.strip().startswith(f"{k}=") and v is not None:
                new_lines.append(f"{k}={v}\n")
                os.environ[k] = v
                updated.add(k)
                matched = True
                break
        if not matched:
            new_lines.append(line)
    for k, v in mapping.items():
        if v is not None and k not in updated:
            new_lines.append(f"{k}={v}\n")
            os.environ[k] = v
    open(ENV_FILE, "w").writelines(new_lines)
    return {"success": True, "updated": [k for k, v in mapping.items() if v]}

# ── Serve frontend ─────────────────────────────────────────────────────────────
_fe = os.path.join(os.path.dirname(__file__), "..", "frontend", "public")
if os.path.exists(_fe):
    _st = os.path.join(_fe, "static")
    if os.path.exists(_st):
        app.mount("/static", StaticFiles(directory=_st), name="static")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        return FileResponse(os.path.join(_fe, "index.html"))

# ── Startup validation ─────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_check():
    nv = os.getenv("NVIDIA_API_KEY",   "").strip()
    gk = os.getenv("GROQ_API_KEY",     "").strip()
    n2 = os.getenv("NVIDIA_API_KEY_2", "").strip()
    ok = "\033[92m✓\033[0m"
    no = "\033[91m✗\033[0m"
    print("\n\033[1m⚔  AI Arena v4.1 — Key Status\033[0m")
    print(f"  {ok if nv and not nv.startswith('nvapi-xxx') else no}  NVIDIA_API_KEY   {'set' if nv else '← MISSING — add to Render Environment'}")
    print(f"  {ok if n2 and not n2.startswith('nvapi-xxx') else no}  NVIDIA_API_KEY_2 {'set (dedicated judge)' if n2 else '(optional — falls back to primary key)'}")
    print(f"  {ok if gk and not gk.startswith('gsk_xxx')  else no}  GROQ_API_KEY     {'set' if gk else '← MISSING — add to Render Environment'}")
    print()

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    print(f"\n\033[92m⚔  AI Arena → http://localhost:{port}\033[0m\n")
    is_dev = os.getenv("RENDER") is None
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=is_dev)