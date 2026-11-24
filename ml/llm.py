"""Chat with LLMs about the experiments (the ML UI's "AI 分析" page): Gemini (generateContent) and Claude (Messages API), one adapter each,
settings in ml/local/llm.json.

Everything here is plain Python without Streamlit, so it can be tested with a fake HTTP opener. A conversation lives in the UI's session, one per
provider (history = [{"role": "user" | "model", "text": ...}]); the APIs are stateless, so every call sends that provider's whole history.
Privacy: a key comes from an environment variable or from ml/local/llm.json (git ignores ml/local), it goes in a request header (never the URL)
and is scrubbed from any error text; what is sent are the compact digests of modelmeta (no paths, no personal data)."""
import datetime
import json
import os
import re
import time
import urllib.error
import urllib.request

import modelmeta

SETTINGS_FILE = os.path.join(modelmeta.LOCAL_DIR, "llm.json")
DEFAULT_CONVERSATION_LIMIT = 120000  # characters of one provider's whole conversation (what every call sends)
CLAUDE_MAX_TOKENS = 8192
CLAUDE_VERSION = "2023-06-01"  # the anthropic-version header

# The providers (one adapter each): label, the environment variable that holds the key, and the defaults of its settings.
# A provider that costs money (Claude) starts disabled; enabling it is a checkbox on its settings tab.
PROVIDERS = {
    "gemini": {"label": "Gemini", "env": "GEMINI_API_KEY", "endpoint": "https://generativelanguage.googleapis.com/v1beta",
               "model": "gemini-2.5-flash", "enabled": True},
    "claude": {"label": "Claude", "env": "ANTHROPIC_API_KEY", "endpoint": "https://api.anthropic.com",
               "model": "claude-sonnet-5-5", "enabled": False},
}
DEFAULT_MODEL = PROVIDERS["gemini"]["model"]  # kept for callers that only know Gemini

SYSTEM_INSTRUCTION = (
    "你是機器學習實驗的分析助理。使用者提供的數字都已經算好，不要重新計算，也不要編造不存在的數字；"
    "差距沒有超過誤差範圍（±95% 區間）就明說「不顯著」；資料不足時說明缺了什麼。回答要具體、可執行，用繁體中文，先講結論再列依據。")

DEFAULT_PRIMER = (
    "專案：波多黎各（3、4 人基礎版）桌遊的策略模擬器。用大量模擬找強策略；除了手寫策略，還有 MCTS 搭配學習型局面價值函數"
    "（LightGBM／MLP 估值模型）。訓練資料由 Runner 在模擬對局裡取樣局面（dump）；模型用這些資料訓練，再放進 MCTS 對戰驗證。\n"
    "判斷原則：好壞只看對戰勝率（對原版 MCTS、對手寫策略、同桌對打）；驗證 R²／交叉熵只是檢查訓練有沒有壞，資料分布一換就不能比。"
    "勝率差要看 95% 信賴區間（±），區間含 0 就不是顯著差異；座位順序用 balanced／random，單一排列不能下結論。"
    "規則版本（base-vN）或策略版本變了，舊資料與模型就是舊版。\n"
    "目前已知：多打資料、更好的自我對戰資料、新特徵、加大模型都沒有明顯進步；瓶頸可能是靜態估值很難預測後期結果，需要往前看（rollout／搜尋）。")

DEFAULT_QUESTIONS = [
    {"name": "比較模型", "text": "比較這幾個模型：訓練資料、參數與對戰勝率有什麼差異？哪些差距是顯著的？"},
    {"name": "找問題", "text": "這個模型（或資料）有什麼問題？哪個回合段的誤差最大，可能的原因是什麼？"},
    {"name": "下一步", "text": "根據這些結果，下一步最值得做的實驗是什麼？為什麼？"},
]


class LlmError(Exception):
    """A failed call; the text never contains the API key."""


