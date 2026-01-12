# 配置文件说明

本插件使用 `config.toml` 作为配置文件，但此文件**不包含在仓库中**。

## 配置文件获取方式

### 方法1：首次运行自动生成
插件首次运行时，会自动生成 `config.toml` 文件，包含所有默认配置项。

### 方法2：手动创建模板
创建 `config.toml` 文件并复制以下内容：

```toml
# daily_anime_plugin - 配置文件
# 基于 Bangumi API 的每日新番资讯插件

# 插件基本信息
[plugin]

# 配置文件版本
config_version = "1.0.0"

# 是否启用插件
enabled = true


# Bangumi API 配置
[api]

# Bangumi API 基础URL
base_url = "https://api.bgm.tv"

# API 请求超时时间(秒)
timeout = 30

# API 请求间隔延迟(秒)
rate_limit_delay = 1.0


# 缓存配置
[cache]

# 默认缓存过期时间(秒)
default_ttl = 1800

# 最大缓存项数
max_size = 500

# 每日放送日程缓存时间(秒)
calendar_ttl = 1800

# 搜索结果缓存时间(秒)
search_ttl = 3600

# 番剧详情缓存时间(秒)
detail_ttl = 3600


# 推送配置
[push]

# 是否启用每日推送
daily_push_enabled = false

# 每日推送时间
push_time = "09:00"

# 推送目标聊天ID列表
push_chat_ids = []
```

## 配置项说明

### [plugin] 插件配置
- `enabled`: 是否启用插件 (true/false)
- `config_version`: 配置文件版本，请勿修改

### [api] API配置  
- `base_url`: Bangumi API地址，通常不需要修改
- `timeout`: API请求超时时间，单位秒
- `rate_limit_delay`: 请求间隔延迟，避免频繁请求

### [cache] 缓存配置
- `default_ttl`: 默认缓存过期时间，单位秒 (默认1800秒=30分钟)
- `max_size`: 最大缓存项数量 (默认500)
- `calendar_ttl`: 每日放送日程缓存时间
- `search_ttl`: 搜索结果缓存时间  
- `detail_ttl`: 番剧详情缓存时间

### [push] 推送配置
- `daily_push_enabled`: 是否启用每日定时推送
- `push_time`: 推送时间，格式：HH:MM (如 "09:00")
- `push_chat_ids`: 推送目标的聊天ID列表

## 配置文件位置

将 `config.toml` 文件放置在插件根目录，与 `plugin.py` 同级即可。

配置文件会在插件启动时自动加载，修改后重启插件生效。