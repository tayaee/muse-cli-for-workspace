#!/usr/bin/env python3
"""muse-cli-w: cp-style file transfer utility for Muse AI workspace.

Usage:
  # 1. Directory & Preset listing (조회)
  muse-cli-w ls [muse:workspace]
  muse-cli-w ls -R [muse:workspace]
  muse-cli-w ls --media
  muse-cli-w ls --artifacts
  muse-cli-w ls --recent
  muse-cli-w ls --format json

  # 1b. Detailed listing (same as ls -l)
  muse-cli-w dir [muse:workspace]
  muse-cli-w dir -R [muse:workspace]

  # 2. Download from workspace (다운로드)
  muse-cli-w cp [OPTIONS] muse:REMOTE_SRC... LOCAL_DEST
  muse-cli-w cp -r [OPTIONS] muse:REMOTE_DIR LOCAL_DEST
  muse-cli-w cp --media LOCAL_DEST
  muse-cli-w cp --artifacts LOCAL_DEST

  # 3. Upload to workspace (업로드)
  muse-cli-w cp [OPTIONS] LOCAL_SRC... muse:REMOTE_DEST
  muse-cli-w cp -r [OPTIONS] LOCAL_DIR muse:REMOTE_DEST

  # 4. Print remote file content (내용 출력, Windows: type)
  muse-cli-w cat FILE
  muse-cli-w type FILE

  # Windows-style names (동일 동작): copy (= cp), dir (= ls -l), type (= cat)

Options:
  -r, -R, --recursive   Copy directories recursively
  -f, --force           Overwrite destination files without asking
  -v, --verbose         Show detailed progress including skipped files
"""

import argparse
import base64
import fnmatch
import glob
import json
import os
import subprocess
import sys
from pathlib import Path

CHUNK_SIZE = 32 * 1024  # 32KB chunks to comply with Noise protocol 65,535-byte frame limit
REMOTE_PREFIXES = ("muse:", "muse://")

# Platform command mapping. Help always shows both groups.
LINUX_COMMANDS = ("cp", "ls", "cat")
WINDOWS_COMMANDS = ("copy", "dir", "type")


class PlatformHelpFormatter(argparse.HelpFormatter):
    """Show subcommands grouped by platform. Both groups are always displayed."""

    def _format_action(self, action):
        if isinstance(action, argparse._SubParsersAction):
            return self._format_subparsers_by_platform(action)
        return super()._format_action(action)

    def _format_subparsers_by_platform(self, action):
        help_by_name = {a.dest: a.help for a in action._choices_actions}
        width = max(len(n) for n in LINUX_COMMANDS + WINDOWS_COMMANDS)
        # NOTE: the section heading ("positional arguments:") is emitted by
        # the section itself, so only emit the platform groups here.
        lines = []
        for group_title, names in (
            ("For Windows", WINDOWS_COMMANDS),
            ("For Linux", LINUX_COMMANDS),
        ):
            lines.append(f"  {group_title}:")
            for name in names:
                lines.append(f"    {name:<{width}}  {help_by_name.get(name, '')}")
        return "\n".join(lines) + "\n\n"


def is_remote(path: str) -> bool:
    """Check if a path specifies a remote Muse workspace path."""
    return any(path.startswith(p) for p in REMOTE_PREFIXES)


def to_remote_path(path: str) -> str:
    """Normalize remote path. Treats 'workspace/' as the remote current working directory (CWD).
    - If path starts with '/' (e.g. 'muse:/memory', 'muse:/workspace'), treated as VM root path.
    - If path starts with 'workspace', kept as is.
    - If path is empty, '.' or omitted, defaults to 'workspace'.
    - Otherwise (e.g. 'spaces', 'downloads/ticker'), automatically prefixed with 'workspace/'.
    """
    p = path.strip()
    for pref in REMOTE_PREFIXES:
        if p.startswith(pref):
            p = p[len(pref) :]
            break

    p = p.replace("\\", "/")
    if p.startswith("/"):
        p = p.lstrip("/")
        return p if p else "."

    if not p or p == ".":
        return "workspace"

    return f"workspace/{p}"


