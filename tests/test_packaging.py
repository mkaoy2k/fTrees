"""Packaging, license, and container-file checks."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_INSTRUCTIONS = {
    "FROM",
    "ARG",
    "WORKDIR",
    "RUN",
    "COPY",
    "ADD",
    "ENV",
    "USER",
    "EXPOSE",
    "VOLUME",
    "LABEL",
    "HEALTHCHECK",
    "CMD",
    "ENTRYPOINT",
    "SHELL",
    "STOPSIGNAL",
}


def _dockerfile_commands(text):
    """Logical Dockerfile instructions, with backslash continuations joined."""
    logical = []
    buffer = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not buffer and (not stripped or stripped.startswith("#")):
            continue
        if stripped.endswith("\\"):
            buffer += stripped[:-1].strip() + " "
            continue
        buffer += stripped
        logical.append(buffer.strip())
        buffer = ""
    if buffer:
        raise ValueError("Dockerfile has a dangling continuation")
    commands = []
    for line in logical:
        name, _, rest = line.partition(" ")
        commands.append((name, rest.strip()))
    return commands


def _direct_lock_names(text):
    """Packages the lock installs because the ftrees project depends on them."""
    names = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line or line.startswith("#") or line.startswith(" "):
            continue
        name = line.split("==", 1)[0].split("[", 1)[0].strip().lower()
        notes = []
        cursor = index + 1
        while cursor < len(lines) and lines[cursor].startswith(" "):
            notes.append(lines[cursor])
            cursor += 1
        if any("ftrees" in note for note in notes):
            names.append(name)
    return names


class PackagingTests(unittest.TestCase):
    def test_lockfile_drops_numpy_and_adds_graphviz(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        direct_section = pyproject.split("[tool.uv]", 1)[0].lower()
        self.assertNotIn("numpy", direct_section)
        self.assertIn("graphviz>=", direct_section)
        self.assertTrue((ROOT / "uv.lock").is_file())
        locked = _direct_lock_names((ROOT / "requirements.txt").read_text(encoding="utf-8"))
        self.assertIn("graphviz", locked)
        self.assertIn("pandas", locked)
        self.assertIn("streamlit", locked)
        self.assertNotIn("numpy", locked)
        environment = (ROOT / "environment.yaml").read_text(encoding="utf-8")
        self.assertNotIn("/Users/", environment)
        self.assertIn("requirements.txt", environment)
        self.assertIn("python=3.12", environment)

    def test_license_is_mit(self):
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(license_text.startswith("MIT License"))
        self.assertIn("Copyright (c) 2026 Michael Kao", license_text)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("streamlit run ftpe.py", readme)
        self.assertIn("data/family.db", readme)
        self.assertIn("in place", readme)
        self.assertIn("family.db.bak", readme)
        self.assertIn("https://github.com/mkaoy2k/fTrees.git", readme)
        self.assertIn("python -m unittest discover -s tests -t . -v", readme)

    def test_dockerfile_syntax_volume_headless_and_healthcheck(self):
        text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        commands = _dockerfile_commands(text)
        names = [name for name, _rest in commands]
        unknown = [name for name in names if name not in _INSTRUCTIONS]
        self.assertEqual(unknown, [])
        self.assertEqual(names[0], "FROM")
        self.assertIn("VOLUME", names)
        self.assertIn("HEALTHCHECK", names)
        self.assertIn("CMD", names)
        volume = next(rest for name, rest in commands if name == "VOLUME")
        self.assertEqual(json.loads(volume), ["/fts/data"])
        health = next(rest for name, rest in commands if name == "HEALTHCHECK")
        self.assertIn("_stcore/health", health)
        payload = health.split("CMD", 1)[1].strip()
        self.assertIsInstance(json.loads(payload), list)
        command = next(rest for name, rest in commands if name == "CMD")
        self.assertIn("--server.headless=true", command)
        self.assertIsInstance(json.loads(command), list)
        self.assertIn("STREAMLIT_SERVER_HEADLESS=true", text)
        self.assertIn("uid 1000", text)
        ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        self.assertIn(".env", ignore)
        self.assertIn("data/*.db", ignore)
