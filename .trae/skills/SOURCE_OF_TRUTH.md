# Skill tree provenance

`.trae/skills` is the **canonical** skill-pack tree for this project.

The sibling trees `.claude/skills`, `.vscode/skills`, and `.qoder/skills` are
generated copies mirrored from this directory so each provider (Claude Code,
VS Code, Qoder, Trae) routes the same skill set.

Edit skill packs **only here**, then re-sync the derived trees (copy the
changed pack directories, excluding `__pycache__`). Do not edit the derived
copies directly — changes made there will be overwritten on the next sync.
