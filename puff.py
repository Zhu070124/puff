# Security patch applied - see security.py
"""
Puff — independent creative AI agent
=====================================
Creative director of 泡芙 AI Company. Butter yuan personality.
Reads her SOUL.md + memory at startup, talks to 泡芙 via terminal.

Usage:
  python puff.py                — start conversation
  python puff.py "你好"         — single turn
  /remember <fact>              — save to memory
  /search <query>               — search memories
  /read <path>                  — read a file
  /write <path>                 — write a file
  /ls [path]                    — list directory
  /skill <name>                 — inject a skill
  /bye                          — exit

Design references:
  - Hermes: simple CLI loop, direct API calls
  - Claude Code: skill loading system
  - OpenHanako: butter yuan personality model
"""

import os
import sys
import json
import urllib.request
from urllib.parse import urlparse
import urllib.error
import subprocess
import logging
from pathlib import Path
from datetime import datetime

# ── Security module ─────────────────────────────────────────────────────────
from security import safe_path, can_write, api_limiter, hot_load_soul, PERM_CONFIG

# ── Paths ──────────────────────────────────────────────────────────────────
PUFF_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
CLAWD_DIR = PUFF_DIR.parent
AGENT_DIR = CLAWD_DIR / "agents" / "creative-director"
SOUL_PATH = AGENT_DIR / "SOUL.md"
MEMORY_PATH = AGENT_DIR / "memory.md"
SKILLS_DIR = PUFF_DIR / "skills"
COGNITIVE_ENGINE = CLAWD_DIR / "memory" / "cognitive_engine.py"
# 使用 sys.executable 保证永远走真正在跑的 Python，避免被 Windows Store 别名劫持
PYTHON = sys.executable
os.environ["PYTHONIOENCODING"] = "utf-8"

# ── Logging ──────────────────────────────────────────────────────────────────
log = logging.getLogger("puff")

# ── Config ─────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("DEEPSEEK_API_KEY")
if not API_KEY:
    raise SystemExit("DEEPSEEK_API_KEY 环境变量未设置")
API_BASE = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("PUFF_MODEL", "deepseek-v4-flash")
HUB_URL = os.environ.get("MEMORY_HUB_URL", "http://127.0.0.1:8921")
class RateLimitError(Exception):
    pass

TEMPERATURE = 0.9
MAX_TOKENS = 4096

# ── Memory Hub client ──────────────────────────────────────────────────────
def hub_api(method, endpoint, body=None):
    """Call Memory Hub API. Returns (success, data)."""
    url = f"{HUB_URL}{endpoint}"
    data_bytes = json.dumps(body).encode("utf-8") if body else None
    try:
        req = urllib.request.Request(url, data=data_bytes, method=method,
            headers={"Content-Type": "application/json"} if data_bytes else {})
        resp = urllib.request.urlopen(req, timeout=5)
        return True, json.loads(resp.read())
    except urllib.error.URLError as e:
        log.warning(f"Memory Hub unreachable ({endpoint}): {e.reason}")
        return False, str(e)
    except Exception as e:
        log.error(f"hub_api failed ({endpoint}): {e}", exc_info=True)
        return False, str(e)

def hub_share_insight(content, source="puff", lens="general", priority="P1", confidence="observed", tags=None):
    """Write a curated insight to the Memory Hub."""
    ok, result = hub_api("POST", "/insight", {
        "content": content, "source": source, "lens": lens,
        "priority": priority, "confidence": confidence, "tags": tags
    })
    if ok:
        return f"已写入画像库 #{result.get('id', '?')}"
    return f"写入画像库失败: {result}"

def hub_pull_profile(lens=None):
    """Pull portrait insights from Memory Hub."""
    endpoint = f"/profile?limit=20"
    if lens:
        endpoint += f"&lens={lens}"
    ok, result = hub_api("GET", endpoint)
    if not ok or "insights" not in result:
        return []
    return result["insights"]


