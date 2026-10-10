# muse-cli-w

A CLI tool for seamless file synchronization and asset management between Muse AI cloud Workspace and your local file system.

---

## Quick Installation

### 1) Prerequisite: `muse-cli`
This tool interacts with the Muse AI cloud through [`muse-cli`](https://github.com/muse-ai/muse-cli). Please refer to the [`muse-cli` repository](https://github.com/muse-ai/muse-cli) for installation instructions.

Verify connectivity to your Muse agent:
```bash
muse-cli status
```

### 2) Install `muse-cli-w`
Install `muse-cli-w` via [`uv`](https://github.com/astral-sh/uv):
```bash
# From cloned repository directory
uv tool install -e . --force

# Or directly from Git repository
uv tool install https://github.com/tayaee/muse-cli-for-workspace.git --force
```
Verify installation:
```bash
muse-cli-w --help
```

---

## Quick Start

A typical end-to-end workflow (request generation -> list -> download -> upload):

### 1) Request chart generation from Muse agent
Ask the agent to find/generate a stock chart image and snapshot information, saving them into a date-structured directory:
```bash
muse-cli send "Search for AAPL 2026-10-09 stock chart image and information and save it to downloads/ticker/AAPL/<YYYY>/<MM>/<DD>/snapshot.{png,json} in the workspace"
```

### 2) List files (`ls`)
Verify that the generated snapshot files exist in the workspace (supports recursive listing with `-R`):
```bash
muse-cli-w ls downloads/ticker/AAPL/2026/10/09/
```
*Example Output:*
```text
snapshot.json
snapshot.png
```

### 3) Download files (`cp`)
Download files from the remote workspace to your local machine (remote paths start with `muse:` prefix):
```bash
# Sync ticker directory recursively to your local folder
muse-cli-w cp -r muse:downloads/ticker/AAPL/ ~/muse/workspace/downloads/ticker/AAPL/

# Or download a specific snapshot file directly
muse-cli-w cp muse:downloads/ticker/AAPL/2026/10/09/snapshot.png ./
```

Verify downloaded files locally:
```bash
ls -lR ~/muse/workspace/downloads/ticker/AAPL/
```

### 4) Upload files (`cp`)
Upload locally authored reports or data files to the workspace:
```bash
muse-cli-w cp tests/report-2026-10-09.md muse:uploads/reports/2026/10/
```
*Example Output:*
```text
+ muse-cli-w cp tests/report-2026-10-09.md muse:uploads/reports/2026/10/report-2026-10-09.md
```

---

## Specifications & Detailed Manuals

For comprehensive command options (`-f`, `-v`, `--format json`, `--media`, `--artifacts`, etc.) and internal gateway mapping details, see the dedicated documentation:

- [Listing (`ls`) Specification](docs/spec/ls.md): Directory navigation, JSON output formatting, and smart preset views
- [Copying (`cp`) Specification](docs/spec/cp.md): Recursive sync, force overwrite (`-f`), verbose output (`-v`), and batch preset downloads
- [Low-Level Gateway Recipes](docs/muse-cli.recipes.md): Direct invocations of `muse-cli raw fs.*` APIs
