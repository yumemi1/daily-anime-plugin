# 🌸 Daily Anime Plugin for MaiBot

基于 Bangumi API 的每日新番资讯插件，为 MaiBot 用户提供实时的新番更新信息。

## ✨ 功能特性

- 📅 **每日新番更新提醒** - 实时获取当天放送日程
- 🔍 **智能番剧搜索** - 支持关键词、标签、评分等多维度搜索  
- 📊 **详细番剧信息** - 提供评分、简介、集数等完整数据
- 🤖 **自然语言交互** - 支持智能对话式查询
- ⚡ **高性能缓存** - 本地缓存机制，快速响应
- 🕐 **定时推送** - 自定义时间推送新番更新

## 🚀 快速开始

### 安装依赖
```bash
pip install aiohttp pydantic
```

### 插件安装
1. 将插件克隆到 MaiBot 的 `plugins/` 目录：
```bash
git clone https://github.com/yumemi1/daily-anime-plugin.git plugins/daily_anime_plugin
```

2. 在插件配置中启用：
```toml
[plugin]
enabled = true
```

## 📱 使用方式

### 命令式交互
- `/anime_today` - 查询今日新番
- `/anime_week` - 查询本周新番汇总  
- `/anime_search <关键词>` - 搜索特定番剧

### 智能对话
- "今天有什么新番更新吗？"
- "本周有什么好看的动漫？"
- "帮我搜索一下鬼灭之刃"

## ⚙️ 配置选项

详见 `config.toml` 文件中的完整配置说明。

### 基本配置
```toml
[plugin]
enabled = true
config_version = "1.0.0"

[api]
base_url = "https://api.bgm.tv"
timeout = 30
rate_limit_delay = 1.0

[cache]
default_ttl = 1800
max_size = 500

[push]
daily_push_enabled = false
push_time = "09:00"
push_chat_ids = []
```

## 🛠️ 技术栈

- Python 3.8+ with asyncio
- aiohttp for HTTP requests
- pydantic for data validation
- Bangumi API (https://api.bgm.tv)

## 📋 API 使用规范

本插件遵循 Bangumi API 的使用规范，使用符合要求的 User-Agent：

```
yumemi1/MaiBot-DailyAnimePlugin/1.0.0 (https://github.com/yumemi1/daily-anime-plugin)
```

## 📄 许可证

GPL-3.0 License - 详见 [LICENSE](LICENSE) 文件

## 🤝 贡献

Issues 和 Pull Request 都是欢迎的！

### 贡献指南
1. Fork 本项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📊 项目状态

![Version](https://img.shields.io/badge/Version-1.0.0-orange)
![License](https://img.shields.io/badge/License-GPL--3.0-green)
![Python](https://img.shields.io/badge/Python-3.8+-blue)
![Bangumi API](https://img.shields.io/badge/API-Bangumi%20v0-red)

---

Made with ❤️ by [yumemi1](https://github.com/yumemi1)