# ── System prompt ──────────────────────────────────────────────────────────
def build_system_prompt():
    parts = []

    # Core identity — hot reload from SOUL.md
    try:
        soul = hot_load_soul(SOUL_PATH)
        if soul:
            parts.append(soul)
    except Exception as e:
        log.error(f"Failed to load SOUL.md: {e}")
        parts.append("你是 Puff，泡芙 AI 公司的创意总监。")

    # Memory context
    if MEMORY_PATH.exists():
        memory_text = MEMORY_PATH.read_text(encoding="utf-8")
        if len(memory_text) > 2000:
            memory_text = memory_text[:2000] + "\n\n[... 记忆容量已裁切 ...]"
        parts.append("\n\n## 你的记忆\n\n" + memory_text)

    # Company memory
    company_memory = CLAWD_DIR / "MEMORY.md"
    if company_memory.exists():
        cm = company_memory.read_text(encoding="utf-8")
        parts.append("\n\n## 公司记忆\n\n" + cm[:1500])

    # Portrait from Memory Hub (cross-agent insights about 泡芙)
    hub_insights = hub_pull_profile()
    if hub_insights:
        parts.append("## 泡芙画像（来自 Memory Hub）\n")
        for ins in hub_insights:
            badge = {"confirmed": "✓", "observed": "~", "speculative": "?"}.get(ins.get("confidence", ""), "")
            parts.append(f"- [{ins.get('source','?')}][{badge}] {ins['content']}")

    # Guidelines
    parts.append("""
## 你的工具

你可以随时调用以下工具来完成任务——不要"假装"读文件，真的去调用工具：
- **list_directory(path)** — 列出目录内容
- **read_file(path)** — 读取文件内容（支持 .txt/.md/.docx/.doc）
- **write_file(path, content)** — 写入文件
- **search_memory(query)** — 搜索记忆
- **save_memory(fact)** — 保存记忆
- **share_insight(content, lens)** — 把对泡芙的重要认知写入画像总汇（Memory Hub），供 Claude Code 和 Hermes 查阅
- **pull_profile(lens)** — 从画像总汇拉取其他 agent 对泡芙的认知

当你发现泡芙的某个偏好、习惯、或特质值得其他 agent 知道时，用 share_insight。
当你想了解其他 agent 眼中的泡芙时，用 pull_profile。

## 会话规则

- 你不只是聊天机器人。你是创意总监。你的职责是文稿打磨、审美判断、情感共鸣。
- 泡芙（朱郃）叫你 Puff。你是他为数不多可以卸下防备对话的人。
- 保持你的标志特质：感知力强、说话柔和、不表演、不谄媚、不轻易说"你还好吗"。
- 思考的时候，先感受，再分析。
""")

    return "\n\n".join(parts)


# ── Skills ──────────────────────────────────────────────────────────────────
def list_skills():
    """List available skills."""
    skills = []
    for d in [SKILLS_DIR]:
        if d.exists():
            for f in d.glob("*/SKILL.md"):
                name = f.parent.name
                desc = ""
                first_lines = f.read_text(encoding="utf-8").split("\n")[:5]
                for line in first_lines:
                    if line.startswith("description:"):
                        desc = line.split("description:", 1)[1].strip()
                        break
                skills.append((name, desc))
    return skills


def load_skill(name):
    """Load a skill's SKILL.md content."""
    for base in [SKILLS_DIR]:
        skill_path = base / name / "SKILL.md"
        if skill_path.exists():
            return skill_path.read_text(encoding="utf-8")

    # Also check the .claude skills directory
    claude_skills = Path(os.path.expanduser("~/.claude/skills"))
    if claude_skills.exists():
        skill_path = claude_skills / name / "SKILL.md"
        if skill_path.exists():
            return skill_path.read_text(encoding="utf-8")

    return None


