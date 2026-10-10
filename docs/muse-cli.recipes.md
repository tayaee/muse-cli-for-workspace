# muse-cli Raw FS Recipes

A recipe collection for exploring the file system (`fs`) inside the Muse AI VM and downloading images/media files locally using `muse-cli raw`.

---

## 1. List Files & Directories (`fs.list`)

Inspect directory contents inside the VM.

### Caveats
- **Never use absolute paths (`/`)**: Passing `/` causes an `absolute paths are not allowed` error.
- Always provide a **relative path** (`.` or a subdirectory name like `workspace`).

### Recipes
```bash
# List root directory
muse-cli raw fs.list --body '{"path": "."}'

# List workspace directory
muse-cli raw fs.list --body '{"path": "workspace"}'

# List a specific subdirectory
muse-cli raw fs.list --body '{"path": "workspace/user"}'
```

---

## 2. Check Library Presets (`fs.library`)

Query asset lists categorized by Muse AI.

### Caveats
- The `preset` field is required and accepts only these 3 variants:
  - `"media"`: Generated image/video media files (including variants URL and metadata)
  - `"artifacts"`: Agent deliverables and documents (.xlsx, .csv, .md, etc.)
  - `"recents"`: Recently modified files
- Any other value (such as `"all"` or `"recent"`) returns a `422 Unprocessable Entity` error.

### Recipes
```bash
# Query generated images/videos
muse-cli raw fs.library --body '{"preset": "media"}'

# Query project deliverables / artifacts
muse-cli raw fs.library --body '{"preset": "artifacts"}'

# Query recently touched files
muse-cli raw fs.library --body '{"preset": "recents"}'
```

---

## 3. Search Files (`fs.search`)

Search files by extensions or name patterns.

### Caveats
- At least one filter (`extensions` or `name.contains`) is required. Passing an empty body (`{}`) causes an `invalid_params` error.

### Recipes
```bash
# Search for all image files by extensions
muse-cli raw fs.search --body '{"extensions": ["png", "jpg", "jpeg", "webp"]}'

# Search by filename keyword
muse-cli raw fs.search --body '{"name": {"contains": "avatar"}}'
```

---

## 4. Check File Metadata (`fs.stat`)

Inspect file size and modification timestamps. Required for calculating the exact `len` parameter prior to downloading.

### Recipe
```bash
muse-cli raw fs.stat --body '{"path": "workspace/user/media_library/image/ae/aea206c16d7c49608094c4c86eb4f58bb8b36b2bea204ceaaecda029980734ba.png"}'
```

---

## 5. Download Image/Media Files (`fs.read`)

Retrieve binary files (images, videos, etc.) from Muse AI as Base64-encoded payloads and write them to local files.

### Caveats
- Direct URLs (`*.metaaivm.com`) reside inside an internal virtual network and cannot be accessed via standard browsers or curl.
- You must retrieve data via the `fs.read` gateway method.
- The `path`, `offset`, and `len` fields are **all required**.
- The binary payload is returned Base64-encoded under `result.data_base64`.

### Download a Single File (Python One-Liner)
```bash
python3 -c '
import subprocess, json, base64

# Target relative path inside VM
target_path = "workspace/user/media_library/image/ae/aea206c16d7c49608094c4c86eb4f58bb8b36b2bea204ceaaecda029980734ba.png"

# 1. Check file size
stat = json.loads(subprocess.check_output(["muse-cli", "raw", "fs.stat", "--body", json.dumps({"path": target_path})]))
size = stat["result"]["size"]

# 2. Call fs.read to fetch Base64 data
body = json.dumps({"path": target_path, "offset": 0, "len": size})
res = json.loads(subprocess.check_output(["muse-cli", "raw", "fs.read", "--body", body]))

# 3. Decode and save locally
filename = target_path.split("/")[-1]
with open(filename, "wb") as f:
    f.write(base64.b64decode(res["result"]["data_base64"]))

print(f"Downloaded: {filename} ({size} bytes)")
'
```

### Batch Download All Media Library Assets
```bash
python3 -c '
import subprocess, json, base64, os

# 1. Fetch media library list
lib = json.loads(subprocess.check_output(["muse-cli", "raw", "fs.library", "--body", json.dumps({"preset": "media"})]))
entries = lib.get("result", {}).get("entries", [])

os.makedirs("downloaded_media", exist_ok=True)

for item in entries:
    raw_path = item["path"].lstrip("/")
    name = item["name"]
    size = item["size"]
    print(f"Downloading: {name} ({size} bytes)...")
    
    # 2. Fetch chunk and save
    body = json.dumps({"path": raw_path, "offset": 0, "len": size})
    res = json.loads(subprocess.check_output(["muse-cli", "raw", "fs.read", "--body", body]))
    
    data = base64.b64decode(res["result"]["data_base64"])
    out_file = os.path.join("downloaded_media", name)
    with open(out_file, "wb") as f:
        f.write(data)

print(f"Completed download of {len(entries)} files! (Saved to ./downloaded_media/)")
'
```

---

## 6. Export Plain Text Files (`fs.export`)

Quickly view or extract the contents of plain UTF-8 text files.

### Caveats
- **UTF-8 Text Only**: Calling this on binary files (images/videos) raises a `file is not valid UTF-8 text` error. Use `fs.read` for binary files.

### Recipe
```bash
muse-cli raw fs.export --body '{"path": "IDENTITY.md"}'
```

---

## 7. High-Level Transfer Tool (`muse-cli-w`)

`muse-cli-w` abstracts these low-level calls into a standard `cp`/`ls` interface (similar to `docker cp`, `kubectl cp`, or `scp`).

- **Remote Path Prefix**: `muse:` (e.g., `muse:workspace/avatars`, `muse:workspace/images/photo.png`)
- **Safety Policy**: Target files that already exist are **skipped by default** (`(skipped)`). Pass `-f` / `--force` to overwrite.
- **Verbose Flag**: `-v` / `--verbose` prints detailed progress for both transferred and skipped files.

### Syntax
```bash
muse-cli-w cp [OPTIONS] SOURCE... DEST
muse-cli-w ls [OPTIONS] [PATH]
```