def provider_defaults(name):
    p = PROVIDERS[name]
    return {"enabled": p["enabled"], "endpoint": p["endpoint"], "apiKey": "", "model": p["model"], "conversationLimit": DEFAULT_CONVERSATION_LIMIT}


def default_settings():
    return {"primer": DEFAULT_PRIMER, "questions": [dict(q) for q in DEFAULT_QUESTIONS], "providers": {n: provider_defaults(n) for n in PROVIDERS}}


def load_settings(path=None):
    """The saved settings over the defaults (a missing or broken file = defaults). A file from before there were several providers
    (endpoint / apiKey / model / conversationLimit at the top) becomes the Gemini entry."""
    settings = default_settings()
    try:
        with open(path or SETTINGS_FILE, encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, json.JSONDecodeError):
        return settings
    if not isinstance(saved, dict):
        return settings
    settings["providers"]["gemini"].update({k: saved[k] for k in ("endpoint", "apiKey", "model", "conversationLimit") if k in saved})
    for k in ("primer", "questions"):
        if k in saved:
            settings[k] = saved[k]
    for name, p in (saved.get("providers") or {}).items():
        if name in settings["providers"] and isinstance(p, dict):
            settings["providers"][name].update({k: v for k, v in p.items() if k in settings["providers"][name]})
    return settings


def provider_settings(settings, name):
    """One provider's settings with its name, kind (= which adapter) and label, the shape chat / list_models / api_key take."""
    return {**settings["providers"][name], "name": name, "kind": name, "label": PROVIDERS[name]["label"]}


def save_settings(settings, path=None):
    """Writes the settings to ml/local/llm.json (an "apiKey" already in the file stays; the page never writes one), readable by this user only
    where the system allows it."""
    path = path or SETTINGS_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    try:
        os.chmod(tmp, 0o600)
    except OSError:  # Windows
        pass
    os.replace(tmp, path)


def api_key(ps, env=None):
    """(key, source) of a provider: its environment variable first (GEMINI_API_KEY, ANTHROPIC_API_KEY), then "apiKey" in ml/local/llm.json
    (edited by hand; the page never asks for or shows a key). source is "env", "file" or "" (no key)."""
    env = os.environ if env is None else env
    var = PROVIDERS[ps.get("kind", "gemini")]["env"]
    if (env.get(var) or "").strip():
        return env[var].strip(), "env"
    if (ps.get("apiKey") or "").strip():
        return ps["apiKey"].strip(), "file"
    return "", ""


def redact(text, key):
    """text without the key (and without anything that looks like one in a URL query)."""
    text = str(text)
    if key:
        text = text.replace(key, "[key]")
    return re.sub(r"([?&]key=)[^&\s\"']+", r"\1[key]", text)


def _headers(ps, key):
    if ps.get("kind", "gemini") == "claude":
        return {"Content-Type": "application/json", "x-api-key": key, "anthropic-version": CLAUDE_VERSION}
    return {"Content-Type": "application/json", "x-goog-api-key": key}


