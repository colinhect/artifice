"""Tests for History - command history with multi-mode navigation and persistence."""

import json
from artifice.history import History


class TestHistoryAdd:
    def test_add_python(self, tmp_history_file):
        h = History(history_file=tmp_history_file)
        h.add("print('hello')", "python")
        assert h._python_history == ["print('hello')"]
        assert h._ai_history == []
        assert h._shell_history == []

    def test_add_ai(self, tmp_history_file):
        h = History(history_file=tmp_history_file)
        h.add("explain this code", "ai")
        assert h._ai_history == ["explain this code"]

    def test_add_shell(self, tmp_history_file):
        h = History(history_file=tmp_history_file)
        h.add("ls -la", "shell")
        assert h._shell_history == ["ls -la"]

    def test_max_size_enforcement(self, tmp_history_file):
        h = History(history_file=tmp_history_file, max_history_size=3)
        for i in range(5):
            h.add(f"cmd{i}", "python")
        assert len(h._python_history) == 3
        assert h._python_history == ["cmd2", "cmd3", "cmd4"]

    def test_add_resets_navigation_index(self, tmp_history_file):
        h = History(history_file=tmp_history_file)
        h.add("cmd1", "python")
        h.navigate_back("python", "")
        assert h._python_history_index != -1
        h.add("cmd2", "python")
        assert h._python_history_index == -1


class TestNavigateBack:
    def test_empty_history_returns_none(self, tmp_history_file):
        h = History(history_file=tmp_history_file)
        assert h.navigate_back("python", "current") is None

    def test_navigates_to_last_entry(self, tmp_history_file):
        h = History(history_file=tmp_history_file)
        h.add("first", "python")
        h.add("second", "python")
        result = h.navigate_back("python", "current_text")
        assert result == "second"

    def test_navigates_further_back(self, tmp_history_file):
        h = History(history_file=tmp_history_file)
        h.add("first", "python")
        h.add("second", "python")
        h.navigate_back("python", "current")
        result = h.navigate_back("python", "")
        assert result == "first"

    def test_stops_at_beginning(self, tmp_history_file):
        h = History(history_file=tmp_history_file)
        h.add("only", "python")
        h.navigate_back("python", "cur")
        result = h.navigate_back("python", "")
        assert result is None  # Already at the oldest entry

    def test_saves_current_input_on_first_back(self, tmp_history_file):
        h = History(history_file=tmp_history_file)
        h.add("old", "python")
        h.navigate_back("python", "my typing")
        assert h._current_input["python"] == "my typing"

    def test_modes_are_independent(self, tmp_history_file):
        h = History(history_file=tmp_history_file)
        h.add("python_cmd", "python")
        h.add("ai_prompt", "ai")
        h.add("shell_cmd", "shell")

        assert h.navigate_back("python", "") == "python_cmd"
        assert h.navigate_back("ai", "") == "ai_prompt"
        assert h.navigate_back("shell", "") == "shell_cmd"


class TestNavigateForward:
    def test_not_browsing_returns_none(self, tmp_history_file):
        h = History(history_file=tmp_history_file)
        h.add("cmd", "python")
        assert h.navigate_forward("python") is None

    def test_forward_returns_to_current_input(self, tmp_history_file):
        h = History(history_file=tmp_history_file)
        h.add("old", "python")
        h.navigate_back("python", "my_input")
        result = h.navigate_forward("python")
        assert result == "my_input"

    def test_forward_through_entries(self, tmp_history_file):
        h = History(history_file=tmp_history_file)
        h.add("first", "python")
        h.add("second", "python")
        h.add("third", "python")
        # Go all the way back
        h.navigate_back("python", "current")  # -> third
        h.navigate_back("python", "")  # -> second
        h.navigate_back("python", "")  # -> first
        # Now forward
        assert h.navigate_forward("python") == "second"
        assert h.navigate_forward("python") == "third"
        assert h.navigate_forward("python") == "current"  # restored input

    def test_back_and_forward_roundtrip(self, tmp_history_file):
        h = History(history_file=tmp_history_file)
        h.add("a", "ai")
        h.add("b", "ai")
        h.navigate_back("ai", "typing")  # -> b
        h.navigate_back("ai", "")  # -> a
        h.navigate_forward("ai")  # -> b
        h.navigate_forward("ai")  # -> typing
        result = h.navigate_forward("ai")
        assert result is None  # No longer browsing


class TestPersistence:
    def test_save_and_load(self, tmp_history_file):
        h = History(history_file=tmp_history_file)
        h.add("py_cmd", "python")
        h.add("ai_cmd", "ai")
        h.add("sh_cmd", "shell")
        h.save()

        h2 = History(history_file=tmp_history_file)
        assert h2._python_history == ["py_cmd"]
        assert h2._ai_history == ["ai_cmd"]
        assert h2._shell_history == ["sh_cmd"]

    def test_load_corrupted_json(self, tmp_history_file):
        with open(tmp_history_file, "w") as f:
            f.write("{invalid json!!!")

        h = History(history_file=tmp_history_file)
        assert h._python_history == []
        assert h._ai_history == []

    def test_load_nonexistent_file(self, tmp_path):
        h = History(history_file=tmp_path / "does_not_exist.json")
        assert h._python_history == []

    def test_save_respects_max_size(self, tmp_history_file):
        h = History(history_file=tmp_history_file, max_history_size=2)
        for i in range(5):
            h.add(f"cmd{i}", "python")
        h.save()

        with open(tmp_history_file) as f:
            data = json.load(f)
        assert len(data["python"]) == 2

    def test_save_sets_restrictive_permissions(self, tmp_history_file):
        h = History(history_file=tmp_history_file)
        h.add("secret", "python")
        h.save()
        mode = tmp_history_file.stat().st_mode & 0o777
        assert mode == 0o600


class TestClear:
    def test_clear_empties_all(self, tmp_history_file):
        h = History(history_file=tmp_history_file)
        h.add("py", "python")
        h.add("ai", "ai")
        h.add("sh", "shell")
        h.clear()
        assert h._python_history == []
        assert h._ai_history == []
        assert h._shell_history == []
        assert h._python_history_index == -1
        assert h._ai_history_index == -1
        assert h._shell_history_index == -1
