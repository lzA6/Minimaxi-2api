# app/providers/minimaxi_provider.py (v8.0 - Playwright 终极方案)

import asyncio
import json
import traceback
from typing import Dict, Any, AsyncGenerator

from fastapi import Request
from fastapi.responses import StreamingResponse, JSONResponse
from loguru import logger
from starlette.responses import Response
from playwright.async_api import async_playwright, Browser, Page, Playwright

from app.providers.base import BaseProvider
from app.core.config import settings

class MinimaxiProvider(BaseProvider):
    BASE_URL = "https://chat.minimaxi.com/"
    MODEL_MAP = {"minimaxi-pro": "mm-m1"}

    _playwright: Playwright = None
    _browser: Browser = None
    _lock = asyncio.Lock()

    def __init__(self):
        # 在初始化时，我们只做最基本的事。浏览器将在第一次请求时启动。
        logger.info("Minimaxi Playwright Provider is initializing...")
        # 启动一个后台任务来确保浏览器在程序退出时关闭
        asyncio.create_task(self.cleanup_on_shutdown())

    async def get_browser(self) -> Browser:
        """单例模式启动并返回一个浏览器实例"""
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                logger.info("No active browser found. Launching a new Playwright browser...")
                self._playwright = await async_playwright().start()
                # 在 Docker/Linux 环境中，必须使用 --no-sandbox
                self._browser = await self._playwright.chromium.launch(headless=True, args=["--no-sandbox"])
                logger.success("Playwright browser launched successfully.")
            return self._browser

    async def cleanup_on_shutdown(self):
        """注册一个清理函数，在程序关闭时调用"""
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(2, self._sync_cleanup) # SIGINT
        loop.add_signal_handler(15, self._sync_cleanup) # SIGTERM

    def _sync_cleanup(self):
        """同步的清理包装器"""
        logger.warning("Shutdown signal received. Cleaning up Playwright resources...")
        asyncio.create_task(self.cleanup())

    async def cleanup(self):
        """关闭浏览器和 Playwright 实例"""
        async with self._lock:
            if self._browser and self._browser.is_connected():
                await self._browser.close()
                logger.info("Playwright browser closed.")
            if self._playwright:
                await self._playwright.stop()
                logger.info("Playwright instance stopped.")
            self._browser = None
            self._playwright = None

    async def chat_completion(self, request_data: Dict[str, Any], original_request: Request) -> Response:
        try:
            # Playwright 必须是流式响应
            return StreamingResponse(
                self._stream_generator(request_data),
                media_type="text/event-stream"
            )
        except Exception as e:
            logger.error(f"Fatal error in Playwright chat completion: {e}")
            traceback.print_exc()
            return JSONResponse(content={"error": {"message": f"An error occurred: {e}", "type": "playwright_error"}}, status_code=500)

    async def _stream_generator(self, request_data: Dict[str, Any]) -> AsyncGenerator[str, None]:
        page: Page = None
        browser = await self.get_browser()
        context = None
        
        try:
            # 1. 创建一个干净的浏览器上下文
            context = await browser.new_context()
            page = await context.new_page()

            # 2. 注入 Token (关键步骤)
            await page.goto(self.BASE_URL, wait_until="domcontentloaded")
            token_data = {
                "token": settings.MINIMAXI_TOKENS,
                "expire": int(time.time() * 1000) + 3600 * 24 * 30 * 1000 # 伪造一个超长的过期时间
            }
            # 使用 JS 将 token 注入到 Local Storage
            await page.evaluate(f"window.localStorage.setItem('_token', '{json.dumps(token_data)}')")
            logger.info("Token injected into Local Storage.")

            # 3. 重新加载页面以使登录生效
            await page.goto(self.BASE_URL, wait_until="networkidle")
            logger.info("Page reloaded with authentication.")

            # 4. 等待输入框出现并输入问题
            input_selector = "textarea[placeholder*='输入']"
            await page.wait_for_selector(input_selector, timeout=30000)
            user_message = request_data.get("messages", [{}])[-1].get("content", "你好")
            await page.fill(input_selector, user_message)
            logger.info(f"Filled input with: '{user_message}'")

            # 5. 点击发送按钮
            send_button_selector = "button[class*='send-button']"
            await page.click(send_button_selector)
            logger.info("Send button clicked.")

            # 6. 实时监控回复区域的 DOM 变化 (最复杂的部分)
            # 等待回复的第一个块出现
            reply_container_selector = "div[class*='msg-content-container']"
            await page.wait_for_selector(reply_container_selector, timeout=60000)
            
            # 获取最后一个回复容器（即 AI 的回复）
            last_reply_handle = await page.query_selector_all(reply_container_selector)
            last_reply = last_reply_handle[-1]

            last_content = ""
            is_first_chunk = True
            
            # 轮询检查内容变化
            timeout = 120  # 2分钟超时
            start_time = time.time()
            while time.time() - start_time < timeout:
                # 查找表示“已完成”的元素，例如重新出现的发送按钮
                is_finished = await page.is_visible(send_button_selector)

                current_content = await last_reply.inner_text()
                
                if current_content != last_content:
                    if is_first_chunk:
                        yield f"data: {json.dumps({'id': 'chat-1', 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': 'minimaxi-pro', 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
                        is_first_chunk = False

                    delta = current_content[len(last_content):]
                    last_content = current_content
                    
                    chunk = {'id': 'chat-1', 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': 'minimaxi-pro', 'choices': [{'index': 0, 'delta': {'content': delta}, 'finish_reason': None}]}
                    yield f"data: {json.dumps(chunk)}\n\n"

                if is_finished and current_content == last_content:
                    logger.info("Detected end of stream (send button visible and content stable).")
                    break
                
                await asyncio.sleep(0.1) # 轮询间隔

        except Exception as e:
            logger.error(f"Error during Playwright stream: {e}")
            traceback.print_exc()
            error_chunk = {'id': 'chat-1', 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': 'minimaxi-pro', 'choices': [{'index': 0, 'delta': {'content': f"\n\n[Playwright Error: {e}]"}, 'finish_reason': 'error'}]}
            yield f"data: {json.dumps(error_chunk)}\n\n"
        
        finally:
            # 发送结束信号
            yield f"data: {json.dumps({'id': 'chat-1', 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': 'minimaxi-pro', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
            yield "data: [DONE]\n\n"
            logger.success("Playwright stream finished.")
            if context:
                await context.close() # 关闭上下文和页面，释放资源

