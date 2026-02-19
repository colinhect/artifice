from __future__ import annotations

from textual.theme import Theme


def create_artifice_theme() -> Theme:
    # black = "#07080A"
    dark_gray = "#3B4252"
    gray = "#434C5E"
    # light_gray = "#4C566A"
    # light_gray_bright = "#616E88"
    # darkest_white = "#D8DEE9"
    # darker_white = "#E5E9F0"
    white = "#ECEFF4"
    teal = "#8FBCBB"
    # off_blue = "#88C0D0"
    glacier = "#81A1C1"
    blue = "#5E81AC"
    red = "#BF616A"
    # orange = "#D08770"
    # yellow = "#EBCB8B"
    green = "#A3BE8C"
    # purple = "#B48EAD"
    # none = "NONE"

    return Theme(
        name="artifice",
        primary=blue,
        secondary=green,
        accent=teal,
        foreground=white,
        # background=black,
        success=green,
        warning=glacier,
        error=red,
        surface=dark_gray,
        panel=gray,
        dark=True,
    )