def to_display_remote(path: str) -> str:
    """Format an internal normalized remote path back to a user-friendly display path.
    - If path is inside 'workspace/' (e.g. 'workspace/downloads/a.png'), strips 'workspace/' -> 'downloads/a.png'.
    - If path is exactly 'workspace', returns '.'.
    - If path was accessed via VM root (e.g. 'IDENTITY.md', 'memory/state.json'), returns f"/{path}".
    """
    p = path.strip().replace("\\", "/").lstrip("/")
    if p.startswith("workspace/"):
        return p[len("workspace/") :]
    if p == "workspace":
        return "."
    return f"/{p}"


def call_gateway(method: str, body: dict) -> dict:
    """Call muse-cli raw with a JSON body and return the parsed JSON response."""
    cmd = ["muse-cli", "raw", method, "--body", json.dumps(body, ensure_ascii=False)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        err_msg = res.stderr.strip() or res.stdout.strip()
        raise RuntimeError(f"muse-cli error (exit {res.returncode}): {err_msg}")
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"failed to parse JSON from muse-cli: {res.stdout}") from e


def stat_remote(path: str) -> dict | None:
    """Return stat dict for a normalized remote path, or None if it does not exist."""
    try:
        res = call_gateway("fs.stat", {"path": path})
        return res.get("result")
    except Exception:
        return None


def list_remote_dir(path: str) -> list[dict]:
    """List entries inside a normalized remote directory."""
    res = call_gateway("fs.list", {"path": path})
    return res.get("entries", [])


def list_remote_recursive(dir_path: str) -> list[tuple[str, int]]:
    """Recursively list all files under normalized dir_path. Returns [(rel_path, size)]."""
    base = dir_path.rstrip("/")
    results = []

    def _walk(curr_path: str, rel_prefix: str):
        entries = list_remote_dir(curr_path)
        for e in entries:
            name = e.get("name", "")
            child_rel = f"{rel_prefix}/{name}" if rel_prefix else name
            child_remote = f"{curr_path}/{name}"
            if e.get("type") in ("directory", "dir"):
                _walk(child_remote, child_rel)
            else:
                results.append((child_rel, e.get("size", 0)))

    _walk(base, "")
    return results


def upload_single_file(
    local_path: Path,
    remote_file_path: str,
    force: bool,
    quiet: bool,
    omit_skipped: bool,
    verbose: bool,
) -> str:
    """Upload a single file to Muse workspace using fs.write. Returns 'copied', 'skipped', or 'failed'."""
    if not local_path.is_file():
        return "skipped"

    display_rem = f"muse:{to_display_remote(remote_file_path)}"
    # Skip if target remote file already exists unless force is specified
    if not force:
        stat_res = stat_remote(remote_file_path)
        if verbose:
            print(f"[debug] stat_remote('{remote_file_path}') = {stat_res}", file=sys.stderr)
        if stat_res is not None:
            if not quiet and not omit_skipped:
                print(f"+ muse-cli-w cp {local_path} {display_rem} (skipped)")
            return "skipped"

    file_size = local_path.stat().st_size
    with open(local_path, "rb") as f:
        is_first = True
        offset = 0
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk and not is_first:
                break

            if verbose:
                print(f"[debug] fs.write chunk offset={offset} len={len(chunk)} (total {file_size})", file=sys.stderr)

            b64_data = base64.b64encode(chunk).decode("ascii")
            body = {
                "path": remote_file_path,
                "data_base64": b64_data,
                "overwrite": force if is_first else False,
                "append": not is_first,
                "create_parent": True,
            }
            try:
                res = call_gateway("fs.write", body)
                if not res.get("ok"):
                    err = res.get("error", "unknown error")
                    print(f"error: failed to write {display_rem}: {err}", file=sys.stderr)
                    return "failed"
            except Exception as e:
                print(f"error: failed to write {display_rem}: {e}", file=sys.stderr)
                return "failed"

            offset += len(chunk)
            is_first = False
            if len(chunk) < CHUNK_SIZE:
                break

    if not quiet:
        print(f"+ muse-cli-w cp {local_path} {display_rem}")
    return "copied"


