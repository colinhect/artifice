"""Executor functions for agent tools.

Each executor is an async function: (args: dict) -> str.
They are registered on ToolDef.executor so the terminal can invoke them
directly when the user approves a tool call.
"""

from __future__ import annotations

import asyncio
import glob
import os
import platform
import shutil
from typing import Any


async def execute_read_file(args: dict[str, Any]) -> str:
    """Read file contents, optionally with offset and limit."""
    path = os.path.expanduser(args["path"])
    offset = args.get("offset", 0)
    limit = args.get("limit")

    if not os.path.isfile(path):
        return f"Error: File not found: {path}"

    try:
        with open(path) as f:
            lines = f.readlines()
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except Exception as e:
        return f"Error reading file: {e}"

    if offset:
        lines = lines[offset:]
    if limit:
        lines = lines[:limit]

    start = offset or 0
    numbered = []
    for i, line in enumerate(lines):
        numbered.append(f"{start + i + 1:4d} | {line}")

    return "".join(numbered) if numbered else "(empty file)"


async def execute_write_file(args: dict[str, Any]) -> str:
    """Write content to a file, creating directories as needed."""
    path = os.path.expanduser(args["path"])
    content = args["content"]

    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error writing file: {e}"


async def execute_file_search(args: dict[str, Any]) -> str:
    """Search for files matching a glob pattern."""
    pattern = args["pattern"]
    path = os.path.expanduser(args.get("path", "."))

    full_pattern = os.path.join(path, pattern)

    loop = asyncio.get_running_loop()
    try:
        matches = await loop.run_in_executor(
            None, lambda: sorted(glob.glob(full_pattern, recursive=True))
        )
    except Exception as e:
        return f"Error searching: {e}"

    if not matches:
        return f"No files matching '{pattern}' in {path}"

    max_results = 100
    result = "\n".join(matches[:max_results])
    if len(matches) > max_results:
        result += f"\n... and {len(matches) - max_results} more"
    return result


async def execute_web_fetch(args: dict[str, Any]) -> str:
    """Fetch contents of a URL."""
    import urllib.request

    url = args["url"]

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Artifice/1.0"})
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: urllib.request.urlopen(req, timeout=15),  # noqa: S310
        )
        content = response.read()
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1")

        max_chars = 50_000
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n... (truncated, {len(text)} total chars)"
        return text
    except Exception as e:
        return f"Error fetching URL: {e}"


async def execute_web_search(args: dict[str, Any]) -> str:
    """Search the web using DuckDuckGo HTML."""
    import re
    import urllib.parse
    import urllib.request

    query = args["query"]
    encoded = urllib.parse.urlencode({"q": query})
    url = f"https://html.duckduckgo.com/html/?{encoded}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Artifice/1.0"})
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: urllib.request.urlopen(req, timeout=15),  # noqa: S310
        )
        html = response.read().decode("utf-8", errors="replace")

        results = []
        pattern = r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
        for match in re.finditer(pattern, html):
            href = match.group(1)
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            if href and title:
                results.append(f"- {title}\n  {href}")

        if not results:
            return f"No results found for '{query}'"

        return f"Search results for '{query}':\n\n" + "\n\n".join(results[:10])
    except Exception as e:
        return f"Error searching: {e}"


async def execute_system_info(args: dict[str, Any]) -> str:
    """Get system information for requested categories."""
    categories = args.get("categories", ["os", "env", "cwd"])

    sections = []

    if "os" in categories:
        sections.append(
            f"OS: {platform.system()} {platform.release()}\n"
            f"Platform: {platform.platform()}\n"
            f"Python: {platform.python_version()}\n"
            f"Architecture: {platform.machine()}"
        )

    if "cwd" in categories:
        sections.append(f"Working directory: {os.getcwd()}")

    if "env" in categories:
        safe_vars = [
            "HOME",
            "USER",
            "SHELL",
            "TERM",
            "PATH",
            "LANG",
            "EDITOR",
            "VIRTUAL_ENV",
        ]
        env_lines = []
        for var in safe_vars:
            val = os.environ.get(var)
            if val:
                env_lines.append(f"  {var}={val}")
        if env_lines:
            sections.append("Environment:\n" + "\n".join(env_lines))

    if "disk" in categories:
        try:
            usage = shutil.disk_usage(".")
            total_gb = usage.total / (1024**3)
            free_gb = usage.free / (1024**3)
            used_gb = usage.used / (1024**3)
            sections.append(
                f"Disk usage (current mount):\n"
                f"  Total: {total_gb:.1f} GB\n"
                f"  Used:  {used_gb:.1f} GB\n"
                f"  Free:  {free_gb:.1f} GB"
            )
        except Exception:
            pass

    return "\n\n".join(sections) if sections else "No information categories specified."
