"""ANSI escape code handling for terminal color output.

This module provides utilities to parse ANSI escape sequences and convert them
to Textual markup for rich terminal output display.
"""

import re
from typing import List, Tuple

# ANSI SGR (Select Graphic Rendition) codes for basic colors
ANSI_BASIC_COLORS = {
    # Foreground colors (30-37)
    30: "black",
    31: "red",
    32: "green",
    33: "yellow",
    34: "blue",
    35: "magenta",
    36: "cyan",
    37: "white",
    # Bright foreground colors (90-97)
    90: "bright_black",
    91: "bright_red",
    92: "bright_green",
    93: "bright_yellow",
    94: "bright_blue",
    95: "bright_magenta",
    96: "bright_cyan",
    97: "bright_white",
}

ANSI_BASIC_BG_COLORS = {
    # Background colors (40-47)
    40: "on black",
    41: "on red",
    42: "on green",
    43: "on yellow",
    44: "on blue",
    45: "on magenta",
    46: "on cyan",
    47: "on white",
    # Bright background colors (100-107)
    100: "on bright_black",
    101: "on bright_red",
    102: "on bright_green",
    103: "on bright_yellow",
    104: "on bright_blue",
    105: "on bright_magenta",
    106: "on bright_cyan",
    107: "on bright_white",
}

ANSI_STYLES = {
    1: "bold",
    2: "dim",
    3: "italic",
    4: "underline",
    7: "reverse",
    9: "strike",
}

# Pattern to match ANSI escape sequences
ANSI_ESCAPE_PATTERN = re.compile(
    r'\x1b\['  # ESC [
    r'([0-9;]*)'  # parameter bytes
    r'([A-Za-z])'  # final byte
)


def strip_ansi(text: str) -> str:
    """Remove all ANSI escape codes from text.
    
    Args:
        text: Text potentially containing ANSI escape codes
        
    Returns:
        Text with all ANSI codes removed
    """
    return ANSI_ESCAPE_PATTERN.sub('', text)


def ansi_to_textual(text: str) -> str:
    """Convert ANSI escape codes to Textual markup.
    
    This function parses ANSI SGR (Select Graphic Rendition) codes and converts
    them to Textual's markup syntax for rich text display.
    
    Args:
        text: Text containing ANSI escape codes
        
    Returns:
        Text with ANSI codes converted to Textual markup
    """
    # Remove carriage returns (common in PTY output)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    if '\x1b[' not in text:
        # Fast path: no ANSI codes present
        return text
    
    result = []
    pos = 0
    active_styles: List[str] = []
    
    for match in ANSI_ESCAPE_PATTERN.finditer(text):
        # Add text before this escape code
        if match.start() > pos:
            result.append(text[pos:match.start()])
        
        params = match.group(1)
        command = match.group(2)
        
        # Only handle SGR (Select Graphic Rendition) commands
        if command in ('m', 'M'):
            if not params:
                # Reset
                if active_styles:
                    result.append('[/]')
                    active_styles.clear()
            else:
                codes = [int(x) if x else 0 for x in params.split(';')]
                new_markup = _parse_sgr_codes(codes, active_styles)
                if new_markup:
                    result.append(new_markup)
        
        pos = match.end()
    
    # Add remaining text
    if pos < len(text):
        result.append(text[pos:])
    
    return ''.join(result)


def _parse_sgr_codes(codes: List[int], active_styles: List[str]) -> str:
    """Parse SGR codes and generate Textual markup.
    
    Args:
        codes: List of SGR parameter codes
        active_styles: Current active style stack (modified in place)
        
    Returns:
        Textual markup string to apply these codes
    """
    markup_parts = []
    i = 0
    
    while i < len(codes):
        code = codes[i]
        
        if code == 0:
            # Reset all
            if active_styles:
                markup_parts.append('[/]')
                active_styles.clear()
        
        elif code in ANSI_BASIC_COLORS:
            # Foreground color
            color = ANSI_BASIC_COLORS[code]
            markup_parts.append(f'[{color}]')
            active_styles.append('color')
        
        elif code in ANSI_BASIC_BG_COLORS:
            # Background color
            color = ANSI_BASIC_BG_COLORS[code]
            markup_parts.append(f'[{color}]')
            active_styles.append('bgcolor')
        
        elif code in ANSI_STYLES:
            # Text style (bold, italic, etc.)
            style = ANSI_STYLES[code]
            markup_parts.append(f'[{style}]')
            active_styles.append('style')
        
        elif code == 38 and i + 2 < len(codes):
            # Extended foreground color
            if codes[i + 1] == 5 and i + 2 < len(codes):
                # 256-color mode: ESC[38;5;Nm
                color_idx = codes[i + 2]
                markup_parts.append(f'[color({color_idx})]')
                active_styles.append('color')
                i += 2
            elif codes[i + 1] == 2 and i + 4 < len(codes):
                # RGB mode: ESC[38;2;R;G;Bm
                r, g, b = codes[i + 2], codes[i + 3], codes[i + 4]
                markup_parts.append(f'[rgb({r},{g},{b})]')
                active_styles.append('color')
                i += 4
        
        elif code == 48 and i + 2 < len(codes):
            # Extended background color
            if codes[i + 1] == 5 and i + 2 < len(codes):
                # 256-color mode: ESC[48;5;Nm
                color_idx = codes[i + 2]
                markup_parts.append(f'[on color({color_idx})]')
                active_styles.append('bgcolor')
                i += 2
            elif codes[i + 1] == 2 and i + 4 < len(codes):
                # RGB mode: ESC[48;2;R;G;Bm
                r, g, b = codes[i + 2], codes[i + 3], codes[i + 4]
                markup_parts.append(f'[on rgb({r},{g},{b})]')
                active_styles.append('bgcolor')
                i += 4
        
        elif code in (39, 49, 22, 23, 24, 27, 29):
            # Reset specific attributes
            if active_styles:
                markup_parts.append('[/]')
                active_styles.clear()
        
        i += 1
    
    return ''.join(markup_parts)


def has_ansi_codes(text: str) -> bool:
    """Check if text contains ANSI escape codes.
    
    Args:
        text: Text to check
        
    Returns:
        True if text contains ANSI escape codes
    """
    return '\x1b[' in text
