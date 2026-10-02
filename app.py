"""Campus Mind 数字人 — 云端精简版（单容器：静态页 + 对话 SSE + TTS viseme）

与本地 aiserver 的差异：
- 去掉 Java 回调/记忆/知识库/orchestrator，仅保留数字人所需链路
- 静态资源由本服务直接托管，前端同源调用，无 CORS 问题
- 所有配置走环境变量，密钥不入镜像

端口：默认 7860（HF Spaces 约定），其他平台用 PORT 环境变量覆盖
"""
import asyncio
import base64
import json
import logging
import re

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

import llm
from config import settings
from prompts import (
    COMPANION_SYSTEM_PROMPT, EMOTION_VOCAB, RISK_KEYWORDS, CRISIS_TEXT,
    FALLBACK_REPLY, ChatRequest,
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Campus Mind Digital Human (Cloud)")


# ══════════ 流式对话 ══════════

_EMO_RE = re.compile(r"\[([^\[\]]{1,4})\]")
_SENT_SPLIT = re.compile(r"[。！？!?；;\n]")


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


class SentenceStream:
    """LLM 增量 → 剥离情绪标签 → 整句切分，逐句产出事件。"""

    def __init__(self):
        self.buf = ""
        self.seq = 0
        self.full: list[str] = []
        self.emotion = "温柔"

    def _emit(self, sentence: str) -> list[dict]:
        s = sentence.strip()
        if not s:
            return []
        self.seq += 1
        self.full.append(s)
        return [{"type": "sentence", "seq": self.seq, "text": s}]

    def feed(self, delta: str) -> list[dict]:
        events: list[dict] = []
        self.buf += delta
        while True:
            m = _EMO_RE.search(self.buf)
            if not m:
                break
            tag = m.group(1)
            if tag in EMOTION_VOCAB:
                self.emotion = tag
                events.append({"type": "emotion", "emotion": tag})
            self.buf = self.buf[:m.start()] + self.buf[m.end():]
        while True:
            m = _SENT_SPLIT.search(self.buf)
            if not m:
                break
            s = self.buf[:m.end()]
            self.buf = self.buf[m.end():]
            events += self._emit(s)
        if len(self.buf) > 80:  # 超长无标点时在逗号处切
            idx = max(self.buf.rfind("，"), self.buf.rfind(","))
            if idx > 20:
                s, self.buf = self.buf[:idx + 1], self.buf[idx + 1:]
                events += self._emit(s)
        return events

    def flush(self) -> list[dict]:
        rest, self.buf = self.buf, ""
        return self._emit(rest)

    def text(self) -> str:
        return "".join(self.full)


@app.post("/ai/chat/stream")
async def chat_stream(req: ChatRequest):
    async def gen():
        # 危机兜底门（与主站同一套关键词，命中绕过 LLM）
        if any(k in req.message for k in RISK_KEYWORDS):
            yield _sse({"type": "meta", "mode": "crisis", "sources": []})
            yield _sse({"type": "emotion", "emotion": "难过"})
            parts = [p for p in re.split(r"(?<=[。！？!?；;\n])", CRISIS_TEXT) if p.strip()]
            for i, s in enumerate(parts, 1):
                yield _sse({"type": "sentence", "seq": i, "text": s})
            yield _sse({"type": "done", "mode": "crisis", "sources": [],
                        "risk_level": "ESCALATED"})
            return

        yield _sse({"type": "meta", "mode": "empathy", "sources": []})

        messages = [{"role": "system", "content": COMPANION_SYSTEM_PROMPT}]
        for turn in (req.history or [])[-20:]:
            role = "assistant" if turn.role == "ai" else "user"
            messages.append({"role": role, "content": turn.content})
        messages.append({"role": "user", "content": req.message})

        ss = SentenceStream()
        try:
            async for delta in llm.chat_completion_stream(messages):
                for ev in ss.feed(delta):
                    yield _sse(ev)
            for ev in ss.flush():
                yield _sse(ev)
            if not ss.text().strip():
                raise ValueError("empty reply")
        except Exception as e:
            logger.warning("LLM stream failed: %s", e)
            yield _sse({"type": "sentence", "seq": ss.seq + 1,
                        "text": FALLBACK_REPLY})

        yield _sse({"type": "done", "mode": "empathy", "sources": [],
                    "risk_level": "NORMAL"})

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ══════════ TTS（edge-tts + viseme 词级时间轴） ══════════

_TTS_WS = re.compile(r"\s+")
_TTS_DUP_PUNCT = re.compile(r"([。！？!?；;，、]){2,}")

_VOWEL_SHAPE = {
    "a": {"form": 0.15, "open": 1.0},
    "e": {"form": 0.55, "open": 0.6},
    "i": {"form": 0.9,  "open": 0.35},
    "o": {"form": -0.55, "open": 0.75},
    "u": {"form": -0.9,  "open": 0.45},
    "v": {"form": -0.8,  "open": 0.5},
}
_SHAPE_REST = {"form": 0.3, "open": 0.12}


def _tts_normalize(text: str) -> str:
    t = _TTS_WS.sub(" ", text or "").strip()
    return _TTS_DUP_PUNCT.sub(lambda m: m.group(1), t)


def _word_visemes(word: str) -> list[dict]:
    out = []
    for ch in word:
        if not ch.strip() or not ("\u4e00" <= ch <= "\u9fff"):
            continue
        from pypinyin import lazy_pinyin, Style
        py = lazy_pinyin(ch, style=Style.FINALS, strict=False)
        final = (py[0] if py and py[0] and py[0] != ch else "").lower()
        if "ai" in final or "ao" in final:
            v = "a"
        elif "ei" in final:
            v = "e"
        elif "ou" in final:
            v = "o"
        else:
            core = final.rstrip("ng")
            v = next((c for c in reversed(core) if c in _VOWEL_SHAPE), "e")
        shape = _VOWEL_SHAPE.get(v, _SHAPE_REST)
        out.append({"form": shape["form"], "open": shape["open"]})
    return out or [{"form": _SHAPE_REST["form"], "open": _SHAPE_REST["open"]}]


async def _viseme_response(text: str, voice: str) -> dict:
    import edge_tts
    com = edge_tts.Communicate(text, voice, rate=settings.TTS_RATE,
                               boundary="WordBoundary")
    buf = bytearray()
    words: list[dict] = []
    async for chunk in com.stream():
        if chunk["type"] == "audio":
            buf.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            visemes = _word_visemes(chunk.get("text", ""))
            t0 = chunk["offset"] / 1e7
            dt = (chunk["duration"] / 1e7) / max(1, len(visemes))
            for i, vis in enumerate(visemes):
                words.append({"t": t0 + i * dt, "d": dt,
                              "form": vis["form"], "open": vis["open"]})
    if not buf:
        raise ValueError("no audio")
    return {"audio": base64.b64encode(bytes(buf)).decode(),
            "words": words, "voice": voice}


@app.get("/ai/tts")
async def tts(text: str, voice: str | None = None, meta: int = 0):
    text = _tts_normalize(text)[:500]
    if not text:
        raise HTTPException(400, "text required")
    try:
        if meta:
            data = await _viseme_response(text, voice or settings.TTS_VOICE)
            return Response(json.dumps(data, ensure_ascii=False),
                            media_type="application/json")
        import edge_tts
        com = edge_tts.Communicate(text, voice or settings.TTS_VOICE,
                                   rate=settings.TTS_RATE)
        buf = bytearray()
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                buf.extend(chunk["data"])
        if not buf:
            raise ValueError("no audio")
        return Response(bytes(buf), media_type="audio/mpeg")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("TTS failed: %s", e)
        raise HTTPException(503, "TTS unavailable")


@app.get("/health")
def health():
    return {"status": "ok", "service": "campus-mind-cloud",
            "model": settings.AI_MODEL}


# ── 静态资源挂载必须放在所有 API 路由之后，否则 "/" 会抢走路由 ──
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import os
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))
