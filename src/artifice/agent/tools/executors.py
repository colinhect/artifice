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
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

async def execute_read(args: dict[str, Any]) -> str:
    """Read file contents, optionally with offset and limit."""
    path = Path(args["path"]).expanduser().resolve()
    offset = args.get("offset", 0)
    limit = args.get("limit")

    logger.debug("Reading file: %s (offset=%d, limit=%s)", path, offset, limit)

    if not path.is_file():
        logger.warning("File not found: %s", path)
        return f"Error: File not found: {path}"

    try:
        content = path.read_text(encoding="utf-8")
    except PermissionError:
        logger.warning("Permission denied: %s", path)
        return f"Error: Permission denied: {path}"
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
    """Write content to a file, creating directories as needed."""
    path = Path(args["path"]).expanduser().resolve()
    content = args["content"]

    logger.debug("Writing %d bytes to: %s", len(content), path)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.debug("Successfully wrote to: %s", path)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        logger.error("Error writing file %s: %s", path, e)
        return f"Error writing file: {e}"


async def execute_glob(args: dict[str, Any]) -> str:
    """Search for files matching a glob pattern."""
    pattern = args["pattern"]
    path = Path(args.get("path", ".")).expanduser().resolve()

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
    path = Path(args.get("path", ".")).expanduser().resolve()
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
        files = [f for f in glob.glob(search_pattern, recursive=True) if Path(f).is_file()]

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
        return f"No matches found for '{pattern}' in {path}"

    output = "\n".join(results)
    if len(results) >= max_matches:
        output += f"\n... (max {max_matches} matches reached)"
    return output


async def execute_replace(args: dict[str, Any]) -> str:
    """Replace string occurrences in files with regex support."""
    path = Path(args["path"]).expanduser().resolve()
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

    if not path.is_file():
        return f"Error: File not found: {path}"

    try:
        original_content = path.read_text(encoding="utf-8")
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
        # Generate a more accurate diff using line-by-line comparison
        # with match position information
        diff_lines = []

        # Find all match positions in original content
        matches = list(compiled_pattern.finditer(original_content))

        if matches:
            # Build a simple unified-style diff
            diff_lines.append(f"DRY RUN: {count} replacement(s) would be made to {path}:")
            diff_lines.append("")

            # Show context around each match
            for idx, match in enumerate(matches[:10]):  # Limit to first 10 matches
                start_pos = match.start()
                end_pos = match.end()

                # Get context around the match
                context_start = max(0, start_pos - 30)
                context_end = min(len(original_content), end_pos + 30)

                before = original_content[context_start:start_pos]
                matched = original_content[start_pos:end_pos]
                after = original_content[end_pos:context_end]

                diff_lines.append(f"  Match {idx + 1} at position {start_pos}:")
                diff_lines.append(f"    - {repr(before)}{repr(matched)}{repr(after)}")
                diff_lines.append(f"    + {repr(before)}{repr(replacement)}{repr(after)}")
                diff_lines.append("")

            if count > 10:
                diff_lines.append(f"  ... and {count - 10} more replacement(s)")

        return "\n".join(diff_lines)

    try:
        path.write_text(new_content, encoding="utf-8")
        logger.debug("Replaced %d occurrences in: %s", count, path)
        return f"Replaced {count} occurrence(s) in {path}"
    except Exception as e:
        logger.error("Error writing file %s: %s", path, e)
        return f"Error writing file: {e}"


async def execute_web_fetch(args: dict[str, Any]) -> str:
    """Fetch contents of a URL."""
    import urllib.request

    url = args["url"]

    # Validate URL
    try:
        parsed = urlparse(url)
        if not parsed.scheme or parsed.scheme not in ("http", "https"):
            return f"Error: Invalid URL scheme '{parsed.scheme}'. Only http and https are supported."
        if not parsed.netloc:
            return f"Error: Invalid URL: missing network location (domain)."
    except Exception as e:
        return f"Error: Invalid URL: {e}"

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
            pattern = r'<a[^>]+href="([^"]*)"[^>]*class="[^"]*result[^"]*"[^>]*>(.*?)</a>'
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