def download_single_file(
    remote_path: str,
    local_file: Path,
    force: bool,
    quiet: bool,
    omit_skipped: bool,
    verbose: bool,
) -> str:
    """Download a single file from Muse workspace using fs.read with chunking. Returns 'copied', 'skipped', or 'failed'."""
    display_rem = f"muse:{to_display_remote(remote_path)}"
    # Skip if target local file already exists unless force is specified
    if local_file.exists() and not force:
        if not quiet and not omit_skipped:
            print(f"+ muse-cli-w cp {display_rem} {local_file} (skipped)")
        return "skipped"

    stat_res = stat_remote(remote_path)
    if verbose:
        print(f"[debug] stat_remote('{remote_path}') = {stat_res}", file=sys.stderr)
    remote_size = stat_res.get("size", 0) if stat_res else 0

    local_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = local_file.with_suffix(local_file.suffix + ".tmp")
    offset = 0
    with open(temp_file, "wb") as f:
        while True:
            cur_len = min(CHUNK_SIZE, remote_size - offset) if remote_size > 0 else CHUNK_SIZE
            if cur_len <= 0 and offset > 0:
                break

            if verbose:
                print(f"[debug] fs.read chunk offset={offset} len={cur_len} (remote_size {remote_size})", file=sys.stderr)

            body = {"path": remote_path, "offset": offset, "len": cur_len}
            try:
                read_res = call_gateway("fs.read", body)
            except Exception as e:
                print(f"error: failed to read {display_rem}: {e}", file=sys.stderr)
                if temp_file.exists():
                    temp_file.unlink()
                return "failed"

            res_data = read_res.get("result", {})
            b64_part = res_data.get("data_base64")
            if b64_part:
                chunk_bytes = base64.b64decode(b64_part)
                f.write(chunk_bytes)
                offset += len(chunk_bytes)

            if res_data.get("eof") or not b64_part or (remote_size > 0 and offset >= remote_size):
                break

    temp_file.replace(local_file)
    if not quiet:
        print(f"+ muse-cli-w cp {display_rem} {local_file}")
    return "copied"


def do_cp_preset(
    preset_name: str,
    dest: str,
    force: bool,
    quiet: bool,
    omit_skipped: bool,
    verbose: bool,
):
    """Download all assets from a library preset."""
    local_dest = Path(dest)
    local_dest.mkdir(parents=True, exist_ok=True)
    res = call_gateway("fs.library", {"preset": preset_name})
    entries = res.get("result", {}).get("entries", [])
    if not entries:
        if not quiet:
            print(f"No items found for preset '{preset_name}'.")
        return

    for item in entries:
        raw_path = item.get("path", "").lstrip("/")
        name = item.get("name") or raw_path.split("/")[-1]
        out_file = local_dest / name
        download_single_file(raw_path, out_file, force, quiet, omit_skipped, verbose)


