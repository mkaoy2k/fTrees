"""Paths the CSV and JSON editors are allowed to open.

Both editors read and write only a file that sits directly in the data
directory. A new name must be a single file name: separators, parent
segments, and links that resolve outside that directory are rejected.
"""
from pathlib import Path


def data_directory(app_root) -> Path:
    """Real ``data`` directory under ``app_root``.

    A ``data`` path that is itself a link is rejected so the editors cannot
    be pointed at another folder by swapping that directory.
    """
    root = Path(app_root).resolve()
    data = root / "data"
    if data.is_symlink():
        raise ValueError("data directory must not be a link")
    data.mkdir(parents=True, exist_ok=True)
    resolved = data.resolve()
    if resolved.parent != root:
        raise ValueError("data directory must not be a link")
    return resolved


def sanitized_filename(raw, suffix: str) -> str:
    """Return a single file name ending with ``suffix``, or raise ValueError."""
    if not isinstance(raw, str) or "\x00" in raw:
        raise ValueError("file name is not allowed")
    suffix = suffix if str(suffix).startswith(".") else f".{suffix}"
    suffix = suffix.lower()
    name = raw.strip().replace("\\", "/")
    if not name or "/" in name or name != Path(name).name:
        raise ValueError("file name is not allowed")
    if not name.lower().endswith(suffix):
        name += suffix
    if name.startswith(".") or name in {".", "..", suffix}:
        raise ValueError("file name is not allowed")
    if len(name) > 120 or not name[0].isalnum():
        raise ValueError("file name is not allowed")
    for char in name:
        if char.isalnum() or char in " ._-":
            continue
        raise ValueError("file name is not allowed")
    return name


def path_inside(data_dir, candidate) -> bool:
    """True when ``candidate`` resolves to a file directly inside ``data_dir``.

    ``Path.resolve`` follows links, so a name inside ``data`` whose target
    lives somewhere else is not inside.
    """
    try:
        data = Path(data_dir).resolve()
        path = Path(candidate).resolve()
    except (OSError, RuntimeError, TypeError, ValueError):
        return False
    if path == data or path.parent != data:
        return False
    try:
        path.relative_to(data)
    except ValueError:
        return False
    return True


def contained_file(app_root, candidate):
    """Resolved path inside ``data``, or None when ``candidate`` is not."""
    if candidate is None or candidate == "":
        return None
    try:
        data = data_directory(app_root)
    except (OSError, ValueError):
        return None
    if not path_inside(data, candidate):
        return None
    return Path(candidate).resolve()


def new_data_file(app_root, raw, suffix: str) -> Path:
    """Path for a new file name that passed ``sanitized_filename``."""
    data = data_directory(app_root)
    name = sanitized_filename(raw, suffix)
    path = (data / name).resolve()
    if not path_inside(data, path):
        raise ValueError("file name is not allowed")
    return path


def list_data_files(app_root, suffix: str):
    """File names directly in ``data`` whose resolved path stays there."""
    data = data_directory(app_root)
    suffix = suffix if str(suffix).startswith(".") else f".{suffix}"
    names = []
    for entry in data.iterdir():
        if entry.name.startswith("."):
            continue
        if entry.suffix.lower() != suffix.lower():
            continue
        if not entry.is_file():
            continue
        if path_inside(data, entry):
            names.append(entry.name)
    return sorted(names)
