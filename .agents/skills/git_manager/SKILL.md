---
name: git_manager
description: Streamline git workflows for this project, including squashing today's commits, checking status, and safely pushing to the remote.
---
# Git Manager Skill

Use this skill when the user asks to "wrap up for today", "commit and squash", or "push changes".

## Rules (always follow)
1. **Always run tests first** (`pytest`) before committing. Do not proceed if tests fail.
2. **Always pull** before committing/pushing if there is a remote.
3. **Always ask the user for approval** on the commit message before committing.
4. **Warn on mixed staged and unstaged changes**: If there are both staged and unstaged changes, explicitly warn the user before committing to prevent partial commits or unnecessary merge conflicts.

## Useful Commands

Check what has changed:
```bash
git status
git diff --stat
```

Run tests:
```bash
pytest
```

Pull latest from remote:
```bash
git pull
```

Stage all changes:
```bash
git add -A
```

Commit with a message (only after user approves):
```bash
git commit -m "<message>"
```

See commits made today (useful for squashing):
```bash
git log --oneline --since="00:00:00"
```

Amend/squash changes into the last commit (if it was made today):
```bash
git commit --amend -m "<new_message_incorporating_all_changes>"
```

Push (use `--force` only after an amend):
```bash
git push
git push --force
```