def _request(ps, url, body=None, timeout=120, opener=urllib.request.urlopen):
    key, _ = api_key(ps)
    if not key:
        raise LlmError(f"沒有讀到 {ps.get('label', 'API')} 的金鑰：設定環境變數 {PROVIDERS[ps.get('kind', 'gemini')]['env']}，或在 ml/local/llm.json 加上 apiKey")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET", headers=_headers(ps, key))
    try:
        with opener(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except (OSError, ValueError, AttributeError):
            detail = ""
        raise LlmError(redact(f"HTTP {e.code}: {detail or e.reason}", key)) from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise LlmError(redact(f"連線失敗：{getattr(e, 'reason', e)}", key)) from None


def model_url(ps):
    base = ps["endpoint"].rstrip("/")
    if ps.get("kind", "gemini") == "claude":
        return f"{base}/v1/messages"
    return f"{base}/models/{ps['model'].removeprefix('models/')}:generateContent"


def build_body(ps, system, history):
    """The request body of the provider's API: the system instruction and the whole conversation so far."""
    if ps.get("kind", "gemini") == "claude":
        return {"model": ps["model"], "max_tokens": CLAUDE_MAX_TOKENS, "system": system,
                "messages": [{"role": "user" if m["role"] == "user" else "assistant", "content": m["text"]} for m in history]}
    return {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": m["role"], "parts": [{"text": m["text"]}]} for m in history]}


def chat(ps, system, history, timeout=180, opener=urllib.request.urlopen):
    """Sends the history (the last entry is the new user message) and returns {"text", "seconds", "tokens"}."""
    start = time.time()
    reply = _request(ps, model_url(ps), build_body(ps, system, history), timeout, opener)
    if ps.get("kind", "gemini") == "claude":
        text = "".join(b.get("text", "") for b in reply.get("content") or [] if b.get("type") == "text")
        reason = reply.get("stop_reason") or "no text"
        usage = reply.get("usage") or {}
        tokens = (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0) or None
    else:
        candidates = reply.get("candidates") or []
        parts = (candidates[0].get("content") or {}).get("parts") if candidates else None
        text = "".join(p.get("text", "") for p in parts or [])
        reason = (candidates[0].get("finishReason") if candidates else None) or (reply.get("promptFeedback") or {}).get("blockReason") or "no text"
        tokens = (reply.get("usageMetadata") or {}).get("totalTokenCount")
    if not text:
        raise LlmError(f"沒有回答（{reason}）")
    return {"text": text, "seconds": round(time.time() - start, 1), "tokens": tokens}


def list_models(ps, timeout=30, opener=urllib.request.urlopen):
    """Names of the models the provider offers for text (Gemini: without the 'models/' prefix)."""
    base = ps["endpoint"].rstrip("/")
    if ps.get("kind", "gemini") == "claude":
        reply = _request(ps, f"{base}/v1/models?limit=100", None, timeout, opener)
        return sorted(m["id"] for m in reply.get("data", []) if m.get("id"))
    reply = _request(ps, f"{base}/models?pageSize=200", None, timeout, opener)
    return sorted(m["name"].removeprefix("models/") for m in reply.get("models", []) if "generateContent" in (m.get("supportedGenerationMethods") or []))


def first_message(primer, digests, question):
    """The first user message: background, then the data, then the question (follow-ups send the question only; the history carries the rest)."""
    parts = []
    if primer.strip():
        parts.append("# 前情提要\n" + primer.strip())
    if digests.strip():
        parts.append("# 資料\n" + digests.strip())
    parts.append("# 問題\n" + question.strip())
    return "\n\n".join(parts)


def history_chars(history):
    return sum(len(m["text"]) for m in history)


def export_markdown(items, conversations, when=None):
    """The summary to download: when, what was analysed, and every provider's conversation (not the data itself).
    conversations = [{"label": "Gemini", "history": [...]}, ...]; each answer says which model gave it."""
    when = when or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# AI 分析總結（{when}）", "", f"- 分析的內容：{'、'.join(items) if items else '—'}",
             f"- 供應商：{'、'.join(c['label'] for c in conversations) or '—'}", ""]
    for c in conversations:
        lines += [f"## {c['label']}", ""]
        for m in c["history"]:
            who = "問" if m["role"] == "user" else f"答（{m.get('model') or c['label']}）"
            text = display_question(m["text"]) if m["role"] == "user" else m["text"]  # the first message carries the background and the data too
            lines += [f"### {who}", "", text.strip(), ""]
    return "\n".join(lines)


def display_question(text):
    """What the user typed in a message: the first message carries the background and the data too, so only its question part is shown."""
    return text.split("# 問題\n", 1)[-1].strip() if text.startswith("# 前情提要") or text.startswith("# 資料") else text
