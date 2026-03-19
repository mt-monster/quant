#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pull Skill Folders from a Git repository into a local .claude/skills directory.

Usage:
  python pull_skills.py <git_repo_url> [--dest <dest_path>] [--branch <branch>] [--overwrite]

- git_repo_url: HTTPS git URL, e.g., https://github.com/GitRepoAuthorName/-.git
- dest_path: Destination folder for skills (default: <cwd>/.claude/skills)
- branch: Branch to checkout (default: auto, uses repo default)
- overwrite: If set, overwrite existing skill folders (default: off)

Behavior:
- Clones the repo into a temporary directory (depth=1)
- Scans top-level subfolders for a SKILL.md file
- Copies those folders into the destination .claude/skills directory

Notes:
- Requires Git installed and available in PATH.
- Only validates existence of SKILL.md, does not validate YAML content.
- Copies one level deep (top-level folders only).
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess
from typing import List, Dict


def run(cmd: List[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def copy_skill_folder(src_folder: str, dest_root: str, overwrite: bool) -> Dict[str, str]:
    name = os.path.basename(src_folder.rstrip("/\\"))
    dest_folder = os.path.join(dest_root, name)

    # STRICT check for SKILL.md existence (case-sensitive)
    # os.listdir returns the actual filename on the filesystem
    if "SKILL.md" not in os.listdir(src_folder):
         return {"status": "skipped", "folder": name, "reason": "no SKILL.md found (strictly case-sensitive)"}

    if os.path.exists(dest_folder):
        if overwrite:
            shutil.rmtree(dest_folder)
        else:
            return {"status": "skipped", "folder": name, "reason": "exists"}
    
    shutil.copytree(src_folder, dest_folder)
    
    return {"status": "copied", "folder": name, "dest": dest_folder}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "ok": False,
            "error": "Missing git repo URL",
            "usage": "python pull_skills.py <git_repo_url> [--dest <dest_path>] [--branch <branch>] [--overwrite]"
        }, ensure_ascii=False))
        sys.exit(1)

    repo_url = sys.argv[1]
    dest = None
    branch = None
    overwrite = False

    # Parse optional args
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--dest" and i + 1 < len(args):
            dest = args[i + 1]
            i += 2
        elif a == "--branch" and i + 1 < len(args):
            branch = args[i + 1]
            i += 2
        elif a == "--overwrite":
            overwrite = True
            i += 1
        else:
            i += 1

    if not dest:
        dest = os.path.join(os.getcwd(), ".claude", "skills")
    ensure_dir(dest)

    tempdir = tempfile.mkdtemp(prefix="pull_skills_")
    repo_dir = os.path.join(tempdir, "repo")


    # Handle local directory vs git URL vs ZIP URL
    if os.path.isdir(repo_url):
        # Case 1: Local directory
        try:
            shutil.copytree(repo_url, repo_dir, dirs_exist_ok=True)
        except Exception as e:
            print(json.dumps({"ok": False, "stage": "copy_local", "error": str(e)}, ensure_ascii=False))
            sys.exit(2)
            
    elif repo_url.lower().endswith(".zip"):
        # Case 2: ZIP URL (direct download)
        import urllib.request
        import zipfile
        
        try:
            zip_path = os.path.join(tempdir, "repo.zip")
            # print(f"Downloading {repo_url}...", file=sys.stderr)
            urllib.request.urlretrieve(repo_url, zip_path)
            
            extract_dir = os.path.join(tempdir, "extracted")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Handle GitHub zip structure: usually extract_dir/<repo-branch>/...
            # We want repo_dir to point to the folder containing the skills
            contents = os.listdir(extract_dir)
            if len(contents) == 1 and os.path.isdir(os.path.join(extract_dir, contents[0])):
                # Move the inner content to repo_dir
                shutil.move(os.path.join(extract_dir, contents[0]), repo_dir)
            else:
                shutil.move(extract_dir, repo_dir)
                
        except Exception as e:
            print(json.dumps({
                "ok": False, 
                "stage": "download_zip", 
                "error": str(e),
                "url": repo_url
            }, ensure_ascii=False))
            sys.exit(2)

    else:
        # Case 3: Git Clone
        clone_cmd = ["git", "clone", "--depth", "1"]
        if branch:
            clone_cmd += ["--branch", branch]
        clone_cmd += [repo_url, repo_dir]

        cp = run(clone_cmd)
        if cp.returncode != 0:
            print(json.dumps({
                "ok": False,
                "stage": "clone",
                "cmd": " ".join(clone_cmd),
                "stderr": cp.stderr.strip(),
                "stdout": cp.stdout.strip()
            }, ensure_ascii=False))
            sys.exit(2)

    # Scan top-level subfolders
    copied: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []

    for entry in os.listdir(repo_dir):
        sub = os.path.join(repo_dir, entry)
        if os.path.isdir(sub):
            # Check for skill.md case-insensitively
            res = copy_skill_folder(sub, dest, overwrite)
            if res["status"] == "copied":
                copied.append(res)
            else:
                # If "no SKILL.md found", we just skip silently effectively (or log as skipped)
                # But to avoid cluttering output with non-skill folders, strict filtering is good.
                pass

    result = {
        "ok": True,
        "repo": repo_url,
        "dest": dest,
        "copied": copied,
        "skipped": skipped
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
