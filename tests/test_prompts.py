"""Tests for prompt template loading."""

from pathlib import Path


from artifice.prompts import list_prompts, load_prompt, fuzzy_match, get_prompt_dirs


class TestFuzzyMatch:
    def test_exact_match(self):
        assert fuzzy_match("hello", "hello")

    def test_subsequence(self):
        assert fuzzy_match("hlo", "hello")

    def test_no_match(self):
        assert not fuzzy_match("xyz", "hello")

    def test_empty_query(self):
        assert fuzzy_match("", "anything")

    def test_case_insensitive(self):
        assert fuzzy_match("HLO", "hello")

    def test_query_longer_than_name(self):
        assert not fuzzy_match("abcdef", "abc")


class TestPromptDirs:
    def test_returns_local_and_home(self, tmp_path, monkeypatch):
        local_dir = tmp_path / "project" / ".artifice" / "prompts"
        local_dir.mkdir(parents=True)
        home_dir = tmp_path / "home" / ".artifice" / "prompts"
        home_dir.mkdir(parents=True)

        monkeypatch.setattr(Path, "cwd", lambda: tmp_path / "project")
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        dirs = get_prompt_dirs()
        assert local_dir in dirs
        assert home_dir in dirs
        # Local should come first
        assert dirs.index(local_dir) < dirs.index(home_dir)

    def test_missing_dirs_excluded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "cwd", lambda: tmp_path / "nonexistent")
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "nonexistent")

        dirs = get_prompt_dirs()
        assert dirs == []


class TestListPrompts:
    def test_lists_md_files(self, tmp_path, monkeypatch):
        prompt_dir = tmp_path / ".artifice" / "prompts"
        prompt_dir.mkdir(parents=True)
        (prompt_dir / "fix-bug.md").write_text("Fix the bug")
        (prompt_dir / "add-tests.md").write_text("Add tests")

        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "nohome")

        prompts = list_prompts()
        assert "fix-bug" in prompts
        assert "add-tests" in prompts

    def test_finds_in_subdirectories(self, tmp_path, monkeypatch):
        prompt_dir = tmp_path / ".artifice" / "prompts"
        sub_dir = prompt_dir / "system"
        sub_dir.mkdir(parents=True)
        (sub_dir / "cli-helper.md").write_text("Help with CLI")

        monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "nohome")

        prompts = list_prompts()
        assert "system/cli-helper" in prompts

    def test_local_overrides_home(self, tmp_path, monkeypatch):
        local_dir = tmp_path / "project" / ".artifice" / "prompts"
        local_dir.mkdir(parents=True)
        (local_dir / "shared.md").write_text("local version")

        home_dir = tmp_path / "home" / ".artifice" / "prompts"
        home_dir.mkdir(parents=True)
        (home_dir / "shared.md").write_text("home version")

        monkeypatch.setattr(Path, "cwd", lambda: tmp_path / "project")
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

        prompts = list_prompts()
        assert prompts["shared"] == local_dir / "shared.md"

