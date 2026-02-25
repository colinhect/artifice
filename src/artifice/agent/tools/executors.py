"""Executor functions for agent tools.

Each executor is an async function: (args: dict) -> str.
They are registered on ToolDef.executor so the terminal can invoke them
directly when the user approves a tool call.
"""

from __future__ import annotations

import asyncio
import glob
import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _relative_path(path: Path) -> Path:
    """Convert absolute path to relative path for display."""
    try:
        return path.relative_to(Path.cwd())
    except ValueError:
        return path


async def execute_read(args: dict[str, Any]) -> str:
    """Read file contents, optionally with offset and limit."""
    path = Path(args["path"]).expanduser().resolve()
    display_path = _relative_path(path)
    offset = args.get("offset", 0)
    limit = args.get("limit")

    logger.debug("Reading file: %s (offset=%d, limit=%s)", path, offset, limit)

    if not path.is_file():
        logger.warning("File not found: %s", path)
        return f"Error: File not found: {display_path}"

    try:
        content = path.read_text(encoding="utf-8")
    except PermissionError:
        logger.warning("Permission denied: %s", path)
        return f"Error: Permission denied: {display_path}"
    except Exception as e:
        logger.error("Error reading file %s: %s", path, e)
        return f"Error reading file: {e}"

    lines = content.splitlines(keepends=True)

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
    """Write content to a file, creating directories as needed.

    Returns JSON string with diff data for UI rendering.

    Args:
        args: {
            "path": str,
            "content": str
        }

    Returns:
        JSON string with structure:
        {
            "success": bool,
            "path": str,
            "old_lines": [str],    # existing content or empty if new file
            "new_lines": [str],    # new content
            "start_line": int,     # always 1 for write
            "context_before": [],  # empty for write
            "context_after": [],   # empty for write
            "is_new_file": bool,
            "error": str | None
        }
    """
    path = Path(args["path"]).expanduser().resolve()
    display_path = _relative_path(path)
    content = args["content"]

    logger.debug("Writing %d bytes to: %s", len(content), path)

    is_new_file = not path.exists()

    if is_new_file:
        old_lines = []
    else:
        try:
            old_content = path.read_text(encoding="utf-8")
            old_lines = old_content.splitlines()
        except Exception:
            old_lines = []

    new_lines = content.splitlines() if content else [""]

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.debug("Successfully wrote to: %s", path)
    except Exception as e:
        logger.error("Error writing file %s: %s", path, e)
        return json.dumps({"success": False, "error": f"Error writing file: {e}"})

    return json.dumps(
        {
            "success": True,
            "path": str(display_path),
            "old_lines": old_lines,
            "new_lines": new_lines,
            "start_line": 1,
            "context_before": [],
            "context_after": [],
            "is_new_file": is_new_file,
            "error": None,
        }
    )


async def execute_glob(args: dict[str, Any]) -> str:
    """Search for files matching a glob pattern."""
    pattern = args["pattern"]
    path = Path(args.get("path", ".")).expanduser().resolve()
    display_path = _relative_path(path)

    logger.debug("Searching for files: pattern=%s, path=%s", pattern, path)

    full_pattern = str(path / pattern)

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
        return f"No files matching '{pattern}' in {display_path}"

    logger.debug("Found %d files matching pattern: %s", len(matches), pattern)
    max_results = 100
    rel_matches = [str(_relative_path(Path(m))) for m in matches[:max_results]]
    result = "\n".join(rel_matches)
    if len(matches) > max_results:
        result += f"\n... and {len(matches) - max_results} more"
    return result


async def execute_grep(args: dict[str, Any]) -> str:
    """Search for regex patterns in files."""
    pattern = args["pattern"]
    path = Path(args.get("path", ".")).expanduser().resolve()
    display_path = _relative_path(path)
    file_filter = args.get("file_filter", "*")
    case_sensitive = args.get("case_sensitive", True)
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

    max_files = 50
    max_matches = 200

    def search_file(filepath: Path) -> list[str]:
        """Search a single file for pattern matches (sync function)."""
        file_results = []
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines(keepends=True)
        except Exception:
            return file_results

        for i, line in enumerate(lines):
            if compiled_pattern.search(line):
                line_num = i + 1
                content = line.rstrip("\n")
                file_results.append(f"  {line_num}: {content}")

                # Add context after
                for j in range(1, context_after + 1):
                    if i + j < len(lines):
                        file_results.append(
                            f"  {line_num + j}: {lines[i + j].rstrip()}"
                        )

        return file_results

    def process_directory() -> list[str]:
        """Process all files in directory (runs in executor)."""
        search_pattern = str(path / "**" / file_filter)
        files = [
            f for f in glob.glob(search_pattern, recursive=True) if Path(f).is_file()
        ]

        all_results = []
        for filepath in files[:max_files]:
            file_results = search_file(Path(filepath))
            if file_results:
                rel_path = Path(filepath).relative_to(path)
                all_results.append(f"{rel_path}:")
                all_results.extend(file_results)
                if len(all_results) >= max_matches:
                    return all_results[:max_matches]
        return all_results

    loop = asyncio.get_running_loop()
    try:
        results = await loop.run_in_executor(None, process_directory)
    except Exception as e:
        logger.error("Error during grep: %s", e)
        return f"Error during grep: {e}"

    if not results:
        return f"No matches found for '{pattern}' in {display_path}"

    output = "\n".join(results)
    if len(results) >= max_matches:
        output += f"\n... (max {max_matches} matches reached)"
    return output


