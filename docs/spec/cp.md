# muse-cli-w `cp` Command Specification

Detailed specification for the `cp` command, used to copy files and directories between the local filesystem and the Muse AI Workspace.

---

## 1. Overview & Syntax

```bash
# 1) Download (Workspace ➔ Local)
muse-cli-w cp [OPTIONS] muse:REMOTE_SRC... LOCAL_DEST

# 2) Upload (Local ➔ Workspace)
muse-cli-w cp [OPTIONS] LOCAL_SRC... muse:REMOTE_DEST
```

- Remote paths are distinguished by the `muse:` prefix (e.g., `muse:workspace/charts/`).
- The transfer direction (download vs. upload) is determined automatically based on the position of the `muse:` prefix.

---

## 2. Options

| Option | Description |
| :--- | :--- |
| `-r`, `-R`, `--recursive` | Recursively copy directories. |
| `-f`, `--force` | Overwrite destination files if they already exist (default: skip). |
| `-q` | Omit `(skipped)` messages for existing files (copied messages remain visible). |
| `--quiet` | Completely suppress all messages (including copied file notifications). |
| `-v`, `--verbose` | Print developer debug messages (`[debug]` chunk offsets, stat payloads). |
| `-m`, `--media` | **[Preset]** Batch download all generated media (images/videos) to local folder. |
| `-a`, `--artifacts` | **[Preset]** Batch download all generated documents/artifacts (.xlsx, .csv, .md) to local folder. |

---

## 3. Core Design Principles

1. **Remote Safety Policy (Skip by Default)**
   - To prevent unnecessary network overhead and accidental data loss, existing target files are skipped by default.
   - To overwrite existing files, the `-f` / `--force` flag must be explicitly passed.
2. **Output Formatting & Logging Rules**
   - **Default output (no flags)**:
     - When a file is copied: Prints `+ muse-cli-w cp SOURCE TARGET`.
     - When a file already exists: Prints `+ muse-cli-w cp SOURCE TARGET (skipped)`.
   - **Skip omission (`-q`)**: Suppresses `(skipped)` notifications; only actual file transfers are echoed.
   - **Full quiet mode (`--quiet`)**: Completely silent transfer (no echo for copies or skips).
   - **Developer debug mode (`-v`, `--verbose`)**: Emits `[debug]` diagnostics (stat results, chunk transfer progress) to `stderr`.
3. **Chunked Streaming for Large Files**
   - Files are transferred in 32KB chunks (compliant with the gateway Noise protocol's 64KB frame limit) using `fs.read`/`fs.write` to prevent memory bottlenecks and timeouts on large media.

---

## 4. Backend Gateway Mapping

| Feature | Gateway Method | Payload / Invocation Rules |
| :--- | :--- | :--- |
| Check file existence | `fs.stat` | `{"path": "<relative path>"}` (used to determine skip condition) |
| Download file | `fs.read` | `{"path": "<path>", "offset": <n>, "len": <chunk>}` ➔ decode base64 |
| Upload file | `fs.write` | `{"path": "<path>", "overwrite": bool, "create_parent": true, "data_base64": "<b64>"}` |

### Path Normalization Rules
- **Workspace as Remote CWD**: Relative paths (e.g. `muse:spaces/`, `muse:downloads/ticker/`) automatically resolve inside `workspace/`.
- **VM Root Access**: Absolute-style paths prefixed with `muse:/` (e.g. `muse:/memory/`, `muse:/IDENTITY.md`, `muse:/`) resolve directly from the VM root.
- **Explicit `workspace/`**: Paths starting with `workspace/` or `muse:workspace/` are preserved without double-nesting.

## 5. Usage Scenarios & Examples

### 5.1. Download (Workspace ➔ Local)
```bash
# ⭐️ Batch download / sync entire Workspace (most common use case)
muse-cli-w cp -r muse:./ ./workspace/
# Or download directly into current working directory:
muse-cli-w cp -r muse:./ ./

# Show detailed progress including skipped files (-v)
muse-cli-w cp -r -v muse:./ ./workspace/

# Single file download
muse-cli-w cp muse:downloads/ticker/AAPL/2026/10/09/snapshot.png ./

# Download and rename
muse-cli-w cp muse:downloads/ticker/AAPL/2026/10/09/snapshot.png ./aapl-snapshot.png

# Remote wildcard pattern match download (quotes recommended)
muse-cli-w cp "muse:avatars/*.webp" ./avatars/

# Recursive subdirectory download
muse-cli-w cp -r muse:avatars/ ./avatars/

# Batch download presets
muse-cli-w cp --media ./media/
muse-cli-w cp --artifacts ./artifacts/
```

### 5.2. Upload (Local ➔ Workspace)
```bash
# Single file upload
muse-cli-w cp photo.png muse:images/

# Multi-file wildcard upload
muse-cli-w cp *.png muse:images/

# Recursive directory upload (-r)
muse-cli-w cp -r ./my_folder/ muse:workspace/

# Force overwrite (-f)
muse-cli-w cp -f photo.png muse:images/

# Verbose directory upload (-v)
muse-cli-w cp -r -v ./my_folder/ muse:workspace/
```