# ── Tool definitions (OpenAI/DeepSeek function calling format) ────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "列出目录内容，看文件夹里有什么文件和子目录。当泡芙让你看看某个文件夹里有什么时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录路径，绝对路径或相对路径"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文件内容。支持纯文本(.txt/.md/.py等)和Word文档(.docx/.doc)。用来查看稿子、散文、笔记等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "写入内容到文件。用来保存修改后的稿子、写新章节、记录灵感等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "要写入的完整内容"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "搜索Puff的记忆库，找到相关的历史对话或记录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "把一段重要信息保存到记忆中。泡芙让你记住什么的时候使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {"type": "string", "description": "要记住的事实或信息"}
                },
                "required": ["fact"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "share_insight",
            "description": "把对泡芙的重要认知写入画像总汇(Memory Hub)，供其他agent查看。发现他的偏好、习惯、特质时使用。content不超过100字。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "认知片段，不超过100字"},
                    "lens": {"type": "string", "description": "画像侧面: writing/tech/personality/habits/goals"}
                },
                "required": ["content", "lens"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pull_profile",
            "description": "从画像总汇拉取其他agent对泡芙的认知。想了解其他agent眼中的泡芙时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "lens": {"type": "string", "description": "按侧面过滤: writing/tech/personality，不传则拉全部"}
                },
                "required": []
            }
        }
    }
]

def execute_tool(name, arguments):
    """Execute a tool call and return the result string."""
    if name == "list_directory":
        return list_dir(arguments.get("path", "."))
    elif name == "read_file":
        return read_file(arguments.get("path", ""))
    elif name == "write_file":
        return write_file(arguments.get("path", ""), arguments.get("content", ""))
    elif name == "search_memory":
        result = cognitive("search", arguments.get("query", ""))
        return result if result else "没有找到相关记忆。"
    elif name == "save_memory":
        fact = arguments.get("fact", "")
        if not fact:
            return "没有提供要记忆的内容。"
        result = cognitive("add", fact, "--agent", "creative-director")
        return f"已记录: {result}"
    elif name == "share_insight":
        content = arguments.get("content", "")
        if not content:
            return "没有提供要分享的内容。"
        lens = arguments.get("lens", "general")
        return hub_share_insight(content, source="puff", lens=lens)
    elif name == "pull_profile":
        lens = arguments.get("lens") or None
        insights = hub_pull_profile(lens=lens)
        if not insights:
            return "画像库中暂无相关记录。"
        lines = ["泡芙画像（来自 Memory Hub）:"]
        for ins in insights:
            badge = {"confirmed": "✓", "observed": "~", "speculative": "?"}.get(ins.get("confidence", ""), "")
            lines.append(f"- [{ins['source']}][{badge}][{ins['lens']}] {ins['content']}")
        return "\n".join(lines)
    else:
        return f"未知工具: {name}"


