# Daily Anime Plugin for MaiBot

基于 Bangumi API 的每日新番资讯插件，为 MaiBot 用户提供实时的新番更新信息和精美的可视化海报。

> ✨ **特色功能**：现代化海报设计、智能过滤系统、多层缓存优化、LLM工具集成

## 📋 目录索引

- [🚀 功能特性](#-功能特性)
- [🚀 快速开始](#-快速开始)
- [📖 使用方式](#-使用方式)
- [⚙️ 配置选项](#️-配置选项)
- [🎨 海报功能详解](#-海报功能详解)
- [🛠️ 技术栈](#️-技术栈)
- [📁 项目结构](#-项目结构)
- [🔧 故障排除](#-故障排除)
- [📋 版本信息](#-版本信息)
- [🤝 贡献指南](#-贡献指南)

## 🚀 功能特性

### 核心功能
- **📅 每日新番更新** - 实时获取当天放送日程，支持周报汇总
- **🎨 精美海报生成** - 自动生成现代化新番资讯海报（纯文本设计，无emoji）
- **🔍 智能番剧搜索** - 支持关键词、标签、评分等多维度搜索
- **📊 详细番剧信息** - 提供评分、简介、追番人数等完整数据
- **💬 自然语言交互** - 支持智能对话式查询和LLM工具集成

### 高级功能
- **🎯 智能过滤系统** - 支持关键词、工作室黑名单，自动过滤不感兴趣内容
- **⚡ 高性能缓存** - 多层缓存机制，剧集信息独立缓存，API调用优化
- **⏰ 定时推送** - 自定义时间推送新番更新和海报生成
- **🌐 多平台适配** - 支持各种聊天平台的消息格式适配

## 🚀 快速开始

### 📦 安装依赖

**基础依赖（必需）：**

```bash
pip install aiohttp pydantic
```

**海报功能依赖（可选，推荐安装）：**

```bash
pip install playwright
playwright install chromium
```

> 💡 **提示**：海报功能依赖 Playwright，如果不需要海报生成功能可跳过

### 🔧 插件安装

1. **克隆或下载插件**到 MaiBot 的 `plugins/` 目录
2. **重启 MaiBot**，插件首次运行时会自动生成 `config.toml` 配置文件
3. **在配置中启用插件**：

```toml
[plugin]
enabled = true
```

4. **（可选）配置海报功能**：

```toml
[poster]
enabled = true
headless_browser = true
```

### 🎯 快速验证

安装完成后，发送以下命令测试：

```
/anime_today    # 查看今日新番
/anime_poster   # 生成今日海报
```

## 📖 使用方式

### 🎮 命令式交互

| 命令 | 功能描述 | 示例 |
|------|----------|------|
| `/anime_today` | 查询今日新番更新 | `/anime_today` |
| `/anime_week` | 查询本周新番汇总 | `/anime_week` |
| `/anime_search <关键词>` | 搜索特定番剧 | `/anime_search 鬼灭之刃` |
| `/anime_poster` | 获取今日新番海报 | `/anime_poster` |
| `/weekly_poster` | 获取本周汇总海报 | `/weekly_poster` |

### 💬 智能对话示例

```
"今天有什么新番更新吗？"
"本周有什么好看的动漫？"
"帮我搜索一下鬼灭之刃"
"生成一张新番海报"
"查一下咒术回战的评分"
```

### 🤖 LLM工具集成

插件提供完整的 LLM 工具接口，支持：

```python
# 可用的工具函数
generate_anime_poster(poster_type="daily", force_refresh=False)
get_daily_anime()
search_anime(keyword="关键词")
get_anime_detail(subject_id=12345)
manage_blacklist(action="add/remove/list", target="关键词/工作室名")
```

### 📱 支持的聊天平台

- ✅ Telegram
- ✅ QQ
- ✅ 微信
- ✅ Discord
- ✅ 其他支持 MaiBot 的平台

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
- **episodes_ttl** (integer, 可选): 剧集信息缓存时间，单位为秒，默认 7200 秒（2小时）

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

### [filter] 番剧过滤配置

- **enabled** (boolean, 必需): 是否启用番剧过滤功能，true 为启用，false 为禁用，默认 true

#### [filter.chinese_anime_filter] 国漫过滤

- **enabled** (boolean, 必需): 是否过滤国漫，true 为过滤，false 为不过滤，默认 true

#### [filter.keyword_blacklist] 关键词黑名单

- **enabled** (boolean, 必需): 是否启用关键词过滤，true 为启用，false 为禁用，默认 true
- **keywords** (array, 可选): 需要过滤的关键词列表，默认 ["试看集", "PV", "预告", "OP", "ED", "CM", "番外", "OVA", "OAD"]

#### [filter.studio_blacklist] 制作公司黑名单

- **enabled** (boolean, 必需): 是否启用制作公司黑名单，true 为启用，false 为禁用，默认 false
- **studios** (array, 可选): 黑名单制作公司列表，默认为空数组 []

#### [filter.custom_blacklist] 自定义标题黑名单

- **enabled** (boolean, 必需): 是否启用自定义标题黑名单，true 为启用，false 为禁用，默认 false
- **titles** (array, 可选): 黑名单番剧标题列表，默认为空数组 []

**注意事项：**

- 配置文件修改后需要重启 MaiBot 才能生效
- 推送功能的 chat_id 需要根据具体的聊天平台获取正确值
- 海报功能需要额外安装 Playwright 依赖
- 缓存时间设置过长可能导致数据不及时，设置过短可能增加API调用频率
- 新增剧集信息缓存，默认2小时，减少API调用频率并提高响应速度

## 海报功能详解

### 自动生成时间

- **04:00** - 每日新番海报自动生成
- **04:10** - 本周汇总海报（仅周一）
- **03:50** - 自动清理过期海报缓存

### 🎨 海报特点

- **🎭 现代设计** - 紫蓝渐变背景，玻璃态卡片效果
- **📝 纯文本设计** - 无emoji依赖，确保跨平台兼容性
- **📊 剧集信息** - 显示评分、追番人数和更新状态
- **🌐 网格布局** - 响应式设计，所有番剧展示封面图
- **🖼️ 高分辨率** - 800px宽度，适配各种显示设备
- **🏆 智能排序** - 按评分高低展示番剧，主番剧突出显示
- **⚡ 预生成机制** - 定时生成，秒级响应
- **💾 多层缓存** - 内存+磁盘双重缓存，剧集信息独立缓存
- **🛡️ 优雅降级** - 海报不可用时自动发送文本版本，图片加载失败显示占位符

### 🕐 自动生成时间表

| 时间 | 功能 | 说明 |
|------|------|------|
| `03:50` | 清理过期海报 | 自动清理超过7天的海报文件 |
| `04:00` | 每日海报生成 | 自动生成当日新番海报 |
| `04:10` | 本周汇总海报 | 仅周一自动生成本周汇总海报 |
| `09:00` | 定时推送 | 推送今日新番更新（可配置） |

## 🛠️ 技术栈

### 核心技术
- **🐍 核心语言**: Python 3.8+ with asyncio
- **🌐 网络请求**: aiohttp for HTTP requests
- **✅ 数据验证**: pydantic for data validation
- **🎨 海报渲染**: Playwright + Chromium (可选依赖)
- **🎭 样式设计**: 现代CSS3特性 (backdrop-filter, grid, animations)

### 架构设计
- **💾 缓存策略**: 内存缓存 + 文件系统，多层缓存优化
- **🔌 API集成**: Bangumi API (https://api.bgm.tv)
- **📱 框架支持**: MaiBot Plugin System v0.8.0+
- **🤖 AI集成**: LLM工具接口，支持智能对话

### 性能优化
- **⚡ 异步处理**: 全异步架构，高并发支持
- **🗂️ 智能缓存**: 分层缓存策略，减少API调用
- **📊 数据压缩**: 优化的数据结构，减少内存占用
- **🔄 错误恢复**: 完善的异常处理和重试机制

## 项目结构

```
plugins/daily-anime-plugin/
├── __init__.py             # 插件包初始化文件
├── plugin.py               # 主插件文件，包含所有组件和功能逻辑
├── _manifest.json          # 插件清单文件
├── README.md               # 插件说明文档
├── LICENSE                 # MIT许可证文件
├── .gitignore             # Git忽略规则
├── utils/                  # 工具模块目录
│   ├── __init__.py        # 工具模块初始化
│   ├── bangumi_api.py     # Bangumi API客户端和数据格式化
│   ├── cache_manager.py   # 多层缓存管理器（内存+文件）
│   ├── scheduler.py       # 定时任务调度器
│   └── blacklist_manager.py # 番剧黑名单管理器
├── poster/                 # 海报生成模块目录
│   ├── __init__.py        # 海报模块初始化
│   ├── renderer.py        # Playwright渲染器（HTML→图片）
│   ├── generator.py       # 海报生成器（数据+模板渲染）
│   ├── cache.py          # 海报文件缓存管理
│   └── templates/        # HTML模板目录
│       ├── daily.html     # 每日新番海报模板
│       ├── weekly.html    # 本周汇总海报模板
│       └── minimal-styles.css  # 现代化CSS样式
├── posters/               # 海报存储目录
│   ├── daily/            # 每日海报文件存储
│   ├── weekly/           # 周报海报文件存储
│   └── cache.json        # 海报缓存索引文件
└── _locales/              # 国际化资源目录
    └── zh-CN.json        # 中文本地化文件
```

## 🔧 故障排除

### 🎨 海报功能不可用

**问题排查步骤：**

```bash
# 1. 检查Playwright是否安装
pip show playwright

# 2. 安装Playwright和浏览器（如果未安装）
pip install playwright
playwright install chromium

# 3. 检查浏览器安装状态
playwright install --help
```

**常见问题：**
- ❌ 浏览器下载失败 → 检查网络连接，使用代理
- ❌ 权限不足 → 以管理员身份运行安装命令
- ❌ 磁盘空间不足 → 清理磁盘空间

### 🚫 插件启动失败

**基础检查：**
```bash
# 1. 检查基础依赖
pip install aiohttp pydantic

# 2. 检查Python版本（需要3.8+）
python --version

# 3. 检查MaiBot版本（需要0.8.0+）
# 查看 MaiBot 的版本信息
```

**日志调试：**
- 查看 MaiBot 的日志输出
- 检查插件目录的读写权限
- 确认插件文件完整性

### ⚙️ 配置问题

**配置文件相关：**
- 📁 插件首次运行会自动生成 `config.toml`
- 🔄 如需重置配置，删除 `config.toml` 并重启插件
- 📍 确保配置文件与 `plugin.py` 同级目录

**常见配置错误：**
- ❌ `chat_ids` 格式错误 → 应为 `[123456789, 987654321]`
- ❌ 时间格式错误 → 应为 `"HH:MM"` 格式，如 `"09:00"`
- ❌ API地址错误 → 默认为 `"https://api.bgm.tv"`，通常不需要修改

### 📡 API相关问题

**Bangumi API限制：**
- ⏰ 请求频率限制：建议间隔1秒以上
- 🌐 网络问题：检查与 bgm.tv 的连接
- 🔑 无需API密钥：使用公开API端点

**缓存问题：**
- 🗂️ 缓存文件损坏 → 删除 `posters/cache.json`
- 💾 内存不足 → 调整缓存配置大小
- 📊 数据过期 → 等待缓存自动刷新或强制刷新

## 📋 版本信息

### 🏷️ 基本信息
- **🔢 版本**: 1.0.0
- **📄 许可证**: MIT
- **🐍 Python要求**: 3.8+
- **🤖 MaiBot最低版本**: 0.8.0
- **🌐 API**: Bangumi v0 (https://api.bgm.tv)

### 📊 项目统计
- **📁 项目结构**: 10+ 模块文件
- **🎨 海报模板**: 2套精美模板（每日/周报）
- **⚡ 缓存策略**: 多层缓存，支持5种TTL配置
- **🔧 配置选项**: 30+ 可配置参数

### 🎯 最近更新
- ✨ **重构海报设计** - 移除过度装饰元素，采用纯文本设计
- 🚀 **性能优化** - 改进缓存机制，减少不必要的渲染
- 🛠️ **代码重构** - 简化视觉效果，提升静态截图性能
- 📱 **兼容性改进** - 确保跨平台显示一致性

---

## 🤝 贡献指南

### 📝 如何贡献
1. **Fork** 本仓库
2. **创建** 特性分支 (`git checkout -b feature/AmazingFeature`)
3. **提交** 更改 (`git commit -m 'Add some AmazingFeature'`)
4. **推送** 到分支 (`git push origin feature/AmazingFeature`)
5. **开启** Pull Request

### 🐛 问题反馈
- 📋 使用 [Issues](https://github.com/yumemi1/daily-anime-plugin/issues) 报告Bug
- 💡 提出 [Feature Request](https://github.com/yumemi1/daily-anime-plugin/issues/new?assignees=&labels=&template=feature_request.md)
- 📖 查看 [Wiki](https://github.com/yumemi1/daily-anime-plugin/wiki) 获取更多文档

---

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

---

<div align="center">

### ⭐ 如果这个插件对你有帮助，请给个Star支持一下！

**作者**: [yumemi1](https://github.com/yumemi1)  
**项目主页**: [GitHub Repository](https://github.com/yumemi1/daily-anime-plugin)

</div>
