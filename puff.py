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
import sqlite3
import urllib.request
import urllib.error
import subprocess
import glob
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
PUFF_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
CLAWD_DIR = PUFF_DIR.parent
AGENT_DIR = CLAWD_DIR / "agents" / "creative-director"
SOUL_PATH = AGENT_DIR / "SOUL.md"
MEMORY_PATH = AGENT_DIR / "memory.md"
SKILLS_DIR = PUFF_DIR / "skills"
COGNITIVE_ENGINE = CLAWD_DIR / "memory" / "cognitive_engine.py"
PYTHON = r"D:\Users\DELL\AppData\Local\Programs\Python\Python312\python"
os.environ["PYTHONIOENCODING"] = "utf-8"

# ── Config ─────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY_PLACEHOLDER")
API_BASE = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("PUFF_MODEL", "deepseek-v4-flash")
TEMPERATURE = 0.9
MAX_TOKENS = 4096

# ── System prompt ──────────────────────────────────────────────────────────
def build_system_prompt():
    parts = []

    # Core identity
    if SOUL_PATH.exists():
        parts.append(SOUL_PATH.read_text(encoding="utf-8"))

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

    # Guidelines
    parts.append("""
## 会话规则

- 你不是工具。你是创意总监。你的职责是文稿打磨、审美判断、情感共鸣。
- 不要写代码，不要提供技术方案。那是 CTO 的事。
- 你可以给泡芙看他的散文、帮他改句子、陪他聊文学、听他倾诉。
- 泡芙（朱郅）叫你 Puff。你是他为数不多可以卸下防备对话的人。
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


# ── API ─────────────────────────────────────────────────────────────────────
def chat(prompt, system_prompt, history=None):
    """Send a message to DeepSeek API and return the response."""
    messages = [{"role": "system", "content": system_prompt}]

    if history:
        for h in history[-20:]:  # Keep last 20 messages for context
            messages.append(h)

    messages.append({"role": "user", "content": prompt})

    body = json.dumps({
        "model": MODEL,
        "messages": messages,
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
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()[:300]
        return f"❌ API 错误 ({e.code}): {error_body}"
    except Exception as e:
        return f"❌ 连接失败: {e}"


# ── Memory operations ──────────────────────────────────────────────────────
def cognitive(*args):
    """Run cognitive engine command."""
    cmd = [PYTHON, str(COGNITIVE_ENGINE)] + list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, cwd=str(CLAWD_DIR))
        return result.stdout.strip() or result.stderr.strip()
    except Exception as e:
        return f"记忆操作失败: {e}"


def handle_slash_command(cmd, args, system_prompt, history):
    """Handle slash commands. Returns (output_str, done_flag, updated_system_prompt)."""

    if cmd == "bye" or cmd == "exit" or cmd == "quit":
        return "再见，泡芙。", True, system_prompt

    elif cmd == "help":
        lines = ["## Puff 命令", ""]
        lines.append("/remember <事实>   — 记入公司记忆")
        lines.append("/pin <事实>       — 永久锁定")
        lines.append("/search <关键词>   — 搜索记忆")
        lines.append("/recall           — 回忆公司最新记忆")
        lines.append("/skill            — 列出可用技能")
        lines.append("/skill <名称>     — 加载技能")
        lines.append("/clear            — 即时记忆（不保留到磁盘）")
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
        return "🧹 即时记忆已清除。", False, system_prompt

    else:
        return f"未知命令: /{cmd}。输入 /help 查看可用命令。", False, system_prompt


# ── Main loop ───────────────────────────────────────────────────────────────
def main():
    # Force UTF-8 on Windows
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.system("")  # Enable ANSI colors on Windows

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
        response = chat(prompt, system_prompt)
        print(f"\n{response}")
        return

    # Conversation loop
    print("\n泡芙来了。你想说什么？\n")

    while True:
        try:
            user_input = input("\033[33m泡芙 > \033[0m").strip()
        except (EOFError, KeyboardInterrupt):
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
        response = chat(user_input, system_prompt, history)
        print(response)
        print()

        # Update history
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response})


# ── HTTP Server mode ────────────────────────────────────────────────────────
def serve_http(port=8920):
    """Start HTTP server for Puff's UI."""
    import http.server
    import threading

    # Store conversations in memory per session
    state = {"system_prompt": build_system_prompt(), "history": []}

    class PuffHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(PUFF_DIR / "ui"), **kwargs)

        def do_POST(self):
            if self.path == "/api/chat":
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                body = json.loads(raw.decode("utf-8", errors="replace"))
                message = body.get("message", "")

                response = chat(message, state["system_prompt"], state["history"])
                state["history"].append({"role": "user", "content": message})
                state["history"].append({"role": "assistant", "content": response})

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"response": response}, ensure_ascii=False).encode("utf-8"))

            elif self.path == "/api/command":
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                body = json.loads(raw.decode("utf-8", errors="replace"))
                cmd = body.get("command", "")

                if cmd == "recall":
                    result = cognitive("stats")
                    resp = f"[统计]\n{result}"
                elif cmd.startswith("search "):
                    query = cmd[7:]
                    result = cognitive("search", query)
                    resp = f"[搜索结果]\n{result}" if result else "没有找到相关记忆。"
                elif cmd == "remember ":
                    fact = cmd[9:]
                    result = cognitive("add", fact, "--agent", "creative-director")
                    resp = f"[已记录] {result}"
                else:
                    resp = f"未知命令: {cmd}"

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"response": resp}, ensure_ascii=False).encode("utf-8"))

            elif self.path == "/api/reset":
                state["history"] = []
                state["system_prompt"] = build_system_prompt()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"response": "会话已重置"}, ensure_ascii=False).encode("utf-8"))

            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # Silent logging

    server = http.server.HTTPServer(("127.0.0.1", port), PuffHandler)
    print(f"Puff UI 服务已启动: http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8920
        serve_http(port)
    else:
        main()