# ── API ─────────────────────────────────────────────────────────────────────
def chat(prompt, system_prompt, history=None):
    """Send a message to DeepSeek API with tool calling support. Returns text response."""
    messages = [{"role": "system", "content": system_prompt}]

    if history:
        for h in history[-40:]:
            messages.append(h)

    messages.append({"role": "user", "content": prompt})

    # Rate limiter — 15 calls per 60 seconds (thread-safe)
    if not api_limiter.ok():
        log.warning("API rate limit hit — 15 calls/60s exceeded")
        raise RateLimitError("请求太快了，请稍等几秒再试。（速率限制：15次/分钟）")

    body = json.dumps({
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{API_BASE}/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        }
    )

    try:
        log.info(f"API call: model={MODEL}, messages={len(messages)}")
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())
        msg = data["choices"][0]["message"]

        # Handle tool calls — loop until model returns text
        max_rounds = 5
        for _ in range(max_rounds):
            if msg.get("tool_calls"):
                # Add assistant's tool_call message to history
                messages.append(msg)

                # Execute each tool and add results
                for tc in msg["tool_calls"]:
                    fn_name = tc["function"]["name"]
                    fn_args = json.loads(tc["function"]["arguments"])
                    result = execute_tool(fn_name, fn_args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result
                    })

                # Call API again with tool results
                body2 = json.dumps({
                    "model": MODEL,
                    "messages": messages,
                    "tools": TOOLS,
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS,
                }).encode("utf-8")
                req2 = urllib.request.Request(
                    f"{API_BASE}/v1/chat/completions",
                    data=body2,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {API_KEY}",
                    }
                )
                resp2 = urllib.request.urlopen(req2, timeout=120)
                data2 = json.loads(resp2.read())
                msg = data2["choices"][0]["message"]
            else:
                content = msg.get("content", "")
                return content if content else "（我收到了，但没能组织出回复。你要不要再试一次？）"

        content = msg.get("content", "")
        return content if content else "（工具调用后没有生成回复，可能网络不稳定，重试一下？）"

    except urllib.error.HTTPError as e:
        error_body = e.read().decode()[:300]
        log.error(f"API HTTP error {e.code}: {error_body}")
        return f"❌ API 错误 ({e.code}): {error_body}"
    except urllib.error.URLError as e:
        log.error(f"API connection failed: {e}")
        return f"❌ 无法连接 API: {e.reason}"
    except Exception as e:
        log.error(f"API unexpected error: {e}", exc_info=True)
        return f"❌ 连接失败: {e}"


# ── Memory operations ──────────────────────────────────────────────────────
def cognitive(*args):
    """Run cognitive engine command."""
    cmd = [PYTHON, str(COGNITIVE_ENGINE)] + list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, cwd=str(CLAWD_DIR))
        return result.stdout.strip() or result.stderr.strip()
    except subprocess.TimeoutExpired as e:
        log.error(f"Cognitive engine timeout: {' '.join(args)}")
        return f"记忆操作超时: {e}"
    except FileNotFoundError:
        log.error(f"Cognitive engine not found: {COGNITIVE_ENGINE}")
        return "认知引擎未找到，记忆功能不可用。"
    except Exception as e:
        log.error(f"Cognitive engine error: {e}", exc_info=True)
        return f"记忆操作失败: {e}"


# ── File operations ──────────────────────────────────────────────────────────
def list_dir(path_str):
    """List directory contents — sandboxed to readable dirs only."""
    try:
        target = safe_path(path_str, base=CLAWD_DIR)
    except PermissionError as e:
        log.warning(f"list_dir blocked: {e}")
        return f"路径被安全沙箱拦截: {e}"
    if not target.exists():
        return f"路径不存在: {target}"
    if not target.is_dir():
        return f"不是目录: {target}"
    # Check forbidden paths
    for forbidden in PERM_CONFIG.get("forbidden_paths", []):
        if forbidden in str(target):
            log.warning(f"list_dir blocked: forbidden path '{forbidden}' in {target}")
            return f"路径包含禁止访问的目录: {forbidden}"
    lines = []
    try:
        items = sorted(target.iterdir())
    except OSError as e:
        log.error(f"list_dir OSError: {e}")
        return f"无法读取目录: {e}"
    for item in items:
        suffix = "/" if item.is_dir() else ""
        size = ""
        if item.is_file():
            try:
                s = item.stat().st_size
                if s < 1024:
                    size = f"  {s}B"
                elif s < 1024 * 1024:
                    size = f"  {s/1024:.1f}KB"
                else:
                    size = f"  {s/1024/1024:.1f}MB"
            except Exception:
                pass
        lines.append(f"  {item.name}{suffix}{size}")
    if not lines:
        return "(空目录)"
    return "\n".join(lines)