def do_cp_upload(
    sources: list[str],
    dest: str,
    recursive: bool,
    force: bool,
    quiet: bool,
    omit_skipped: bool,
    verbose: bool,
):
    """Copy local sources to remote destination."""
    dest_path = to_remote_path(dest)
    dest_stat = stat_remote(dest_path)
    dest_is_dir = (
        dest_stat is not None and dest_stat.get("kind") in ("directory", "dir")
    ) or dest.endswith("/") or ("." not in dest_path.split("/")[-1])

    expanded_files = []
    for s in sources:
        matched = glob.glob(s)
        if not matched:
            p = Path(s)
            if p.exists():
                matched = [str(p)]
            else:
                print(f"Error: Local path not found: {s}", file=sys.stderr)
                sys.exit(1)
        for m in matched:
            mp = Path(m)
            if mp.is_dir():
                if not recursive:
                    print(f"omitting directory '{m}' (use -r to copy recursively)", file=sys.stderr)
                    continue
                dest_top_name = Path(dest_path).name
                src_top_name = mp.name
                trailing_slash = m.endswith("/") or m.endswith(os.sep)
                same_name = (dest_top_name == src_top_name)
                nest = (len(matched) > 1) or (not same_name and not trailing_slash and dest_is_dir)
                base_dir = mp.parent if nest else mp
                for root, _, files in os.walk(mp):
                    for file in files:
                        full_p = Path(root) / file
                        rel_p = full_p.relative_to(base_dir)
                        expanded_files.append((full_p, rel_p))
            elif mp.is_file():
                expanded_files.append((mp, Path(mp.name)))

    if not expanded_files:
        return

    is_multi = len(expanded_files) > 1
    if is_multi and not dest_is_dir:
        dest_is_dir = True

    for src_file, rel_path in expanded_files:
        if dest_is_dir:
            rem_file = f"{dest_path.rstrip('/')}/{rel_path.as_posix()}"
        else:
            rem_file = dest_path

        upload_single_file(src_file, rem_file, force, quiet, omit_skipped, verbose)


def do_cp_download(
    sources: list[str],
    dest: str,
    recursive: bool,
    force: bool,
    quiet: bool,
    omit_skipped: bool,
    verbose: bool,
):
    """Copy remote sources to local destination."""
    local_dest = Path(dest)
    dest_already_dir = local_dest.is_dir() or str(dest).endswith(os.sep) or str(dest).endswith("/")
    dest_is_dir = dest_already_dir or len(sources) > 1

    remote_files_to_get = []  # list of (remote_full_path, local_relative_path)

    for s in sources:
        r_path = to_remote_path(s)
        has_wildcard = "*" in r_path or "?" in r_path

        if has_wildcard:
            dest_is_dir = True
            parent_dir = str(Path(r_path).parent).replace("\\", "/")
            pattern = Path(r_path).name
            entries = list_remote_dir(parent_dir if parent_dir != "." else "workspace")
            matched = [e["name"] for e in entries if fnmatch.fnmatch(e.get("name", ""), pattern)]
            if not matched:
                if not quiet:
                    print(f"Warning: No remote files matched '{s}'", file=sys.stderr)
            for m in matched:
                base_dir = parent_dir if parent_dir != "." else "workspace"
                full_rem = f"{base_dir.rstrip('/')}/{m}"
                remote_files_to_get.append((full_rem, Path(m)))
        else:
            r_stat = stat_remote(r_path)
            if r_stat and r_stat.get("kind") in ("directory", "dir"):
                if not recursive:
                    print(f"omitting directory 'muse:{to_display_remote(r_path)}' (use -r to copy recursively)", file=sys.stderr)
                    continue
                dest_is_dir = True
                dir_entries = list_remote_recursive(r_path)
                top_name = Path(r_path).name

                trailing_slash = s.endswith("/") or s.endswith(os.sep)
                same_name = (local_dest.name == top_name)
                should_nest = dest_already_dir and not same_name and not trailing_slash

                for child_rel, _ in dir_entries:
                    full_rem = f"{r_path.rstrip('/')}/{child_rel}"
                    if should_nest:
                        rel_out = Path(top_name) / child_rel
                    else:
                        rel_out = Path(child_rel)
                    remote_files_to_get.append((full_rem, rel_out))
            elif r_stat:
                remote_files_to_get.append((r_path, Path(Path(r_path).name)))
            else:
                print(f"Error: Path not found: 'muse:{to_display_remote(r_path)}'", file=sys.stderr)

    if not remote_files_to_get:
        return

    if dest_is_dir:
        local_dest.mkdir(parents=True, exist_ok=True)

    for rem_path, rel_local in remote_files_to_get:
        if dest_is_dir:
            out_file = local_dest / rel_local
        else:
            out_file = local_dest

        download_single_file(rem_path, out_file, force, quiet, omit_skipped, verbose)


