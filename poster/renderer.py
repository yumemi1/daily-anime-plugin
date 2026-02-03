"""
Playwright海报渲染器
负责将HTML模板渲染为图片
"""

import os
import json
import re
import asyncio
from typing import Dict, Any, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

try:
    from src.common.logger import get_logger
except ImportError:
    import logging

    def get_logger(name):
        return logging.getLogger(name)  # type: ignore


logger = get_logger("poster_renderer")


class PosterRenderer:
    """海报渲染器"""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.viewport = {"width": 1200, "height": 800}  # 初始高度较小，后续动态调整
        self.template_dir = os.path.dirname(os.path.abspath(__file__))
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self._init_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self._cleanup()

    async def _init_browser(self):
        """初始化浏览器"""
        try:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-web-security",
                    "--disable-features=VizDisplayCompositor",
                    "--disable-extensions",
                    "--disable-plugins",
                    "--disable-images-blocked",  # 确保图片不被阻止
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding",
                    "--disable-ipc-flooding-protection",
                    "--enable-features=NetworkService",
                    "--disable-features=TranslateUI",
                    "--blink-settings=imagesEnabled=true",  # 明确启用图片加载
                ],
            )

            self.context = await self.browser.new_context(
                viewport={"width": 1200, "height": 800},  # 设置基础视口，页面可以超出
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                # 配置字体支持emoji和中文字符
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                # 网络配置优化
                ignore_https_errors=True,  # 忽略HTTPS错误以加载更多图片
                extra_http_headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                },
            )

            logger.info("Playwright浏览器初始化成功")

        except Exception as e:
            logger.error(f"浏览器初始化失败: {e}")
            raise

    async def _cleanup(self):
        """清理资源"""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            logger.info("浏览器资源清理完成")
        except Exception as e:
            logger.error(f"资源清理失败: {e}")

    async def _load_template(self, template_name: str) -> str:
        """加载HTML模板并处理CSS"""
        template_path = os.path.join(self.template_dir, "templates", template_name)
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"模板文件不存在: {template_path}")

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template_content = f.read()

            # 内嵌CSS以避免路径问题
            template_content = self._embed_css(template_content)

            return template_content
        except Exception as e:
            logger.error(f"加载模板失败: {e}")
            raise

    def _embed_css(self, template_content: str) -> str:
        """将CSS文件内容内嵌到HTML中"""
        import re

        # 查找CSS链接
        css_pattern = r'<link\s+[^>]*rel=["\']stylesheet["\'][^>]*href=["\']([^"\']+)["\'][^>]*>'

        def replace_css_link(match):
            href = match.group(1)

            # 构建CSS文件完整路径
            css_path = os.path.join(self.template_dir, "templates", href)

            try:
                if os.path.exists(css_path):
                    with open(css_path, "r", encoding="utf-8") as f:
                        css_content = f.read()
                    return f'<style type="text/css">\n{css_content}\n</style>'
                else:
                    logger.warning(f"CSS文件不存在: {css_path}")
                    return match.group(0)  # 保持原始链接
            except Exception as e:
                logger.error(f"内嵌CSS失败: {e}")
                return match.group(0)  # 保持原始链接

        # 替换所有CSS链接
        return re.sub(css_pattern, replace_css_link, template_content, flags=re.IGNORECASE)

    def _render_template_content(self, template_content: str, data: Dict[str, Any]) -> str:
        """增强的模板渲染器，支持更复杂的数据绑定和条件判断"""
        content = template_content

        # 递归处理嵌套数据结构
        def resolve_value(key_path: str, data_context: Dict[str, Any]) -> Any:
            """解析嵌套键路径，如 'main_anime.title'"""
            keys = key_path.split(".")
            value = data_context

            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    return None
            return value

        # 处理简单变量替换 {{variable}}
        def replace_simple_variables(text: str, context: Dict[str, Any]) -> str:
            """替换简单变量"""
            pattern = r"{{(\w+(?:\.\w+)*)}}"

            def replacer(match):
                key_path = match.group(1)
                value = resolve_value(key_path, context)

                if value is None:
                    return ""
                elif isinstance(value, bool):
                    return "true" if value else "false"
                elif isinstance(value, (int, float)):
                    return str(value)
                elif isinstance(value, str):
                    # HTML转义
                    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
                else:
                    return str(value)

            return re.sub(pattern, replacer, text)

        # 处理条件块 {{#if condition}}...{{/if}}
        def process_conditionals(text: str, context: Dict[str, Any]) -> str:
            """处理条件块"""
            # if条件
            if_pattern = r"{{#if\s+(\w+(?:\.\w+)*)}}(.*?){{/if}}"

            def if_replacer(match):
                condition = match.group(1)
                body = match.group(2)
                value = resolve_value(condition, context)

                # 判断条件
                if value is not None and (
                    (isinstance(value, bool) and value)
                    or (isinstance(value, (str, list, dict)) and value)
                    or (isinstance(value, (int, float)) and value != 0)
                ):
                    # 递归处理条件体内的内容
                    return process_template(body, context)
                else:
                    return ""

            text = re.sub(if_pattern, if_replacer, text, flags=re.DOTALL)

            # unless条件
            unless_pattern = r"{{#unless\s+(\w+(?:\.\w+)*)}}(.*?){{/unless}}"

            def unless_replacer(match):
                condition = match.group(1)
                body = match.group(2)
                value = resolve_value(condition, context)

                # unless条件与if相反
                if value is None or (
                    (isinstance(value, bool) and not value)
                    or (isinstance(value, (str, list, dict)) and not value)
                    or (isinstance(value, (int, float)) and value == 0)
                ):
                    return process_template(body, context)
                else:
                    return ""

            text = re.sub(unless_pattern, unless_replacer, text, flags=re.DOTALL)

            return text

        # 处理循环块 {{#each array}}...{{/each}}
        def process_loops(text: str, context: Dict[str, Any]) -> str:
            """处理循环块"""
            each_pattern = r"{{#each\s+(\w+(?:\.\w+)*)}}(.*?){{/each}}"

            def each_replacer(match):
                array_path = match.group(1)
                body_template = match.group(2)
                array_value = resolve_value(array_path, context)

                if not isinstance(array_value, list) or not array_value:
                    return ""

                result_parts = []
                for index, item in enumerate(array_value):
                    # 为循环项创建局部上下文
                    item_context = context.copy()
                    item_context.update(
                        {"this": item, "index": index, "first": index == 0, "last": index == len(array_value) - 1}
                    )

                    # 如果item是字典，添加其所有属性到上下文
                    if isinstance(item, dict):
                        item_context.update(item)

                    # 处理循环体
                    processed_item = process_template(body_template, item_context)
                    result_parts.append(processed_item)

                return "".join(result_parts)

            return re.sub(each_pattern, each_replacer, text, flags=re.DOTALL)

        # 主处理函数
        def process_template(text: str, context: Dict[str, Any]) -> str:
            """递归处理模板"""
            # 先处理条件块（可能包含循环）
            text = process_conditionals(text, context)
            # 再处理循环块（可能包含条件）
            text = process_loops(text, context)
            # 最后处理简单变量
            text = replace_simple_variables(text, context)
            return text

        # 执行模板渲染
        try:
            content = process_template(content, data)

            # 清理未处理的模板标记
            content = re.sub(r"{{[^}]*}}", "", content)

            logger.debug(f"模板渲染完成，输入长度: {len(template_content)}, 输出长度: {len(content)}")

        except Exception as e:
            logger.error(f"模板渲染过程中发生错误: {str(e)}")
            # 发生错误时返回清理后的原始模板
            content = re.sub(r"{{[^}]*}}", "", template_content)

        return content

    async def render_poster(self, template_data: Dict[str, Any], template_name: str = "daily.html") -> bytes:
        """渲染海报图片

        Args:
            template_data: 模板数据
            template_name: 模板文件名

        Returns:
            图片的二进制数据
        """
        if not self.browser or not self.context:
            await self._init_browser()

        try:
            # 加载模板
            template_content = await self._load_template(template_name)

            # 渲染模板内容
            rendered_html = self._render_template_content(template_content, template_data)

            # 创建新页面
            page = await self.context.new_page()

            try:
                # 设置页面内容
                await page.set_content(rendered_html, wait_until="domcontentloaded")

                # 动态调整视口高度以适应内容
                await page.evaluate("""
                    () => {
                        // 等待所有图片加载完成后再计算高度
                        const images = Array.from(document.images);
                        images.forEach(img => {
                            if (!img.complete) {
                                img.loading = 'eager';
                            }
                        });
                        
                        // 强制重新计算布局
                        document.body.offsetHeight;
                    }
                """)

                # 增强图片加载等待
                await page.wait_for_load_state("domcontentloaded", timeout=30000)

                # 添加图片加载重试机制
                await page.evaluate("""
                    () => {
                        const images = Array.from(document.images);
                        images.forEach(img => {
                            if (!img.complete) {
                                img.loading = 'eager'; // 强制加载
                                // 重新触发加载
                                const src = img.src;
                                img.src = '';
                                img.src = src;
                            }
                        });
                    }
                """)

                # 等待所有图片加载完成，带重试
                max_image_retries = 2
                for retry in range(max_image_retries):
                    try:
                        await page.wait_for_function(
                            """() => {
                                const images = Array.from(document.images);
                                const loaded = images.filter(img => img.complete && img.naturalHeight > 0);
                                const failed = images.filter(img => img.naturalHeight === 0);
                                console.log(`图片状态: 已加载 ${loaded.length}/${images.length}, 失败 ${failed.length}`);
                                return loaded.length >= Math.ceil(images.length * 0.8) || // 80%加载成功
                                       images.length === 0; // 没有图片
                            }""",
                            timeout=10000,
                        )
                        logger.info(f"图片加载完成 (重试 {retry + 1})")
                        break
                    except Exception as e:
                        if retry < max_image_retries - 1:
                            logger.warning(f"图片加载重试 {retry + 1}/{max_image_retries}: {e}")
                            await page.wait_for_timeout(2000)  # 等待2秒再重试
                        else:
                            logger.warning(f"图片加载最终超时，继续渲染: {e}")

                # 检查并记录图片加载状态
                image_status = await page.evaluate("""
                    Array.from(document.images).map((img, index) => ({
                        index,
                        src: img.src,
                        loaded: img.complete,
                        error: img.naturalHeight === 0,
                        dimensions: `${img.naturalWidth}x${img.naturalHeight}`
                    }))
                """)

                logger.info(f"图片加载状态: {image_status}")

                # 等待页面完全渲染并计算最终高度
                await page.wait_for_timeout(2000)  # 额外等待确保渲染完成

                # 获取精确的内容高度
                dimensions = await page.evaluate("""
                    () => {
                        const poster = document.querySelector('.poster');
                        const body = document.body;
                        const html = document.documentElement;
                        
                        const posterHeight = poster ? poster.scrollHeight : 0;
                        const bodyHeight = body.scrollHeight;
                        const htmlHeight = html.scrollHeight;
                        
                        return {
                            poster: posterHeight,
                            body: bodyHeight,
                            html: htmlHeight,
                            max: Math.max(posterHeight, bodyHeight, htmlHeight)
                        };
                    }
                """)

                final_height = dimensions["max"] + 100  # 添加底部缓冲
                logger.info(f"内容尺寸计算: {dimensions}, 最终高度: {final_height}px")

                # 生成完整长图截图
                screenshot = await page.screenshot(
                    type="png",
                    full_page=True,  # 自动截取完整页面高度
                    animations="disabled",
                    quality=90,  # 设置图片质量
                    scale="device",  # 使用设备像素比
                )

                logger.info(f"海报渲染成功，大小: {len(screenshot)} bytes")
                return screenshot

            finally:
                await page.close()

        except Exception as e:
            logger.error(f"海报渲染失败: {e}")
            raise

    async def test_render(self) -> bytes:
        """测试渲染功能 - 包含大量内容测试长图生成"""
        test_data = {
            "date": "2026年1月12日",
            "has_animes": True,
            "main_anime": {
                "title": "黄金神威 最终章 第四季续作",
                "score": "8.7",
                "watchers": "2580人追番",
                "latest_episode": "第12话",
                "episode_progress": "12/24",
                "update_status": "连载中",
                "cover_url": "https://lain.bgm.tv/pic/cover/m/7c/f1/443106_b4QP3.jpg",
            },
            "other_animes": [
                {
                    "title": "石纪元 第三季 新世界篇",
                    "score": "8.1",
                    "latest_episode": "第8话",
                    "episode_progress": "8/12",
                    "cover_url": "https://lain.bgm.tv/pic/cover/m/7c/f1/443107_b4QP3.jpg",
                },
                {
                    "title": "链锯人 第二季 蕾塞篇",
                    "score": "8.5",
                    "latest_episode": "第6话",
                    "episode_progress": "6/12",
                    "cover_url": "https://lain.bgm.tv/pic/cover/m/7c/f1/443108_b4QP3.jpg",
                },
                {
                    "title": "咒术回战 第二季 涉谷事变",
                    "score": "8.9",
                    "latest_episode": "第15话",
                    "episode_progress": "15/23",
                    "cover_url": "https://lain.bgm.tv/pic/cover/m/7c/f1/443109_b4QP3.jpg",
                },
                {
                    "title": "间谍过家家 第二季",
                    "score": "8.3",
                    "latest_episode": "第10话",
                    "episode_progress": "10/12",
                    "cover_url": "https://lain.bgm.tv/pic/cover/m/7c/f1/443110_b4QP3.jpg",
                },
                {
                    "title": "葬送的芙莉莲",
                    "score": "9.1",
                    "latest_episode": "第20话",
                    "episode_progress": "20/28",
                    "cover_url": "https://lain.bgm.tv/pic/cover/m/7c/f1/443111_b4QP3.jpg",
                },
                {
                    "title": "药屋少女的呢喃",
                    "score": "8.0",
                    "latest_episode": "第18话",
                    "episode_progress": "18/24",
                    "cover_url": "https://lain.bgm.tv/pic/cover/m/7c/f1/443112_b4QP3.jpg",
                },
            ],
            "generated_time": "2026-01-12 16:30",
        }

        return await self.render_poster(test_data)


async def create_renderer(headless: bool = True) -> PosterRenderer:
    """创建渲染器实例"""
    return await PosterRenderer(headless).__aenter__()


# 测试函数
async def test_renderer():
    """测试渲染器功能"""
    try:
        async with PosterRenderer() as renderer:
            screenshot = await renderer.test_render()

            # 保存测试图片
            test_path = os.path.join(os.path.dirname(__file__), "..", "test_poster.png")
            with open(test_path, "wb") as f:
                f.write(screenshot)
            logger.info(f"测试海报已保存到: {test_path}")

    except Exception as e:
        logger.error(f"测试渲染器失败: {e}")


if __name__ == "__main__":
    asyncio.run(test_renderer())