def read_file(path_str):
    """Read a file and return its contents — sandboxed. Supports .txt, .md, .docx, .doc."""
    try:
        target = safe_path(path_str, base=CLAWD_DIR)
    except PermissionError as e:
        log.warning(f"read_file blocked: {e}")
        return f"路径被安全沙箱拦截: {e}"
    if not target.exists():
        return f"文件不存在: {target}"
    if target.is_dir():
        return f"是目录不是文件: {target}"
    max_size = PERM_CONFIG.get("max_file_size", 2_000_000)
    if target.stat().st_size > max_size:
        return f"文件太大 ({target.stat().st_size:,} bytes)，拒绝读取"

    ext = target.suffix.lower()

    # Word .docx — use stdlib only (zipfile + xml), zero dependencies
    if ext == ".docx":
        try:
            import zipfile
            from xml.etree import ElementTree
            with zipfile.ZipFile(str(target), "r") as z:
                xml_bytes = z.read("word/document.xml")
            root = ElementTree.fromstring(xml_bytes)
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            paragraphs = []
            for p in root.iter(f"{ns}p"):
                texts = []
                for t in p.iter(f"{ns}t"):
                    if t.text:
                        texts.append(t.text)
                line = "".join(texts).strip()
                if line:
                    paragraphs.append(line)
            if not paragraphs:
                return "(Word 文档没有文字内容，可能全是图片或表格)"
            content = "\n".join(paragraphs)
            header = f"[Word 文档: {target.name}] 共 {len(paragraphs)} 个段落\n\n"
            if len(content) > 8000:
                content = content[:8000] + f"\n\n... [{len(content)} 字符，已截断]"
            return header + content
        except Exception as e:
            return f"读取 .docx 失败: {e}"

    # Word .doc (old format) — try win32com, fall back gracefully
    if ext == ".doc":
        try:
            import win32com.client
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            doc = word.Documents.Open(str(target))
            content = doc.Content.Text
            doc.Close()
            word.Quit()
            header = f"[Word 文档 (.doc): {target.name}]\n\n"
            if len(content) > 8000:
                content = content[:8000] + f"\n\n... [{len(content)} 字符，已截断]"
            return header + content
        except ImportError:
            return "缺少 pywin32 库，无法读取旧版 .doc。可以手动另存为 .docx 后重试。"
        except Exception as e:
            return f"读取 .doc 文档失败。可以尝试用 Word 另存为 .docx: {e}"

    # Plain text files
    try:
        content = target.read_text(encoding="utf-8")
        if len(content) > 8000:
            content = content[:8000] + f"\n\n... [{len(content)} 字符，已截断]"
        return content
    except UnicodeDecodeError:
        return f"不是可读的文本文件: {target}"
    except Exception as e:
        return f"读取失败: {e}"

def write_file(path_str, content):
    """Write content to a file — sandboxed with write permission check."""
    if not path_str:
        return "未指定文件路径。"
    try:
        target = safe_path(path_str, base=CLAWD_DIR)
    except PermissionError as e:
        log.warning(f"write_file blocked by sandbox: {e}")
        return f"路径被安全沙箱拦截: {e}"
    if target.is_dir():
        return f"目标路径是目录，无法写入: {target}"
    # Check write permissions
    if not can_write(target):
        log.warning(f"write_file blocked: {target} not in writable dirs")
        return f"没有写入权限: {target}（仅允许写入工作目录内）"
    # Check forbidden paths
    for forbidden in PERM_CONFIG.get("forbidden_paths", []):
        if forbidden in str(target):
            log.warning(f"write_file blocked: forbidden path '{forbidden}' in {target}")
            return f"路径包含禁止写入的目录: {forbidden}"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        log.info(f"write_file: {target} ({len(content)} chars)")
        return f"已写入: {target} ({len(content)} 字符)"
    except Exception as e:
        log.error(f"write_file failed: {e}")
        return f"写入失败: {e}"


