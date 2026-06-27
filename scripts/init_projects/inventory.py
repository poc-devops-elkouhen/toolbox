from __future__ import annotations

import re
from pathlib import Path

from .errors import fail


def read_internal_gitlab_host(apps_file: Path) -> str:
    content = apps_file.read_text()
    match = re.search(r"^\s*internalHost:\s*(\S+)\s*$", content, re.MULTILINE)
    if not match:
        fail(f"Champ gitlab.internalHost introuvable dans {apps_file}")
    return match.group(1)


def write_apps_file(apps_file: Path, app_name: str, app: dict) -> str:
    content = apps_file.read_text()
    prefix, chunks = split_apps_block(content)
    new_chunk = "\n".join(emit_yaml([app], 2))
    action = "ajoute"
    replaced = False
    updated_chunks = []
    for chunk in chunks:
        if app_chunk_name(chunk) == app_name:
            updated_chunks.append(new_chunk)
            replaced = True
            action = "mis a jour"
        else:
            updated_chunks.append(chunk)
    if not replaced:
        updated_chunks.append(new_chunk)

    apps_text = "apps:\n" + "\n".join(updated_chunks) if updated_chunks else "apps: []"
    apps_file.write_text(prefix.rstrip() + "\n\n" + apps_text.rstrip() + "\n")
    return action


def write_app_file(apps_dir: Path, app_name: str, app: dict) -> str:
    apps_dir.mkdir(parents=True, exist_ok=True)
    app_file = apps_dir / f"{app_name}.yaml"
    action = "mis a jour" if app_file.exists() else "ajoute"
    app_file.write_text("\n".join(emit_yaml(app)).rstrip() + "\n")
    return action


def delete_app_file(apps_dir: Path, app_name: str) -> Path | None:
    app_file = apps_dir / f"{app_name}.yaml"
    if not app_file.exists():
        return None
    app_file.unlink()
    return app_file


def delete_app_from_apps_file(apps_file: Path, app_name: str) -> bool:
    content = apps_file.read_text()
    prefix, chunks = split_apps_block(content)
    updated_chunks = [chunk for chunk in chunks if app_chunk_name(chunk) != app_name]
    if len(updated_chunks) == len(chunks):
        return False

    apps_text = "apps:\n" + "\n".join(updated_chunks) if updated_chunks else "apps: []"
    apps_file.write_text(prefix.rstrip() + "\n\n" + apps_text.rstrip() + "\n")
    return True


def split_apps_block(content: str) -> tuple[str, list[str]]:
    match = re.search(r"^apps:\s*$", content, re.MULTILINE)
    if not match:
        return content.rstrip() + "\n\n", []
    prefix = content[: match.start()]
    apps_text = content[match.end() :].strip("\n")
    if not apps_text.strip():
        return prefix, []

    chunks: list[str] = []
    current: list[str] = []
    for line in apps_text.splitlines():
        if re.match(r"^  - name:\s+", line) and current:
            chunks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("\n".join(current))
    return prefix, chunks


def app_chunk_name(chunk: str) -> str | None:
    match = re.search(r"^  - name:\s*(\S+)\s*$", chunk, re.MULTILINE)
    return match.group(1) if match else None


def yaml_scalar(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    text = str(value)
    if text == "" or text[0] in "@`" or text.strip() != text:
        return repr(text)
    if re.search(r"[:{}\[\],&*#?|<>=!%@`]", text):
        return repr(text)
    return text


def emit_yaml(value: object, indent: int = 0) -> list[str]:
    prefix = " " * indent
    lines: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(emit_yaml(item, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {yaml_scalar(item)}")
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                first = True
                for key, child in item.items():
                    marker = "- " if first else "  "
                    if isinstance(child, (dict, list)):
                        lines.append(f"{prefix}{marker}{key}:")
                        lines.extend(emit_yaml(child, indent + 4))
                    else:
                        lines.append(f"{prefix}{marker}{key}: {yaml_scalar(child)}")
                    first = False
            elif isinstance(item, list):
                lines.append(f"{prefix}-")
                lines.extend(emit_yaml(item, indent + 2))
            else:
                lines.append(f"{prefix}- {yaml_scalar(item)}")
    else:
        lines.append(f"{prefix}{yaml_scalar(value)}")
    return lines
