"""Path identity for kit directories (W3).

Kit paths go through ``pathlib``. External task ids become stable directory
ids; display titles stay on the task record and are not used as folder names.
Windows reserved names, trailing space/dot, ``..``, drive letters, backslash,
and case collisions are rejected the same way on every host so a tree created
here still works on Windows. Network/UNC paths are reported as unsupported.
"""

from __future__ import annotations

import hashlib
import re
import sys
import unicodedata
from pathlib import Path

_RESERVED = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)
_ILLEGAL = re.compile(r'[<>:"|?*]')
_MAX_DIR_LEN = 80


class PathRuleError(ValueError):
    """A kit path or external id breaks the path rules."""


def _platform(platform: str | None) -> str:
    return platform or sys.platform


def is_reserved_name(name: str) -> bool:
    stem = name.split(".", 1)[0]
    return name.upper() in _RESERVED or stem.upper() in _RESERVED


def path_issues(raw: str, *, platform: str | None = None) -> list[dict[str, str]]:
    """Return structured problems for one user-supplied path string.

    ``platform`` defaults to the current OS. Tests pass ``win32`` or ``linux``
    so the rules are checked without a second machine.
    """
    system = _platform(platform)
    issues: list[dict[str, str]] = []
    if raw is None or str(raw).strip() == "":
        return [{"code": "empty", "message": "路径为空"}]
    text = str(raw)
    if "\x00" in text:
        issues.append({"code": "nul", "message": "路径含 NUL"})
    if text.startswith("\\\\") or text.startswith("//"):
        issues.append(
            {
                "code": "unc",
                "message": "UNC/网络路径不在本预览的一致性承诺内（未支持）",
            }
        )

    rest = text
    if system == "win32":
        drive = re.match(r"^([A-Za-z]):(.*)$", text, re.S)
        if drive:
            rest = drive.group(2)
            if rest.startswith("\\") or rest.startswith("/"):
                rest = rest[1:]
            elif rest == "":
                issues.append({"code": "drive_only", "message": "只有盘符，没有路径"})
    elif re.match(r"^[A-Za-z]:[\\/]", text):
        issues.append({"code": "windows_drive", "message": "非 Windows 路径带盘符"})

    if system == "win32":
        parts_text = rest.replace("\\", "/")
    else:
        if "\\" in rest:
            issues.append({"code": "backslash", "message": "非 Windows 路径含反斜杠"})
        parts_text = rest

    for part in (p for p in parts_text.split("/") if p not in ("", ".")):
        if part == "..":
            issues.append({"code": "dotdot", "message": "路径含 ..，不按字面拆成组件后放行"})
            continue
        if part.endswith(" ") or part.endswith("."):
            issues.append(
                {
                    "code": "trailing_space_or_dot",
                    "message": f"路径组件以空格或点结尾: {part!r}",
                }
            )
        if is_reserved_name(part):
            issues.append({"code": "reserved", "message": f"Windows 保留名: {part}"})
        if _ILLEGAL.search(part) or any(ord(ch) < 32 for ch in part):
            issues.append({"code": "illegal_char", "message": f"路径组件含非法字符: {part!r}"})
    return issues


def filesystem_kind(raw: str) -> str:
    """``local`` for a normal path, ``未支持`` for UNC/network-style prefixes."""
    text = str(raw or "")
    if text.startswith("\\\\") or text.startswith("//"):
        return "未支持"
    return "local"


def assert_kit_path(raw: str, *, platform: str | None = None) -> None:
    issues = path_issues(raw, platform=platform)
    if issues:
        detail = "；".join(item["message"] for item in issues)
        raise PathRuleError(detail)


def _legal_dir_component(text: str) -> bool:
    """One directory component that is portable, including Chinese.

    The display title is not a path. A task id that is already one legal
    component is kept so existing run directories do not move.
    """
    if not text or text in (".", ".."):
        return False
    if len(text) > _MAX_DIR_LEN:
        return False
    if "/" in text or "\\" in text or "\x00" in text:
        return False
    if text.endswith(" ") or text.endswith("."):
        return False
    if is_reserved_name(text):
        return False
    if _ILLEGAL.search(text):
        return False
    if any(ord(ch) < 32 for ch in text):
        return False
    return True


def stable_dir_id(external_id: str) -> str:
    """Map an external task/team id onto one stable directory name.

    A single legal component is kept (ASCII or Chinese). Slash, reserved
    Windows names, trailing space/dot, and other illegal components become
    ``slug-sha256[:12]``. The same input always yields the same id. This is
    not the human title.
    """
    text = unicodedata.normalize("NFC", str(external_id or "").strip())
    if not text:
        raise PathRuleError("外部 id 为空，不能映射目录")
    if _legal_dir_component(text):
        return text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()[:24]
    if not slug:
        slug = "task"
    return f"{slug}-{digest}"


def assert_no_case_collision(parent: Path, dir_name: str) -> None:
    """Refuse a second directory whose name differs only by case.

    Exact same name is left to the caller's overwrite policy. A case-only
    collision is never overwritten, including when ``--force`` is set.
    """
    if not parent.is_dir():
        return
    folded = dir_name.casefold()
    for child in parent.iterdir():
        if not child.is_dir():
            continue
        if child.name == dir_name:
            continue
        if child.name.casefold() == folded:
            raise PathRuleError(
                f"目录大小写碰撞: 已有 {child.name!r}，拒绝再创建 {dir_name!r}（不覆盖）"
            )


def resolve_under_root(root: Path, raw: str) -> Path:
    """Resolve ``raw`` and require the result to stay strictly inside ``root``.

    Symlinks and Windows junctions are followed by ``Path.resolve``. If the
    final path leaves ``root``, this raises. ``..`` in the supplied string is
    rejected before resolution.
    """
    assert_kit_path(raw)
    root_p = Path(root).resolve()
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root_p / candidate
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise PathRuleError(f"路径无法解析: {raw}") from exc
    try:
        resolved.relative_to(root_p)
    except ValueError as exc:
        raise PathRuleError(f"路径越出项目根 {root_p}: {resolved}") from exc
    if resolved == root_p:
        raise PathRuleError("路径不能等于项目根，须为独立子目录")
    return resolved


def newline_normalized_digest(data: bytes | str) -> str:
    """SHA-256 after normalizing newlines to LF.

    CRLF and LF copies of the same text share this digest. The raw byte
    digest is :func:`raw_digest`.
    """
    if isinstance(data, str):
        blob = data.encode("utf-8")
    else:
        blob = data
    normalized = blob.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def raw_digest(data: bytes | str) -> str:
    if isinstance(data, str):
        blob = data.encode("utf-8")
    else:
        blob = data
    return hashlib.sha256(blob).hexdigest()