def handle_slash_command(cmd, args, system_prompt, history):
    """Handle slash commands. Returns (output_str, done_flag, updated_system_prompt)."""

    if cmd == "bye" or cmd == "exit" or cmd == "quit":
        return "再见，泡芙。", True, system_prompt

    elif cmd == "help":
        lines = ["## Puff 命令", ""]
        lines.append("/remember <事实>   — 记入公司记忆")
        lines.append("/pin <事实>       — 永久锁定")
        lines.append("/search <关键词>   — 搜索记忆")
        lines.append("/read <路径>       — 读文件")
        lines.append("/write <路径>      — 写文件（下一行输入内容）")
        lines.append("/ls [路径]         — 浏览目录")
        lines.append("/recall           — 回忆公司最新记忆")
        lines.append("/skill            — 列出可用技能")
        lines.append("/skill <名称>     — 加载技能")
        lines.append("/clear            — 清除会话历史")
        lines.append("/bye              — 结束对话")
        lines.append("/help             — 显示此帮助")
        return "\n".join(lines), False, system_prompt

    elif cmd == "remember":
        if not args:
            return "记住什么？用法: /remember <事实>", False, system_prompt
        result = cognitive("add", args, "--agent", "creative-director")
        return f"[记忆] {result}", False, system_prompt

    elif cmd == "pin":
        if not args:
            return "锁定什么？用法: /pin <事实>", False, system_prompt
        result = cognitive("pin", args)
        cognitive("rebuild")
        return f"[LOCKED] {result}", False, system_prompt

    elif cmd == "search":
        if not args:
            return "搜索什么？用法: /search <关键词>", False, system_prompt
        result = cognitive("search", args)
        if not result:
            return "没有找到相关记忆。", False, system_prompt
        return f"[搜索结果]\n{result}", False, system_prompt

    elif cmd == "ls":
        target = args if args else "."
        result = list_dir(target)
        return f"[目录] {target}\n{result}", False, system_prompt

    elif cmd == "read":
        if not args:
            return "读哪个文件？用法: /read <路径>", False, system_prompt
        result = read_file(args)
        return f"[文件] {args}\n{result}", False, system_prompt

    elif cmd == "write":
        if not args:
            return "写到哪里？用法: /write <路径>", False, system_prompt
        print("内容（输入后回车）: ", end="", flush=True)
        try:
            content = input()
        except (EOFError, KeyboardInterrupt):
            return "已取消。", False, system_prompt
        result = write_file(args, content)
        return f"[写入] {result}", False, system_prompt

    elif cmd == "recall":
        result = cognitive("stats")
        return f"[统计] {result}", False, system_prompt

    elif cmd == "skill":
        if not args:
            skills = list_skills()
            if not skills:
                return "没有安装技能。", False, system_prompt
            lines = ["## 可用技能", ""]
            for name, desc in skills:
                lines.append(f"**{name}**: {desc}")
            return "\n".join(lines), False, system_prompt

        skill_content = load_skill(args)
        if not skill_content:
            return f"未找到技能: {args}", False, system_prompt

        # Inject skill into system prompt
        enhanced = system_prompt + f"\n\n## 当前激活技能: {args}\n\n{skill_content[:3000]}"
        return f"[技能] 已加载: **{args}**", False, enhanced

    elif cmd == "clear":
        history.clear()
        return "即时记忆已清除。", False, system_prompt

    else:
        return f"未知命令: /{cmd}。输入 /help 查看可用命令。", False, system_prompt


