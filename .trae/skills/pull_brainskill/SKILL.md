---
name: pull_brainskill
description: Pulls valid Claude Skills from a ZIP URL (preferred), Git repository, or local directory. Only folders containing a strictly named SKILL.md file are imported.
---

# Pull BRAIN Skill

This skill imports skill folders from a remote source or local directory. 

**Strict Validation**: A folder is considered a valid skill ONLY if it contains a `SKILL.md` file (strictly case-sensitive). Folders with `skill.md` or `Skill.md` will be skipped.

## How to use

1. **Locate the script**: 
   - Project path: `.claude/skills/pull_BRAINSkill/scripts/pull_skills.py`
   - Global path (Windows): `%USERPROFILE%\.claude\skills\pull_BRAINSkill\scripts\pull_skills.py`

2. **Run the script**: Provide a ZIP URL (Recommended), Git URL, or local path.

### Example 1: Pull via ZIP (Recommended First Choice)
This method is faster and works best in restricted network environments. To do this, you must firstly parse the repository into a ZIP file URL by appending `/archive/refs/heads/main.zip` to the repo URL. For example, for a repository at `https://github.com/GitRepoAuthorName/RepoName`, the ZIP URL would be `https://github.com/GitRepoAuthorName/RepoName/archive/refs/heads/main.zip`.
```bash
python ".claude/skills/pull_BRAINSkill/scripts/pull_skills.py" "https://github.com/GitRepoAuthorName/RepoName/archive/refs/heads/main.zip" --overwrite
```

### Example 2: Pull via Git
Use this if you need a specific branch or have git configured.
```bash
python ".claude/skills/pull_BRAINSkill/scripts/pull_skills.py" "https://github.com/GitRepoAuthorName/RepoName.git"
```

### Example 3: Import from Local Directory
```bash
python ".claude/skills/pull_BRAINSkill/scripts/pull_skills.py" "C:/Downloads/my-skills-repo"
```

Options:
- `--dest <path>`: Destination directory for skills (default: `.claude/skills` relative to current project).
- `--branch <branch>`: Specify branch to checkout.
- `--overwrite`: Overwrite existing skill folders with the same name.

## Behavior
- Clones the repository shallowly (`--depth 1`) into a temp directory.
- Scans top-level folders for `SKILL.md`.
- Copies valid skill folders into the destination `.claude/skills` directory.

## Notes
- Paths use forward slashes for compatibility.
- Requires `git` in PATH.
- Only checks for the presence of `SKILL.md`, not content validity.