def cmd_cp(args):
    """cp [OPTIONS] SOURCE... DEST"""
    force = getattr(args, "force", False)
    verbose = getattr(args, "verbose", False)
    quiet = getattr(args, "quiet", False)
    omit_skipped = getattr(args, "omit_skipped", False)

    if args.media:
        dest = args.paths[0] if args.paths else "./media"
        do_cp_preset("media", dest, force, quiet, omit_skipped, verbose)
        return
    elif args.artifacts:
        dest = args.paths[0] if args.paths else "./artifacts"
        do_cp_preset("artifacts", dest, force, quiet, omit_skipped, verbose)
        return

    if len(args.paths) < 2:
        print("Error: cp requires at least one SOURCE and one DEST.", file=sys.stderr)
        sys.exit(1)

    sources = args.paths[:-1]
    dest = args.paths[-1]

    src_remote = any(is_remote(s) for s in sources)
    dest_remote = is_remote(dest)

    if src_remote and dest_remote:
        print("Error: remote-to-remote copy is not directly supported.", file=sys.stderr)
        sys.exit(1)
    elif not src_remote and not dest_remote:
        print("Tip: Both paths are local; use regular system 'cp'.", file=sys.stderr)
        sys.exit(1)
    elif not src_remote and dest_remote:
        # Local -> Remote (Upload)
        do_cp_upload(sources, dest, args.recursive, force, quiet, omit_skipped, verbose)
    else:
        # Remote -> Local (Download)
        do_cp_download(sources, dest, args.recursive, force, quiet, omit_skipped, verbose)


def print_dir_listing(target: str, entries: list[dict], long: bool, show_header: bool = False):
    if show_header:
        disp = to_display_remote(target)
        if disp == ".":
            header = "muse:"
        elif disp == "/.":
            header = "muse:/"
        else:
            header = f"muse:{disp}"
        print(f"{header}:")

    for entry in sorted(entries, key=lambda x: x.get("name", "")):
        name = entry.get("name", "")
        is_dir = entry.get("type") in ("dir", "directory")
        name_display = f"{name}/" if is_dir else name

        if not long:
            print(name_display)
        else:
            mode_str = "drwxr-xr-x" if is_dir else "-rw-r--r--"
            nlink = 2 if is_dir else 1
            owner_group = "muse muse"
            size = entry.get("size")
            size_str = f"{size:>8d}" if size is not None else ("    4096" if is_dir else "       0")
            mtime = entry.get("modifiedAt") or ""
            print(f"{mode_str} {nlink:2d} {owner_group} {size_str} {mtime:<24} {name_display}")


def handle_ls_not_found(path_str: str):
    """Print unix-style error message and exit when a path is not found."""
    print(f"muse-cli-w ls: cannot access '{path_str}': No such file or directory", file=sys.stderr)
    sys.exit(2)