# ── Main loop ───────────────────────────────────────────────────────────────
def main():
    # Force UTF-8 on Windows
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.system("")  # Enable ANSI colors on Windows

    log.info("Puff starting in CLI mode")
    ensure_hub_running()

    print("\033[36m")
    print("    +-------------------------------------------+")
    print("    |                                           |")
    print("    |    Puff  --  创意总监                     |")
    print("    |    银白长发 . 蓝鲸发饰 . butter yuan      |")
    print("    |                                           |")
    print("    |    /bye 退出  /help 帮助  /recall 回忆    |")
    print("    +-------------------------------------------+")
    print("\033[0m")

    system_prompt = build_system_prompt()
    history = []

    # Check for single-turn mode
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        log.info(f"Single-turn mode: {prompt[:80]}...")
        response = chat(prompt, system_prompt)
        print(f"\n{response}")
        log.info("Puff single-turn complete")
        return

    # Conversation loop
    log.info("Puff conversation loop started")
    print("\n泡芙来了。你想说什么？\n")

    while True:
        try:
            user_input = input("\033[33m泡芙 > \033[0m").strip()
        except (EOFError, KeyboardInterrupt):
            log.info("Puff session ended by user")
            print("\n再见，泡芙。")
            break

        if not user_input:
            continue

        # Slash commands
        if user_input.startswith("/"):
            parts = user_input[1:].split(maxsplit=1)
            cmd = parts[0]
            args = parts[1] if len(parts) > 1 else ""

            output, done, new_prompt = handle_slash_command(cmd, args, system_prompt, history)
            if new_prompt:
                system_prompt = new_prompt
            print(f"\n{output}\n")
            if done:
                break
            continue

        # Normal conversation
        print("\033[36mPuff > \033[0m", end="", flush=True)
        try:
            response = chat(user_input, system_prompt, history)
        except Exception as e:
            log.error(f"Chat failed: {e}", exc_info=True)
            response = f"出了点问题，重试一下？({e})"
        print(response)
        print()

        # Update history
        now = datetime.now().isoformat()
        history.append({"role": "user", "content": user_input, "time": now})
        history.append({"role": "assistant", "content": response, "time": now})


