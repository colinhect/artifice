"""Theme configuration for Artifice."""

from __future__ import annotations

from textual.theme import Theme


def create_artifice_theme() -> Theme:
    """Create the Artifice color theme based on Nord color palette.

    Nord palette reference: https://www.nordtheme.com/docs/colors-and-palettes

    Color groups:
    - Polar Night: Deep dark blues/blacks for backgrounds
    - Snow Storm: Light grays/whites for foregrounds
    - Frost: Bright blues for accents and primary actions
    - Aurora: Semantic colors (red, orange, yellow, green, purple)
    """
    polar_night_0 = "#2E3440"
    polar_night_1 = "#3B4252"
    polar_night_2 = "#434C5E"
    polar_night_3 = "#4C566A"

    snow_storm_0 = "#D8DEE9"
    snow_storm_1 = "#E5E9F0"
    snow_storm_2 = "#ECEFF4"

    frost_0 = "#8FBCBB"
    frost_1 = "#88C0D0"
    frost_2 = "#81A1C1"
    frost_3 = "#5E81AC"

    aurora_0 = "#BF616A"
    aurora_1 = "#D08770"
    aurora_2 = "#EBCB8B"
    aurora_3 = "#A3BE8C"
    aurora_4 = "#B48EAD"

    return Theme(
        name="artifice",
        primary=frost_3,
        secondary=aurora_3,
        accent=frost_0,
        foreground=snow_storm_2,
        #background=polar_night_0,
        success=aurora_3,
        warning=frost_2,
        error=aurora_0,
        surface=polar_night_1,
        panel=polar_night_2,
        boost="white",
        dark=True,
        variables={
            "polar-night-0": polar_night_0,
            "polar-night-1": polar_night_1,
            "polar-night-2": polar_night_2,
            "polar-night-3": polar_night_3,
            "snow-storm-0": snow_storm_0,
            "snow-storm-1": snow_storm_1,
            "snow-storm-2": snow_storm_2,
            "frost-0": frost_0,
            "frost-1": frost_1,
            "frost-2": frost_2,
            "frost-3": frost_3,
            "aurora-red": aurora_0,
            "aurora-orange": aurora_1,
            "aurora-yellow": aurora_2,
            "aurora-green": aurora_3,
            "aurora-purple": aurora_4,
        },
    )