def cmd_cat(args):
    """Dump remote file content to stdout. Directory input is an error."""
    raw_path = args.path
    target = to_remote_path(raw_path)
    verbose = getattr(args, "verbose", False)

    stat_res = stat_remote(target)
    if verbose:
        print(f"[debug] stat_remote('{target}') = {stat_res}", file=sys.stderr)
    if stat_res is None:
        print(f"muse-cli-w cat: '{raw_path}': No such file or directory", file=sys.stderr)
        sys.exit(1)
    if stat_res.get("kind") in ("directory", "dir"):
        print(f"muse-cli-w cat: '{raw_path}': Is a directory", file=sys.stderr)
        sys.exit(1)

    remote_size = stat_res.get("size", 0) or 0
    offset = 0
    out = getattr(sys.stdout, "buffer", sys.stdout)
    while True:
        cur_len = min(CHUNK_SIZE, remote_size - offset) if remote_size > 0 else CHUNK_SIZE
        if cur_len <= 0 and offset > 0:
            break

        if verbose:
            print(f"[debug] fs.read chunk offset={offset} len={cur_len} (remote_size {remote_size})", file=sys.stderr)

        body = {"path": target, "offset": offset, "len": cur_len}
        try:
            read_res = call_gateway("fs.read", body)
        except Exception as e:
            print(f"muse-cli-w cat: '{raw_path}': {e}", file=sys.stderr)
            sys.exit(1)

        res_data = read_res.get("result", {})
        b64_part = res_data.get("data_base64")
        if b64_part:
            chunk_bytes = base64.b64decode(b64_part)
            if isinstance(out, type(sys.stdout)):
                out.write(chunk_bytes.decode("utf-8", errors="replace"))
            else:
                out.write(chunk_bytes)
            offset += len(chunk_bytes)

        if res_data.get("eof") or not b64_part or (remote_size > 0 and offset >= remote_size):
            break

    try:
        out.flush()
    except Exception:
        pass


def cmd_ls(args):
    """List entries in a remote workspace path or preset."""
    if args.media:
        preset = "media"
    elif args.artifacts:
        preset = "artifacts"
    elif args.recent:
        preset = "recents"
    else:
        preset = None

    if preset:
        try:
            res = call_gateway("fs.library", {"preset": preset})
        except Exception as e:
            print(f"muse-cli-w ls: error querying preset '{preset}': {e}", file=sys.stderr)
            sys.exit(1)
        if getattr(args, "format", "text") == "json":
            print(json.dumps(res, indent=2, ensure_ascii=False))
            return
        entries = res.get("result", {}).get("entries", [])
        print_dir_listing(f"[preset:{preset}]", entries, getattr(args, "long", False), show_header=True)
        return

    target = to_remote_path(args.path)

    if getattr(args, "recursive", False):
        dirs_to_visit = [target]
        all_results = []
        is_first = True
        while dirs_to_visit:
            curr = dirs_to_visit.pop(0)
            try:
                res = call_gateway("fs.list", {"path": curr})
            except Exception as e:
                if is_first and ("not_found" in str(e) or "path not found" in str(e)):
                    handle_ls_not_found(args.path)
                print(f"muse-cli-w ls: cannot access 'muse:{to_display_remote(curr)}': {e}", file=sys.stderr)
                continue

            entries = res.get("entries", [])
            all_results.append({"path": curr, "entries": entries})

            if getattr(args, "format", "text") != "json":
                if not is_first:
                    print()
                print_dir_listing(curr, entries, getattr(args, "long", False), show_header=True)
                is_first = False

            for e in sorted(entries, key=lambda x: x.get("name", "")):
                if e.get("type") in ("dir", "directory"):
                    child_path = f"{curr.rstrip('/')}/{e.get('name')}"
                    dirs_to_visit.append(child_path)

        if getattr(args, "format", "text") == "json":
            print(json.dumps(all_results, indent=2, ensure_ascii=False))
        return

    try:
        res = call_gateway("fs.list", {"path": target})
    except Exception as e:
        if "not_found" in str(e) or "path not found" in str(e):
            handle_ls_not_found(args.path)
        else:
            print(f"muse-cli-w ls: {e}", file=sys.stderr)
            sys.exit(1)

    if getattr(args, "format", "text") == "json":
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return

    entries = res.get("entries", [])
    print_dir_listing(target, entries, getattr(args, "long", False), show_header=False)


