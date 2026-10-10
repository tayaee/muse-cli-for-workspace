# muse-cli-w `ls` Command Specification

Detailed specification for the `ls` command, used to list files, directories, and smart preset views within the Muse AI Workspace.

---

## 1. Overview & Syntax

```bash
muse-cli-w ls [OPTIONS] [PATH]
```

- If `PATH` is omitted, the default path is `workspace`.
- Remote paths can be specified as `workspace`, `workspace/charts`, or with the prefix `muse:workspace/charts`.

---

## 2. Options

| Option | Description |
| :--- | :--- |
| `-r`, `-R`, `--recursive` | List subdirectories recursively (standard Unix `ls -R` behavior) |
| `--media` | **[Preset]** List generated media assets (images, videos) (`fs.library preset=media`) |
| `--artifacts` | **[Preset]** List generated project artifacts (.xlsx, .csv, .md, etc.) (`fs.library preset=artifacts`) |
| `--recent` | **[Preset]** List recently modified/accessed files (`fs.library preset=recents`) |
| `-l`, `--long` | Display detailed metadata (size, modification timestamp, MIME type, etc.) |
| `--format` | Output format selection (`text`, `json`, default: `text`) |

---

## 3. Backend Gateway Mapping

`muse-cli-w ls` internally calls low-level `muse-cli raw` APIs.

| Feature | Gateway Method | Parameters |
| :--- | :--- | :--- |
| Standard directory listing | `fs.list` | `{"path": "<normalized relative path>"}` |
| Preset listing (`--media`, `--artifacts`, `--recent`) | `fs.library` | `{"preset": "media" \| "artifacts" \| "recents"}` |

### Path Normalization Rules
- **Workspace as Remote CWD**: Relative paths (e.g. `spaces/`, `downloads/ticker/`) automatically resolve under `workspace/`.
- **VM Root Access**: Absolute-style paths prefixed with `muse:/` (e.g. `muse:/memory/`, `muse:/IDENTITY.md`, `muse:/`) resolve directly from the VM root.
- **Output Formats**:
  - Default: Unix `ls -1aF` format (one entry per line, trailing `/` for directories, no trailing character for files).
  - Detailed (`-l`): Unix `ls -l` format (`drwxr-xr-x 2 muse muse 4096 <ISO-8601-time> <name>`).
  - Recursive (`-R`): Prints `muse:<path>:` directory headers followed by contents.

---

## 4. Usage Scenarios & Examples

### 4.1. Standard Directory Browsing
```bash
# Browse root workspace directory (ls -1aF style)
muse-cli-w ls

# Detailed long listing (ls -l style)
muse-cli-w ls -l downloads/ticker/AAPL/2026/10/09/

# Browse specific subdirectories
muse-cli-w ls downloads/ticker/AAPL/2026/10/09/
muse-cli-w ls muse:avatars/

# Recursively browse subdirectories (-R / -r)
muse-cli-w ls -R downloads/ticker/AAPL/
```

### 4.2. JSON Output (`--format json`)
Outputs raw JSON formatted data for programmatic automation and pipeline processing.
```bash
muse-cli-w ls --format json
muse-cli-w ls charts/ --format json
```

### 4.3. Smart Preset Views
Instantly inspect curated assets without needing to know deep internal directory paths.
```bash
# View generated image/video media library
muse-cli-w ls --media

# View agent deliverables and documents (.xlsx, .csv, .md, etc.)
muse-cli-w ls --artifacts

# View recently modified files
muse-cli-w ls --recent
```