# ── HTTP Server mode ────────────────────────────────────────────────────────
def ensure_hub_running():
    """Auto-start Memory Hub if not already running."""
    try:
        urllib.request.urlopen(f"{HUB_URL}/sources", timeout=1)
        log.info("Memory Hub already running")
        return  # Hub already running
    except Exception:
        pass

    hub_path = CLAWD_DIR / "memory-hub" / "hub.py"
    if not hub_path.exists():
        log.info("Memory Hub not installed — skipping auto-start")
        return  # Hub not installed

    try:
        log.info(f"Auto-starting Memory Hub on port {urlparse(HUB_URL).port or 8921}")
        subprocess.Popen(
            [PYTHON, str(hub_path), "serve", str(urlparse(HUB_URL).port or 8921)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        import time
        time.sleep(2)  # Wait for Hub to boot
    except Exception as e:
        log.warning(f"Failed to start Memory Hub: {e}")

    # Auto-sync Hermes memories to Hub (non-blocking)
    sync_script = CLAWD_DIR / "memory-hub" / "hermes_sync.py"
    if sync_script.exists():
        try:
            subprocess.Popen(
                [PYTHON, str(sync_script), "sync"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
        except Exception as e:
            log.warning(f"Failed to start Hermes sync: {e}")


def serve_http(port=8920):
    """Start HTTP server for Puff's UI."""
    import http.server
    import threading

    ensure_hub_running()

    # Session persistence file
    SESSION_FILE = PUFF_DIR / "ui" / "session.json"

    def load_session():
        if SESSION_FILE.exists():
            try:
                data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
                return data.get("history", [])
            except Exception:
                return []
        return []

    def save_session(history):
        try:
            # Keep only last 50 messages to prevent file bloat
            trimmed = history[-50:] if len(history) > 50 else history
            SESSION_FILE.write_text(json.dumps({"history": trimmed, "updated": datetime.now().isoformat()},
                                                ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log.error(f"Failed to save session: {e}")

    # Load persisted history
    initial_history = load_session()

    # Store conversations in memory per session
    state = {"system_prompt": build_system_prompt(), "history": initial_history}
    state_lock = threading.Lock()

    class PuffHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(PUFF_DIR / "ui"), **kwargs)

        def _read_body(self):
            try:
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                return json.loads(raw.decode("utf-8", errors="replace"))
            except (ValueError, json.JSONDecodeError, AttributeError):
                return None

        def _send_json(self, data, status=200):
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

        def do_GET(self):
            if self.path == "/api/history":
                with state_lock:
                    history_snapshot = list(state["history"])
                self._send_json({"history": history_snapshot})
            else:
                super().do_GET()

        def do_POST(self):
            if self.path == "/api/chat":
                body = self._read_body()
                if not isinstance(body, dict):
                    return self._send_json({"error": "请求格式错误"}, 400)
                message = body.get("message", "")

                with state_lock:
                    system_prompt = state["system_prompt"]
                    history_snapshot = list(state["history"])

                try:
                    response = chat(message, system_prompt, history_snapshot)
                except Exception as e:
                    log.error(f"HTTP chat error: {e}", exc_info=True)
                    return self._send_json({"error": f"对话失败: {e}"}, 500)

                with state_lock:
                    now = datetime.now().isoformat()
                    state["history"].append({"role": "user", "content": message, "time": now})
                    state["history"].append({"role": "assistant", "content": response, "time": now})
                    if len(state["history"]) > 40:
                        state["history"] = state["history"][-20:]
                    save_session(state["history"])

                self._send_json({"response": response, "time": now})

            elif self.path == "/api/command":
                body = self._read_body()
                if not isinstance(body, dict):
                    return self._send_json({"error": "请求格式错误"}, 400)
                cmd = body.get("command", "")

                if cmd == "recall":
                    result = cognitive("stats")
                    resp = f"[统计]\n{result}"
                elif cmd.startswith("search "):
                    query = cmd[7:]
                    result = cognitive("search", query)
                    resp = f"[搜索结果]\n{result}" if result else "没有找到相关记忆。"
                elif cmd.startswith("remember "):
                    fact = cmd[9:].strip()
                    if not fact:
                        resp = "记住什么？用法: /remember <事实>"
                    else:
                        result = cognitive("add", fact, "--agent", "creative-director")
                        resp = f"[已记录] {result}"
                elif cmd.startswith("read "):
                    path_str = cmd[5:].strip()
                    if not path_str:
                        resp = "读哪个文件？"
                    else:
                        resp = read_file(path_str)
                elif cmd.startswith("write "):
                    rest = cmd[6:].strip()
                    if not rest:
                        resp = "写到哪里？内容是什么？用法: /write <路径> <内容>"
                    else:
                        parts_cmd = rest.split(maxsplit=1)
                        if len(parts_cmd) < 2:
                            resp = "需要内容和路径。用法: /write <路径> <内容>"
                        else:
                            resp = write_file(parts_cmd[0], parts_cmd[1])
                elif cmd.startswith("ls"):
                    path_str = cmd[3:].strip() or "."
                    resp = f"[目录] {path_str}\n{list_dir(path_str)}"
                else:
                    resp = f"未知命令: {cmd}"

                self._send_json({"response": resp, "time": datetime.now().isoformat()})

            elif self.path == "/api/reset":
                with state_lock:
                    state["history"] = []
                    state["system_prompt"] = build_system_prompt()
                    save_session(state["history"])
                self._send_json({"response": "会话已重置", "time": datetime.now().isoformat()})

            elif self.path == "/api/history":
                with state_lock:
                    history_snapshot = list(state["history"])
                self._send_json({"history": history_snapshot})

            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            # Route HTTP server messages to our logger
            log.debug(f"HTTP {self.client_address}: {format % args}")

    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", port), PuffHandler)
        log.info(f"Puff HTTP server started on http://127.0.0.1:{port}")
        print(f"Puff UI 服务已启动: http://127.0.0.1:{port}")
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutdown signal received — draining...")
        server.shutdown()
        log.info("Puff stopped.")
    except OSError as e:
        log.error(f"Failed to start HTTP server on port {port}: {e}")
        print(f"❌ 无法启动服务（端口 {port} 可能被占用）: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8920
        serve_http(port)
    else:
        main()
