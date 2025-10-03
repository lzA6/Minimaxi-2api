# app/core/config.py (v4.0 - 黄金标准最终版)

from pydantic_settings import BaseSettings
from typing import List, Optional

class Settings(BaseSettings):
    APP_NAME: str = "Minimaxi Local API"
    APP_VERSION: str = "4.0.0"
    DESCRIPTION: str = "一个支持粘性会话和动态签名的高性能 Minimaxi 网页版聊天本地代理。"
    API_MASTER_KEY: Optional[str] = None

    # --- 核心修正点：只将环境变量作为简单字符串读取 ---
    MINIMAXI_TOKENS: str = ""
    
    # --- 核心修正点：模型列表是硬编码的，不从环境读取 ---
    SUPPORTED_MODELS: List[str] = ["minimaxi-pro"]

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()

# 在模块加载后进行最终验证
if not settings.MINIMAXI_TOKENS:
    raise ValueError("CRITICAL ERROR: MINIMAXI_TOKENS is not set or empty. Please provide at least one token in your Hugging Face Space secrets.")