def main():
    parser = argparse.ArgumentParser(
        prog="muse-cli-w",
        description="cp-style file transfer utility between Local and Muse AI workspace",
        formatter_class=PlatformHelpFormatter,
    )
    sub = parser.add_subparsers(dest="subcommand", metavar="<command>")

    # cp/copy command (cp on Linux, copy on Windows; identical behavior)
    for _cmd in ("cp", "copy"):
        if _cmd == "cp":
            _help = "Copy files between local and muse (e.g. cp file.png muse:workspace/)"
        else:
            _help = "Copy files between local and muse (same as cp)"
        p_cp = sub.add_parser(_cmd, help=_help)
        p_cp.add_argument("-r", "-R", "--recursive", action="store_true", help="Copy directories recursively")
        p_cp.add_argument("-f", "--force", action="store_true", help="Overwrite existing files without prompt")
        p_cp.add_argument("-q", dest="omit_skipped", action="store_true", help="Omit (skipped) messages")
        p_cp.add_argument("--quiet", dest="quiet", action="store_true", help="Suppress all messages including copied files")
        p_cp.add_argument("-v", "--verbose", action="store_true", help="Debug logging for developers")
        p_cp.add_argument("-m", "--media", action="store_true", help="Download media preset")
        p_cp.add_argument("-a", "--artifacts", action="store_true", help="Download artifacts preset")
        p_cp.add_argument("paths", nargs="*", metavar="PATH", help="SOURCE... DEST (use 'muse:' prefix for remote)")
        p_cp.set_defaults(func=cmd_cp)

    # ls command
    p_ls = sub.add_parser("ls", help="List files in Muse workspace directory")
    p_ls.add_argument("path", nargs="?", default="", help="Remote path (default: workspace root)")
    p_ls.add_argument("-r", "-R", "--recursive", action="store_true", help="List subdirectories recursively")
    p_ls.add_argument("--media", action="store_true", help="List media preset")
    p_ls.add_argument("--artifacts", action="store_true", help="List artifacts preset")
    p_ls.add_argument("--recent", action="store_true", help="List recents preset")
    p_ls.add_argument("-l", "--long", action="store_true", help="Show long metadata")
    p_ls.add_argument("--format", choices=["text", "json"], default="text", help="Output format (text, json)")
    p_ls.set_defaults(func=cmd_ls)

    # dir command (Windows-style alias, same behavior as ls -l)
    p_dir = sub.add_parser("dir", help="List files in long format (same as ls -l)")
    p_dir.add_argument("path", nargs="?", default="", help="Remote path (default: workspace root)")
    p_dir.add_argument("-r", "-R", "--recursive", action="store_true", help="List subdirectories recursively")
    p_dir.add_argument("--media", action="store_true", help="List media preset")
    p_dir.add_argument("--artifacts", action="store_true", help="List artifacts preset")
    p_dir.add_argument("--recent", action="store_true", help="List recents preset")
    p_dir.add_argument("-l", "--long", action="store_true", default=True, help="Show long metadata (always enabled for dir)")
    p_dir.add_argument("--format", choices=["text", "json"], default="text", help="Output format (text, json)")
    p_dir.set_defaults(func=cmd_ls, long=True)

    # cat/type command (cat on Linux, type on Windows; identical behavior)
    for _cmd in ("cat", "type"):
        if _cmd == "cat":
            _help = "Print remote file content to stdout"
        else:
            _help = "Print remote file content to stdout (same as cat)"
        p_cat = sub.add_parser(_cmd, help=_help)
        p_cat.add_argument("path", help="Remote file path (e.g. muse:notes/todo.md)")
        p_cat.add_argument("-v", "--verbose", action="store_true", help="Debug logging for developers")
        p_cat.set_defaults(func=cmd_cat)

    # If first arg is not a known subcommand or help, assume 'cp' by default
    argv = sys.argv[1:]
    if argv and argv[0] not in ("-h", "--help", "cp", "copy", "ls", "dir", "cat", "type", "upload", "download"):
        argv = ["cp"] + argv

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
