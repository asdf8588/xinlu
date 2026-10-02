"""云端精简版配置 — 全部走环境变量（密钥不入代码库）"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM（智谱 BigModel，OpenAI 兼容）
    AI_API_KEY: str = ""            # 部署平台的环境变量/Secret 里设置
    AI_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    AI_MODEL: str = "glm-4-flash"
    AI_MAX_TOKENS: int = 1024
    AI_TEMPERATURE: float = 0.7
    AI_TOP_P: float = 0.9
    AI_TIMEOUT: int = 60

    # TTS
    TTS_VOICE: str = "zh-CN-XiaoyiNeural"
    TTS_RATE: str = "+8%"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
