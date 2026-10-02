"""LLM 客户端 — DashScope OpenAI 兼容模式（qwen）"""
import logging

from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.AI_API_KEY,
            base_url=settings.AI_BASE_URL,
            timeout=settings.AI_TIMEOUT,
        )
    return _client


async def chat_completion(messages: list[dict],
                           temperature: float | None = None) -> str:
    """调用 LLM，返回纯文本。异常由调用方降级处理。"""
    resp = await get_client().chat.completions.create(
        model=settings.AI_MODEL,
        messages=messages,
        max_tokens=settings.AI_MAX_TOKENS,
        temperature=temperature if temperature is not None else settings.AI_TEMPERATURE,
        top_p=settings.AI_TOP_P,
    )
    return (resp.choices[0].message.content or "").strip()


async def chat_completion_stream(messages: list[dict],
                                  temperature: float | None = None):
    """流式调用 LLM，逐段 yield 文本增量。异常由调用方降级处理。"""
    resp = await get_client().chat.completions.create(
        model=settings.AI_MODEL,
        messages=messages,
        max_tokens=settings.AI_MAX_TOKENS,
        temperature=temperature if temperature is not None else settings.AI_TEMPERATURE,
        top_p=settings.AI_TOP_P,
        stream=True,
    )
    async for chunk in resp:
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
