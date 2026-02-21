"""Executor functions for agent tools.

Each executor is an async function: (args: dict) -> str.
They are registered on ToolDef.executor so the terminal can invoke them
directly when the user approves a tool call.
"""

from __future__ import annotations

import asyncio
import glob
import logging
import os
import platform
import re
import shutil
from typing import Any

logger = logging.getLogger(__name__)


async def execute_read(args: dict[str, Any]) -> str:
    """Read file contents, optionally with offset and limit."""
    path = os.path.expanduser(args["path"])
    offset = args.get("offset", 0)
    limit = args.get("limit")

    logger.debug("Reading file: %s (offset=%d, limit=%s)", path, offset, limit)

    if not os.path.isfile(path):
        logger.warning("File not found: %s", path)
        return f"Error: File not found: {path}"

    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except PermissionError:
        logger.warning("Permission denied: %s", path)
        return f"Error: Permission denied: {path}"
    except Exception as e:
        logger.error("Error reading file %s: %s", path, e)
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


async def execute_write(args: dict[str, Any]) -> str:
    """Write content to a file, creating directories as needed."""
    path = os.path.expanduser(args["path"])
    content = args["content"]

    logger.debug("Writing %d bytes to: %s", len(content), path)

    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.debug("Successfully wrote to: %s", path)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        logger.error("Error writing file %s: %s", path, e)
        return f"Error writing file: {e}"


async def execute_glob(args: dict[str, Any]) -> str:
    """Search for files matching a glob pattern."""
    pattern = args["pattern"]
    path = os.path.expanduser(args.get("path", "."))

    logger.debug("Searching for files: pattern=%s, path=%s", pattern, path)

    full_pattern = os.path.join(path, pattern)

    loop = asyncio.get_running_loop()
    try:
        matches = await loop.run_in_executor(
            None, lambda: sorted(glob.glob(full_pattern, recursive=True))
        )
    except Exception as e:
        logger.error("Error searching files: %s", e)
        return f"Error searching: {e}"

    if not matches:
        logger.debug("No files found matching pattern: %s", pattern)
        return f"No files matching '{pattern}' in {path}"

    logger.debug("Found %d files matching pattern: %s", len(matches), pattern)
    max_results = 100
    result = "\n".join(matches[:max_results])
    if len(matches) > max_results:
        result += f"\n... and {len(matches) - max_results} more"
    return result


async def execute_grep(args: dict[str, Any]) -> str:
    """Search for regex patterns in files."""
    pattern = args["pattern"]
    path = os.path.expanduser(args.get("path", "."))
    file_filter = args.get("file_filter", "*")
    case_sensitive = args.get("case_sensitive", True)
    context_before = args.get("context_before", 0)
    context_after = args.get("context_after", 0)

    logger.debug(
        "Grep: pattern=%s, path=%s, filter=%s, case_sensitive=%s",
        pattern,
        path,
        file_filter,
        case_sensitive,
    )

    try:
        regex_flags = 0 if case_sensitive else re.IGNORECASE
        compiled_pattern = re.compile(pattern, regex_flags)
    except re.error as e:
        return f"Error: Invalid regex pattern: {e}"

    results = []
    max_files = 50
    max_matches = 200

    loop = asyncio.get_running_loop()

    async def search_file(filepath: str) -> list[str]:
        file_results = []
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception:
            return []

        for i, line in enumerate(lines):
            if compiled_pattern.search(line):
                line_num = i + 1
                content = line.rstrip("\n")
                file_results.append(f"  {line_num}: {content}")

                # Add context after
                for j in range(1, context_after + 1):
                    if i + j < len(lines):
                        file_results.append(f"  {line_num + j}: {lines[i + j].rstrip()}")

        return file_results

    async def process_directory():
        search_pattern = os.path.join(path, "**", file_filter)
        files = glob.glob(search_pattern, recursive=True)
        files = [f for f in files if os.path.isfile(f)]

        all_results = []
        for filepath in files[:max_files]:
            file_results = await search_file(filepath)
            if file_results:
                rel_path = os.path.relpath(filepath, path)
                all_results.append(f"{rel_path}:")
                all_results.extend(file_results)
                if len(all_results) >= max_matches:
                    return all_results[:max_matches]
        return all_results

    try:
        results = await loop.run_in_executor(None, asyncio.run, process_directory())
    except Exception as e:
        logger.error("Error during grep: %s", e)
        return f"Error during grep: {e}"

    if not results:
        return f"No matches found for '{pattern}' in {path}"

    output = "\n".join(results)
    if len(results) >= max_matches:
        output += f"\n... (max {max_matches} matches reached)"
    return output


async def execute_replace(args: dict[str, Any]) -> str:
    """Replace string occurrences in files with regex support."""
    path = os.path.expanduser(args["path"])
    pattern = args["pattern"]
    replacement = args["replacement"]
    case_sensitive = args.get("case_sensitive", True)
    dry_run = args.get("dry_run", True)

    logger.debug(
        "Replace: pattern=%s, replacement=%s, path=%s, case_sensitive=%s, dry_run=%s",
        pattern,
        replacement,
        path,
        case_sensitive,
        dry_run,
    )

    if not os.path.isfile(path):
        return f"Error: File not found: {path}"

    try:
        with open(path, encoding="utf-8") as f:
            original_content = f.read()
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except Exception as e:
        return f"Error reading file: {e}"

    try:
        regex_flags = 0 if case_sensitive else re.IGNORECASE
        compiled_pattern = re.compile(pattern, regex_flags)
    except re.error as e:
        return f"Error: Invalid regex pattern: {e}"

    new_content, count = compiled_pattern.subn(replacement, original_content)

    if count == 0:
        return f"No matches found for '{pattern}' in {path}"

    if dry_run:
        diff_lines = []
        old_lines = original_content.splitlines()
        new_lines = new_content.splitlines()

        for i, (old_line, new_line) in enumerate(zip(old_lines, new_lines)):
            if old_line != new_line:
                diff_lines.append(f"  Line {i + 1}:")
                diff_lines.append(f"  - {old_line}")
                diff_lines.append(f"  + {new_line}")

        if len(diff_lines) > 50:
            diff_lines = diff_lines[:50]
            diff_lines.append("  ... (truncated)")

        return (
            f"DRY RUN: {count} replacement(s) would be made to {path}:\n\n"
            + "\n".join(diff_lines)
        )

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        logger.debug("Replaced %d occurrences in: %s", count, path)
        return f"Replaced {count} occurrence(s) in {path}"
    except Exception as e:
        logger.error("Error writing file %s: %s", path, e)
        return f"Error writing file: {e}"


async def execute_web_fetch(args: dict[str, Any]) -> str:
    """Fetch contents of a URL."""
    import urllib.request

    url = args["url"]

    logger.debug("Fetching URL: %s", url)

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
        logger.debug("Fetched %d chars from: %s", len(text), url)
        return text
    except Exception as e:
        logger.error("Error fetching URL %s: %s", url, e)
        return f"Error fetching URL: {e}"


async def execute_web_search(args: dict[str, Any]) -> str:
    """Search the web using DuckDuckGo HTML."""
    import urllib.parse
    import urllib.request

    query = args["query"]
    logger.debug("Web search: %s", query)

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
            logger.debug("No search results for: %s", query)
            return f"No results found for '{query}'"

        logger.debug("Found %d search results for: %s", len(results), query)
        return f"Search results for '{query}':\n\n" + "\n\n".join(results[:10])
    except Exception as e:
        logger.error("Error searching web for '%s': %s", query, e)
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
