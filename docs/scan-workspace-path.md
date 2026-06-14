# Scan Workspace Path

`SCAN_REPO_BASE_DIR` should use a backend-relative path in shared env files.

Recommended value:

```env
SCAN_REPO_BASE_DIR=workspace
```

How it resolves:

- On local Windows runs, it resolves to `<backend>/workspace`.
- In Docker containers, it resolves to `/backend/workspace`.

Use OS-specific absolute paths only when the app is guaranteed to run on that same OS. A Windows absolute path like `C:\...` is invalid inside the Linux-based Docker services.