async def execute_edit(args: dict[str, Any]) -> str:
    """Replace a unique string in a file.

    The old_string must appear exactly once in the file.
    Returns JSON string with diff data for UI rendering.

    Args:
        args: {
            "path": str,
            "old_string": str,
            "new_string": str
        }

    Returns:
        JSON string with structure:
        {
            "success": bool,
            "path": str,           # relative path for display
            "old_lines": [str],    # original lines that were replaced
            "new_lines": [str],    # new lines
            "start_line": int,     # 1-based line number where change starts
            "context_before": [str],  # 3 lines before change
            "context_after": [str],   # 3 lines after change
            "error": str | None
        }
    """
    path = Path(args["path"]).expanduser().resolve()
    display_path = _relative_path(path)
    old_string = args["old_string"]
    new_string = args["new_string"]

    if not path.is_file():
        return json.dumps(
            {"success": False, "error": f"File not found: {display_path}"}
        )

    try:
        content = path.read_text(encoding="utf-8")
    except PermissionError:
        return json.dumps(
            {"success": False, "error": f"Permission denied: {display_path}"}
        )
    except Exception as e:
        return json.dumps({"success": False, "error": f"Error reading file: {e}"})

    count = content.count(old_string)
    if count == 0:
        return json.dumps(
            {"success": False, "error": f"String not found in {display_path}"}
        )
    if count > 1:
        return json.dumps(
            {
                "success": False,
                "error": f"String found {count} times in {display_path}. "
                f"Provide a more specific string with surrounding context.",
            }
        )

    lines = content.splitlines(keepends=True)
    char_pos = content.index(old_string)

    start_line = 1
    current_pos = 0
    for i, line in enumerate(lines):
        if current_pos + len(line) > char_pos:
            start_line = i + 1
            break
        current_pos += len(line)

    old_lines = old_string.splitlines()
    end_line = start_line + len(old_lines) - 1

    context_size = 3
    context_before_start = max(0, start_line - 1 - context_size)
    context_after_end = min(len(lines), end_line + context_size)

    context_before = [
        line.rstrip("\n\r") for line in lines[context_before_start : start_line - 1]
    ]
    context_after = [line.rstrip("\n\r") for line in lines[end_line:context_after_end]]

    new_content = content.replace(old_string, new_string)

    try:
        path.write_text(new_content, encoding="utf-8")
    except Exception as e:
        return json.dumps({"success": False, "error": f"Error writing file: {e}"})

    new_lines = new_string.splitlines() if new_string else [""]

    logger.debug(
        "Edited %s: replaced %d lines at line %d",
        display_path,
        len(old_lines),
        start_line,
    )

    return json.dumps(
        {
            "success": True,
            "path": str(display_path),
            "old_lines": old_lines,
            "new_lines": new_lines,
            "start_line": start_line,
            "context_before": context_before,
            "context_after": context_after,
            "error": None,
        }
    )


async def execute_web_search(args: dict[str, Any]) -> str:
    """Search the web using DuckDuckGo HTML."""
    import urllib.parse
    import urllib.request

    query = args["query"]
    logger.debug("Web search: %s", query)

    encoded = urllib.parse.urlencode({"q": query})
    url = f"https://html.duckduckgo.com/html/?{encoded}"

    def parse_dduckgo_html(html: str) -> list[tuple[str, str]]:
        """Parse DuckDuckGo HTML results with multiple pattern attempts."""
        results = []

        # Try the primary pattern first
        pattern = r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>'
        for match in re.finditer(pattern, html, re.DOTALL):
            href = match.group(1)
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            if href and title:
                results.append((title, href))

        # If no results, try alternative pattern (different HTML structure)
        if not results:
            pattern = (
                r'<a[^>]+href="([^"]*)"[^>]*class="[^"]*result[^"]*"[^>]*>(.*?)</a>'
            )
            for match in re.finditer(pattern, html, re.DOTALL):
                href = match.group(1)
                title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
                if href and title and len(title) > 2:
                    results.append((title, href))

        # Final fallback: try to find any result link
        if not results:
            pattern = r'<a[^>]+href="(https?://[^"]+)"[^>]*>([^<]+)</a>'
            seen = set()
            for match in re.finditer(pattern, html):
                href = match.group(1)
                title = match.group(2).strip()
                if href.startswith("http") and title and href not in seen:
                    seen.add(href)
                    results.append((title, href))

        return results

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Artifice/1.0"})
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: urllib.request.urlopen(req, timeout=15),  # noqa: S310
        )
        html = response.read().decode("utf-8", errors="replace")

        results = parse_dduckgo_html(html)

        if not results:
            logger.debug("No search results for: %s", query)
            return f"No results found for '{query}'"

        logger.debug("Found %d search results for: %s", len(results), query)
        formatted = [f"- {title}\n  {href}" for title, href in results[:10]]
        return f"Search results for '{query}':\n\n" + "\n\n".join(formatted)
    except Exception as e:
        logger.error("Error searching web for '%s': %s", query, e)
        return f"Error searching: {e}"
