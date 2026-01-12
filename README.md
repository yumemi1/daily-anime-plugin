# Daily Anime Plugin for MaiBot

基于 Bangumi API 的每日新番资讯插件，为 MaiBot 用户提供实时的新番更新信息和精美海报。

## 功能特性

- **每日新番更新提醒** - 实时获取当天放送日程
- **精美海报生成** - 自动生成新番资讯海报（支持 Playwright）
- **智能番剧搜索** - 支持关键词、标签、评分等多维度搜索  
- **详细番剧信息** - 提供评分、简介、集数等完整数据
- **自然语言交互** - 支持智能对话式查询
- **高性能缓存** - 多层缓存机制，快速响应
- **定时推送** - 自定义时间推送新番更新和海报

## 快速开始

### 安装依赖

**基础依赖：**
```bash
pip install aiohttp pydantic
```

**海报功能依赖（可选）：**
```bash
pip install playwright
playwright install chromium
```

### 插件安装

1. 将插件放置到 MaiBot 的 `plugins/` 目录
2. 插件首次运行时会自动生成 `config.toml` 配置文件
3. 在配置中启用插件：
```toml
[plugin]
enabled = true
```

## 📱 使用方式

### 命令式交互
- `/anime_today` - 查询今日新番
- `/anime_week` - 查询本周新番汇总  
- `/anime_search <关键词>` - 搜索特定番剧
- `/anime_poster` - 获取今日新番海报
- `/weekly_poster` - 获取本周汇总海报

### 智能对话
- "今天有什么新番更新吗？"
- "本周有什么好看的动漫？"
- "帮我搜索一下鬼灭之刃"
- "生成一张新番海报"

### LLM工具集成
```python
# 可用的工具函数
generate_anime_poster(poster_type="daily", force_refresh=False)
get_daily_anime()
search_anime(keyword="关键词")
get_anime_detail(subject_id=12345)
```

## 配置选项

插件首次运行时会在插件目录自动生成 `config.toml` 配置文件。以下是各配置项的详细说明：

### [plugin] 插件基础配置

- **config_version** (string, 必需): 配置文件版本号，请勿手动修改，默认为 "1.0.0"
- **enabled** (boolean, 必需): 是否启用插件，true 为启用，false 为禁用

### [api] Bangumi API 配置

- **base_url** (string, 可选): Bangumi API 基础地址，默认为 "https://api.bgm.tv"，通常不需要修改
- **timeout** (integer, 可选): API 请求超时时间，单位为秒，默认 30 秒
- **rate_limit_delay** (float, 可选): API 请求间隔延迟，单位为秒，避免频繁请求被封禁，默认 1.0 秒

### [cache] 缓存策略配置

- **default_ttl** (integer, 可选): 默认缓存过期时间，单位为秒，默认 1800 秒（30分钟）
- **max_size** (integer, 可选): 内存缓存最大项目数量，默认 500 项
- **calendar_ttl** (integer, 可选): 每日放送日程数据的缓存时间，单位为秒，默认 1800 秒
- **search_ttl** (integer, 可选): 搜索结果缓存时间，单位为秒，默认 3600 秒（1小时）
- **detail_ttl** (integer, 可选): 番剧详细信息缓存时间，单位为秒，默认 3600 秒（1小时）

### [push] 定时推送配置

- **daily_push_enabled** (boolean, 必需): 是否启用每日定时推送功能，false 为不推送，true 为启用
- **push_time** (string, 可选): 每日推送时间，格式为 "HH:MM"，如 "09:00" 表示上午9点，默认 "09:00"
- **push_chat_ids** (array, 必需): 推送目标聊天ID列表，格式为 [chat_id1, chat_id2, ...]，空数组表示不推送

### [poster] 海报功能配置

- **enabled** (boolean, 必需): 是否启用海报生成功能，true 为启用，false 为禁用
- **daily_generation_time** (string, 可选): 每日海报自动生成时间，格式 "HH:MM"，默认 "04:00"
- **weekly_generation_time** (string, 可选): 周报海报自动生成时间，格式 "HH:MM"，默认 "04:10"
- **cleanup_time** (string, 可选): 过期海报清理时间，格式 "HH:MM"，默认 "03:50"
- **max_cache_days** (integer, 可选): 海报文件最大缓存天数，超过此天数的海报将被清理，默认 7 天
- **headless_browser** (boolean, 可选): 是否使用无头浏览器模式，true 为后台运行，false 为显示浏览器窗口，默认 true
- **cache_dir** (string, 可选): 海报缓存目录名称，相对于插件目录，默认 "posters"

**注意事项：**
- 配置文件修改后需要重启 MaiBot 才能生效
- 推送功能的 chat_id 需要根据具体的聊天平台获取正确值
- 海报功能需要额外安装 Playwright 依赖
- 缓存时间设置过长可能导致数据不及时，设置过短可能增加API调用频率

## 海报功能详解

### 自动生成时间
- **04:00** - 每日新番海报自动生成
- **04:10** - 本周汇总海报（仅周一）
- **03:50** - 自动清理过期海报缓存

### 海报特点
- **简约设计** - 深色主题，专业质感
- **移动端优化** - 720x960px，适合分享
- **智能排序** - 按评分高低展示番剧
- **预生成机制** - 定时生成，秒级响应
- **多层缓存** - 内存+磁盘双重缓存
- **优雅降级** - 海报不可用时自动发送文本版本

## 技术栈

- **核心**: Python 3.8+ with asyncio
- **网络**: aiohttp for HTTP requests
- **数据**: pydantic for data validation
- **渲染**: Playwright + Chromium (海报功能)
- **缓存**: 内存缓存 + 文件系统
- **API**: Bangumi API (https://api.bgm.tv)

## 项目结构

```
plugins/daily-anime-plugin/
├── plugin.py              # 主插件文件
├── _manifest.json         # 插件清单
├── config.toml.example    # 配置模板
├── utils/                 # 工具模块
│   ├── bangumi_api.py     # Bangumi API客户端
│   ├── cache_manager.py   # 缓存管理器
│   └── scheduler.py       # 定时任务调度
├── poster/                # 海报生成模块
│   ├── renderer.py        # Playwright渲染器
│   ├── generator.py       # 海报生成器
│   ├── cache.py          # 海报缓存管理
│   └── templates/        # HTML模板
│       ├── daily.html     # 每日海报模板
│       ├── weekly.html    # 周报海报模板
│       └── minimal-styles.css  # 通用样式
└── posters/              # 海报存储目录
    ├── daily/            # 每日海报
    └── weekly/           # 周报海报
```

## 故障排除

### 海报功能不可用
```bash
# 检查Playwright是否安装
pip show playwright

# 安装Playwright和浏览器
pip install playwright
playwright install chromium
```

### 插件启动失败
```bash
# 检查依赖
pip install aiohttp pydantic

# 查看日志
# 检查插件目录权限
```

### 配置问题
- 插件首次运行会自动生成配置文件
- 如需重置，删除 `config.toml` 并重启插件
- 确保配置文件与 `plugin.py` 同级目录

## 版本信息

- **版本**: 1.0.0
- **许可证**: MIT
- **Python要求**: 3.8+
- **MaiBot最低版本**: 0.8.0
- **API**: Bangumi v0

---

Made with ❤️ by [yumemi1](https://github.com/yumemi1)

**海报功能说明**: 海报生成功能需要额外安装 Playwright 依赖，请参考安装说明。