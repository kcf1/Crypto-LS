# SOP: Handling Access Denied Errors in Cursor AI

## Problem

When running Git or Docker commands through Cursor AI's terminal, you may encounter "access denied" errors:

- **Git errors**: `fatal: Unable to create '.git/index.lock': Permission denied`
- **Docker errors**: `open //./pipe/dockerDesktopLinuxEngine: Access is denied`

These errors occur due to sandbox restrictions in Cursor's AI environment.

## Solution: Use Required Permissions

When encountering access denied errors, use the `required_permissions: ['all']` parameter when running terminal commands.

### For Git Commands

**Before (fails with access denied):**
```bash
git add -A
git commit -m "message"
```

**After (works with permissions):**
```python
run_terminal_cmd(
    command="git add -A",
    required_permissions=['all']
)
run_terminal_cmd(
    command="git commit -m 'message'",
    required_permissions=['all']
)
```

### For Docker Commands

**Before (fails with access denied):**
```bash
docker compose up -d
docker compose ps
```

**After (works with permissions):**
```python
run_terminal_cmd(
    command="docker compose up -d",
    required_permissions=['all']
)
```

## When to Use This Approach

Use `required_permissions: ['all']` when:

1. **Git operations fail** with lock file or permission errors
2. **Docker commands fail** with pipe access denied errors
3. **File system operations** require elevated permissions
4. **Standard sandbox restrictions** are blocking necessary operations

## Alternative Solutions

If `required_permissions: ['all']` doesn't work:

### Option 1: Use Cursor's Git UI
1. Press `Ctrl+Shift+G` (Source Control)
2. Stage files using the UI
3. Commit using the UI

### Option 2: Use Your Terminal
Run commands directly in your terminal (outside Cursor):
```bash
git add -A
git commit -m "message"
```

### Option 3: Remove Lock Files Manually
```bash
# Remove Git lock file
del .git\index.lock 2>nul  # Windows
rm -f .git/index.lock      # Linux/Mac

# Then retry Git commands
```

## Best Practices

1. **Try standard commands first** - Only use `required_permissions: ['all']` when needed
2. **Check git status first** - Verify what needs to be committed
3. **Use descriptive commit messages** - Follow project conventions
4. **Verify after committing** - Check `git log` to confirm commit succeeded

## Example Workflow

```python
# 1. Check status
run_terminal_cmd("git status", required_permissions=['all'])

# 2. Stage files
run_terminal_cmd("git add -A", required_permissions=['all'])

# 3. Commit
run_terminal_cmd(
    "git commit -m 'Descriptive commit message'",
    required_permissions=['all']
)

# 4. Verify
run_terminal_cmd("git log --oneline -1", required_permissions=['all'])
```

## Troubleshooting

### Issue: Still getting access denied with `['all']` permissions
- **Solution**: Use Cursor's Git UI or your terminal directly

### Issue: Git lock file persists
- **Solution**: Manually remove `.git/index.lock` and retry

### Issue: Docker commands still fail
- **Solution**: Ensure Docker Desktop is running and accessible
- **Solution**: Run Docker commands from your terminal

### Issue: Files not showing in git status
- **Solution**: Check if files are in `.gitignore`
- **Solution**: Verify files exist in the filesystem

## Related Documentation

- [Docker Setup](../setup/docker-setup.md)
- [Git Workflow](../../../.gitignore)

## Last Updated

2025-02-02
