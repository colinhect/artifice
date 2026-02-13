"""Tests for ANSI escape code parsing and conversion."""

import pytest
from artifice.ansi_handler import (
    strip_ansi, ansi_to_textual, has_ansi_codes, _parse_sgr_codes,
)


class TestStripAnsi:
    def test_no_codes(self):
        assert strip_ansi("hello world") == "hello world"

    def test_strips_color(self):
        assert strip_ansi("\x1b[31mred text\x1b[0m") == "red text"

    def test_strips_multiple_codes(self):
        text = "\x1b[1m\x1b[32mbold green\x1b[0m normal"
        assert strip_ansi(text) == "bold green normal"

    def test_strips_256_color(self):
        assert strip_ansi("\x1b[38;5;196mtext\x1b[0m") == "text"

    def test_strips_rgb_color(self):
        assert strip_ansi("\x1b[38;2;255;128;0mtext\x1b[0m") == "text"

    def test_preserves_newlines(self):
        assert strip_ansi("\x1b[31mline1\nline2\x1b[0m") == "line1\nline2"

    def test_empty_string(self):
        assert strip_ansi("") == ""


class TestHasAnsiCodes:
    def test_plain_text(self):
        assert not has_ansi_codes("hello")

    def test_with_color(self):
        assert has_ansi_codes("\x1b[31mred\x1b[0m")

    def test_partial_escape(self):
        # Just ESC without [ is not an ANSI CSI sequence
        assert not has_ansi_codes("\x1bno bracket")


class TestAnsiToTextualBasicColors:
    def test_red_foreground(self):
        result = ansi_to_textual("\x1b[31mhello\x1b[0m")
        assert "[red]" in result
        assert "hello" in result
        assert "[/]" in result

    def test_green_foreground(self):
        result = ansi_to_textual("\x1b[32mtext\x1b[0m")
        assert "[green]" in result

    def test_blue_background(self):
        result = ansi_to_textual("\x1b[44mtext\x1b[0m")
        assert "[on blue]" in result

    def test_bright_yellow(self):
        result = ansi_to_textual("\x1b[93mtext\x1b[0m")
        assert "[bright_yellow]" in result

    def test_bright_background(self):
        result = ansi_to_textual("\x1b[101mtext\x1b[0m")
        assert "[on bright_red]" in result


class TestAnsiToTextualStyles:
    def test_bold(self):
        result = ansi_to_textual("\x1b[1mtext\x1b[0m")
        assert "[bold]" in result

    def test_italic(self):
        result = ansi_to_textual("\x1b[3mtext\x1b[0m")
        assert "[italic]" in result

    def test_underline(self):
        result = ansi_to_textual("\x1b[4mtext\x1b[0m")
        assert "[underline]" in result

    def test_strikethrough(self):
        result = ansi_to_textual("\x1b[9mtext\x1b[0m")
        assert "[strike]" in result

    def test_combined_bold_and_color(self):
        result = ansi_to_textual("\x1b[1;31mtext\x1b[0m")
        assert "[bold]" in result
        assert "[red]" in result


class TestAnsiToTextualExtendedColors:
    def test_256_foreground(self):
        result = ansi_to_textual("\x1b[38;5;196mtext\x1b[0m")
        assert "[color(196)]" in result

    def test_256_background(self):
        result = ansi_to_textual("\x1b[48;5;22mtext\x1b[0m")
        assert "[on color(22)]" in result

    def test_rgb_foreground(self):
        result = ansi_to_textual("\x1b[38;2;255;128;0mtext\x1b[0m")
        assert "[rgb(255,128,0)]" in result

    def test_rgb_background(self):
        result = ansi_to_textual("\x1b[48;2;10;20;30mtext\x1b[0m")
        assert "[on rgb(10,20,30)]" in result


class TestAnsiToTextualReset:
    def test_reset_closes_styles(self):
        result = ansi_to_textual("\x1b[31mred\x1b[0m normal")
        assert "[/]" in result
        assert "normal" in result

    def test_empty_params_reset(self):
        """ESC[m (no params) should act as reset."""
        result = ansi_to_textual("\x1b[31mred\x1b[m normal")
        assert "[/]" in result

    def test_specific_attribute_reset(self):
        """Codes like 39 (default fg) should reset."""
        result = ansi_to_textual("\x1b[31mred\x1b[39m default")
        assert "[/]" in result


class TestAnsiToTextualEdgeCases:
    def test_no_codes_fast_path(self):
        result = ansi_to_textual("plain text")
        assert result == "plain text"

    def test_carriage_return_handling(self):
        result = ansi_to_textual("line1\r\nline2")
        assert result == "line1\nline2"

    def test_lone_carriage_return(self):
        result = ansi_to_textual("overwrite\rthis")
        assert result == "overwrite\nthis"

    def test_non_sgr_codes_ignored(self):
        """Non-m commands (like cursor movement) should be stripped."""
        # ESC[2J is clear screen - not an SGR code
        result = ansi_to_textual("\x1b[2Jtext")
        assert "text" in result
        assert "\x1b" not in result

    def test_multiple_sequences_in_one_string(self):
        text = "\x1b[31mred \x1b[32mgreen \x1b[0mnormal"
        result = ansi_to_textual(text)
        assert "[red]" in result
        assert "[green]" in result
        assert "normal" in result

    def test_text_between_sequences_preserved(self):
        result = ansi_to_textual("before\x1b[31mred\x1b[0mafter")
        assert "before" in result
        assert "red" in result
        assert "after" in result


class TestParseSgrCodes:
    def test_reset_code(self):
        styles = ["color"]
        result = _parse_sgr_codes([0], styles)
        assert "[/]" in result
        assert len(styles) == 0

    def test_reset_with_no_active_styles(self):
        styles = []
        result = _parse_sgr_codes([0], styles)
        assert result == ""

    def test_multiple_codes_in_sequence(self):
        styles = []
        result = _parse_sgr_codes([1, 31], styles)
        assert "[bold]" in result
        assert "[red]" in result
