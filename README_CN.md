# Puff — 创意总监 AI 智能体

> 一个有灵魂的独立 AI 智能体。会写作、会读你的稿子、会记住你的偏好。
> 自带 Web UI、文件系统访问权限、7 个函数调用工具。

[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://python.org)
[![stdlib](https://img.shields.io/badge/依赖-0-brightgreen)]()
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)
[![Ecosystem](https://img.shields.io/badge/泡芙AI-生态-7C3AED)](https://github.com/Zhu070124)

> 泡芙 AI 生态的创意人格层。另见：[Memory Hub](https://github.com/Zhu070124/memory-hub)（共享记忆）· [Workshop](https://github.com/Zhu070124/paofu-creative-workshop)（群聊）

---

## 这是什么？

大多数 AI 聊天界面千篇一律——同一个模型、同一种语气、没有跨会话记忆。
Puff 不一样：

- **人格，不是提示词模板。** Puff 启动时加载 `SOUL.md`——一份完整的人物设定，包含背景故事、价值观和行为规则
- **持久化记忆。** 跨会话记住你的写作偏好、项目上下文和个人特质（通过 Memory Hub 集成）
- **文件系统访问。** 原生读取 `.txt`、`.md`、`.py`、`.docx`、`.doc` 文件。`.docx` 解析仅用 Python 标准库（`zipfile` + `xml`）——零依赖
- **函数调用。** 7 个内置工具：列目录、读文件、写文件、搜记忆、存记忆、分享洞察到 Memory Hub、从 Memory Hub 拉取画像
- **双模式。** CLI 终端对话 + HTTP 服务器浏览器 Web UI

---

## 架构

```
puff.py
├── CLI 模式:  python puff.py → 终端对话
├── HTTP 模式: python puff.py serve → Web UI 端口 :8920
│
├── 系统提示词（启动时组装）
│   ├── SOUL.md              # 核心人格
│   ├── 私有记忆              # agents/creative-director/memory.md
│   └── Memory Hub 画像       # 跨智能体共享洞察
│
├── 7 个函数调用工具
│   ├── list_directory(path)       # 浏览文件
│   ├── read_file(path)            # 读取 .txt .md .docx .doc
│   ├── write_file(path, content)  # 写文件
│   ├── search_memory(query)       # 搜索私有记忆
│   ├── save_memory(fact)          # 保存到私有记忆
│   ├── share_insight(content)     # 推送到 Memory Hub
│   └── pull_profile(lens)         # 从 Memory Hub 拉取
│
└── Web UI (index.html)
    ├── 暖纸质感主题
    ├── Inter + EB Garamond 字体
    ├── 日夜模式切换
    └── 会话持久化 (session.json)
```

---

## 快速开始

### 前置条件

- Python 3.10+
- DeepSeek API key

### 1. 设置 API key

```bash
export DEEPSEEK_API_KEY="sk-your-key-here"
```

### 2. 启动

```bash
# HTTP 模式（带 Web UI）
python puff.py serve
# 浏览器打开 http://127.0.0.1:8920

# CLI 模式
python puff.py
python puff.py "帮我看看这篇散文"
```

### 3. 可选：接入 Memory Hub

```bash
# 先启动 Memory Hub（见 memory-hub 仓库）
python hub.py serve

# Puff 启动时自动检测并集成
```

---

## 自定义人格

替换 `agents/creative-director/SOUL.md` 为你自己的角色定义。格式是自由文本 Markdown——写任何定义你 Agent 声音的东西：

```markdown
# 你的 Agent 名字
- 背景故事: ...
- 价值观: ...
- 说话风格: ...
- 边界: ...
```

无需改代码。

---

## .docx 支持——零依赖

Word 文档本质是 ZIP 文件。Puff 用标准库解析：

```python
import zipfile
from xml.etree import ElementTree

with zipfile.ZipFile("document.docx") as z:
    xml = z.read("word/document.xml")
# 解析 XML → 提取段落文本
```

不需要 `python-docx`，不需要 pip install。任何 Python 3.x 环境都能跑。

---

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | *必填* | 你的 API key |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API 端点 |
| `PUFF_MODEL` | `deepseek-v4-flash` | 模型名称 |
| `MEMORY_HUB_URL` | `http://127.0.0.1:8921` | Memory Hub 地址 |

---

## 性能与优化

### 当前瓶颈

主要瓶颈是**单线程 HTTP 服务器**（`http.server.ThreadingHTTPServer`）。每次 DeepSeek API 请求会阻塞服务线程 2-10 秒。并发访问时请求串行排队。

### 优化路径

1. **异步 HTTP 服务器（推荐第一步）：** 用 `aiohttp` 或 `FastAPI` + `uvicorn` 替换 `http.server`，把 I/O 等待变成非阻塞协程
2. **流式响应：** 把 DeepSeek API 调用从 `stream=False` 改为 `stream=True`，前端逐字渲染
3. **连接池：** 对频繁的 Memory Hub 调用使用 `urllib3` 连接池或 `aiohttp.ClientSession`

### 速率限制

Puff 内置速率限制器（**15 次/60 秒**），滑动窗口实现，防止 API 滥用和账单意外飙升。

### 安全

所有文件操作**沙箱化**在 `clawd/`（WORK_ROOT）内。路径穿越攻击被显式拦截。可写目录是可读目录的严格子集，敏感路径（`.git`、`.env`、`secrets`、credentials）完全禁止访问。

---

## 常见问题

| 症状 | 可能原因 | 解决 |
|---|---|---|
| `OSError: [Errno 10048]` 启动报错 | 端口 8920 被占用 | 杀掉占用进程或换端口 |
| `DEEPSEEK_API_KEY not set` | 环境变量未设置 | 启动前 `export DEEPSEEK_API_KEY="sk-..."` |
| API 超时或 HTTP 429 | 速率限制或网络问题 | 等 60 秒窗口重置 |
| Memory Hub `Connection refused` | Memory Hub 没启动 | 先启动 Memory Hub，或不接也行 |
| `File access denied` | 路径在 `WORK_ROOT` 外或在禁止列表 | 把文件移到 `clawd/` 工作区 |
| `SOUL.md not found` | 缺少人格文件 | 确保 `agents/creative-director/SOUL.md` 存在 |

---

## 未来规划

- **短期：** 用 `aiohttp` 或 `FastAPI + uvicorn` 替换单线程 HTTP 服务
- **中期：** 添加流式响应（`stream=True`），打字机效果逐字渲染
- **长期：** 设计插件系统，用户自定义 Skill 自动注册为工具

---

## 许可

MIT © 2026 朱郅（泡芙）
