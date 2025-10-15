#!/usr/bin/env python3
import os
import re
import io
import sys
import json
import base64
import shutil
import hashlib
import zipfile
from pathlib import Path

EXCLUDE_DIRS = {'.git', '.github', '__pycache__', '.idea', '.vscode', 'zips'}
EXCLUDE_FILES = {'Thumbs.db', '.DS_Store'}
EXCLUDE_EXTS = {'.pyc', '.pyo', '.pyd', '.db', '.swp'}

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR / 'repo'
ZIPS_DIR = REPO_DIR / 'zips'

PNG_1PX_BASE64 = (
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII='
)


def log(msg: str):
    print(f"[repo-gen] {msg}")


def read_addon_xml(addon_dir: Path) -> str:
    addon_xml_path = addon_dir / 'addon.xml'
    with addon_xml_path.open('r', encoding='utf-8') as f:
        txt = f.read().strip()
    # remove xml declaration if present
    txt = re.sub(r'^\s*<\?xml[^>]*>\s*', '', txt)
    return txt


def parse_addon_meta(addon_dir: Path):
    """Return (addon_id, version)."""
    import xml.etree.ElementTree as ET
    addon_xml_path = addon_dir / 'addon.xml'
    tree = ET.parse(str(addon_xml_path))
    root = tree.getroot()
    addon_id = root.get('id')
    version = root.get('version')
    if not addon_id or not version:
        raise ValueError(f"Missing id/version in {addon_xml_path}")
    return addon_id, version


def ensure_placeholder_assets(addon_dir: Path):
    icon_path = addon_dir / 'icon.png'
    if not icon_path.exists():
        data = base64.b64decode(PNG_1PX_BASE64)
        icon_path.write_bytes(data)
        log(f"Created placeholder icon.png in {addon_dir}")
    # fanart is optional; skip if missing


def should_exclude(path: Path) -> bool:
    name = path.name
    if name in EXCLUDE_FILES:
        return True
    if name.startswith('.') and path.is_file():
        return True
    if path.suffix.lower() in EXCLUDE_EXTS:
        return True
    return False


def zip_addon(addon_dir: Path, out_root: Path, addon_id: str, version: str) -> Path:
    out_dir = out_root / addon_id
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_name = f"{addon_id}-{version}.zip"
    zip_path = out_dir / zip_name

    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(addon_dir):
            root_path = Path(root)
            # filter dirs we don't want to traverse
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]
            for file in files:
                fpath = root_path / file
                if should_exclude(fpath):
                    continue
                rel = fpath.relative_to(addon_dir)
                arcname = Path(addon_id) / rel
                zf.write(str(fpath), str(arcname))

    # md5
    md5_hex = hashlib.md5(zip_path.read_bytes()).hexdigest()
    (zip_path.with_suffix(zip_path.suffix + '.md5')).write_text(md5_hex, encoding='utf-8')
    log(f"Built {zip_path.name} (+ .md5)")
    return zip_path


def build_addons_xml(addon_dirs: list[Path], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    chunks = []
    for a in addon_dirs:
        try:
            chunks.append(read_addon_xml(a))
        except Exception as e:
            raise RuntimeError(f"Failed reading addon.xml from {a}: {e}")
    addons_xml = '<?xml version="1.0" encoding="UTF-8"?>\n<addons>\n' + '\n'.join(chunks) + '\n</addons>\n'
    out_path = out_dir / 'addons.xml'
    out_path.write_text(addons_xml, encoding='utf-8')
    md5_hex = hashlib.md5(out_path.read_bytes()).hexdigest()
    (out_path.parent / 'addons.xml.md5').write_text(md5_hex, encoding='utf-8')
    log("Generated addons.xml and addons.xml.md5")
    return out_path


def main():
    if not REPO_DIR.exists():
        raise SystemExit(f"Repo folder not found: {REPO_DIR}")

    # discover addons (subdirectories with addon.xml)
    addons = []
    for child in REPO_DIR.iterdir():
        if child.is_dir() and child.name != 'zips' and (child / 'addon.xml').exists():
            addons.append(child)

    if not addons:
        raise SystemExit("No addons found under repo/ (each addon must have an addon.xml)")
    
    # zip each addon
    ZIPS_DIR.mkdir(parents=True, exist_ok=True)
    repo_zip = None
    repo_id = 'repository.centulus'
    repo_version = None

    for addon_dir in addons:
        addon_id, version = parse_addon_meta(addon_dir)
        if addon_id == repo_id:
            # ensure minimal assets for repository addon only
            ensure_placeholder_assets(addon_dir)
        zpath = zip_addon(addon_dir, ZIPS_DIR, addon_id, version)
        if addon_id == repo_id:
            repo_zip = zpath
            repo_version = version

    # build addons.xml
    build_addons_xml(addons, ZIPS_DIR)

    # copy repository zip to project root for easy installation
    if repo_zip and repo_version:
        dest = SCRIPT_DIR / f"{repo_id}-{repo_version}.zip"
        shutil.copy2(repo_zip, dest)
        # also copy .md5
        md5_src = repo_zip.with_suffix(repo_zip.suffix + '.md5')
        shutil.copy2(md5_src, dest.with_suffix(dest.suffix + '.md5'))
        log(f"Copied {dest.name} (+ .md5) to project root")
    else:
        log("Warning: repository.centulus not found; cannot copy repository zip to root")

    log("All done")


if __name__ == '__main__':
    main()
