#!/usr/bin/env python3
import os, struct, threading, queue, shutil, subprocess, stat, glob
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# ============================ Config ============================
HOME = os.path.expanduser("~")
TOOLS_DIR = os.path.join(HOME, ".local", "share", "arma_pbo_tools")
BIN_DIR   = os.path.join(HOME, ".local", "bin")

# path files (exe locations + chosen Wine prefix)
CPBO_PATH_FILE   = os.path.join(TOOLS_DIR, "cpbo.path")     # stores ExtractPbo.exe path
UNRAP_PATH_FILE  = os.path.join(TOOLS_DIR, "unrap.path")    # stores DeRap.exe path
PREFIX_PATH_FILE = os.path.join(TOOLS_DIR, "wineprefix.path")

# legacy copy (not used if path files exist)
CPBO_EXE_LEGACY  = os.path.join(TOOLS_DIR, "cpbo.exe")
UNRAP_EXE_LEGACY = os.path.join(TOOLS_DIR, "unRap.exe")

# Standalone installers (adjust versions when needed)
EXTRACTPBO_URL   = "https://mikero.bytex.digital/api/download?filename=ExtractPbo.2.35.9.55.Installer.exe"
DERAP_URL        = "https://mikero.bytex.digital/api/download?filename=DeRap.1.86.8.75.Installer.exe"
DEPBO_URL        = "https://mikero.bytex.digital/api/download?filename=DePbo.9.98.0.23.Installer.exe"
DEOGG_URL        = "https://mikero.bytex.digital/api/download?filename=DeOgg.1.04.7.95.Installer.exe"

EXTRACTPBO_LOCAL = os.path.join(TOOLS_DIR, "ExtractPbo_Installer.exe")
DERAP_LOCAL      = os.path.join(TOOLS_DIR, "DeRap_Installer.exe")
DEPBO_LOCAL      = os.path.join(TOOLS_DIR, "DePbo_Installer.exe")
DEOGG_LOCAL      = os.path.join(TOOLS_DIR, "DeOgg_Installer.exe")

APT_PKGS = ["wine-stable", "winbind", "cabextract", "p7zip-full"]

MPMISSIONS_CANDIDATES = [
    "~/.local/share/Steam/steamapps/common/ARMA Cold War Assault/MPMissions",
    "~/.local/share/Steam/steamapps/common/Arma Cold War Assault/MPMissions",
    "~/.steam/steam/steamapps/common/ARMA Cold War Assault/MPMissions",
    "~/.steam/steam/steamapps/common/Arma Cold War Assault/MPMissions",
    "~/Steam/steamapps/common/ARMA Cold War Assault/MPMissions",
    "~/Steam/steamapps/common/Arma Cold War Assault/MPMissions",
    "~/.wine/drive_c/Program Files/Bohemia Interactive/Arma Cold War Assault/MPMissions",
    "~/.wine/drive_c/Program Files (x86)/Bohemia Interactive/Arma Cold War Assault/MPMissions",
    "~/.wine64/drive_c/Program Files/Bohemia Interactive/Arma Cold War Assault/MPMissions",
    "~/.wine64/drive_c/Program Files (x86)/Bohemia Interactive/Arma Cold War Assault/MPMissions",
]

# ============================ Utils =============================
def have_cmd(cmd): return shutil.which(cmd) is not None

def ensure_dirs():
    os.makedirs(TOOLS_DIR, exist_ok=True)
    os.makedirs(BIN_DIR, exist_ok=True)

def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f: return f.read().strip()
    except Exception:
        return ""

def write_text(path, val):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f: f.write(val)

def get_selected_prefix():
    p = read_text(PREFIX_PATH_FILE)
    if p and os.path.isdir(p): return p
    return os.environ.get("WINEPREFIX", os.path.join(HOME, ".wine"))

def set_selected_prefix(prefix_dir):
    write_text(PREFIX_PATH_FILE, prefix_dir)

def run_cmd(cmd, log, check=False, env=None):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    if p.stdout: log(p.stdout.rstrip())
    if check and p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)} (exit {p.returncode})")
    return p

def write_executable(path, content):
    with open(path, "w") as f: f.write(content)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)

def path_contains_local_bin():
    target = os.path.realpath(BIN_DIR)
    for part in os.environ.get("PATH", "").split(os.pathsep):
        if os.path.realpath(os.path.expanduser(part)) == target:
            return True
    return False

def http_download(url, dest_path, log, timeout=60):
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=timeout) as r, open(dest_path, "wb") as w:
            total = 0
            while True:
                chunk = r.read(8192)
                if not chunk: break
                w.write(chunk)
                total += len(chunk)
        log(f"Downloaded {os.path.basename(dest_path)} ({total} bytes) → {dest_path}")
    except HTTPError as e:
        raise RuntimeError(f"HTTP error {e.code} for {url} (site may require login or link changed).")
    except URLError as e:
        raise RuntimeError(f"Network error for {url}: {e.reason}")
    except Exception as e:
        raise RuntimeError(f"Download failed: {e}")

def pick_default_mpmissions():
    for p in MPMISSIONS_CANDIDATES:
        real = os.path.expanduser(p)
        if os.path.isdir(real): return real
    return HOME

# ========== Minimal fallback (UNCOMPRESSED PBOs only) ===========
def read_cstr(f):
    b = bytearray()
    while True:
        c = f.read(1)
        if not c: raise EOFError("Unexpected EOF while reading C-string")
        if c == b'\x00': return b.decode('ascii', errors='ignore')
        b += c

def parse_header_and_props(f):
    entries = []
    while True:
        name = read_cstr(f)
        if name == "": break
        fields = f.read(20)
        if len(fields) != 20: raise EOFError("Truncated header")
        packing, orig_sz, res1, ts, data_sz = struct.unpack("<IIIII", fields)
        entries.append((name, packing, orig_sz, data_sz))
    props = bytearray()
    while True:
        c = f.read(1)
        if not c: raise EOFError("EOF before properties terminator")
        props += c
        if props.endswith(b"\x00\x00"): break
    return entries

def extract_uncompressed(pbo_path, outdir, log_fn, progress_fn):
    os.makedirs(outdir, exist_ok=True)
    with open(pbo_path, 'rb') as f:
        entries = parse_header_and_props(f)
        total_files = len(entries)
        total_bytes = sum(e[3] for e in entries) if total_files else 0
        done_files = done_bytes = 0
        for name, packing, orig_sz, data_sz in entries:
            if packing != 0:
                raise RuntimeError(f"'{name}' is compressed (packing={packing}). Use cpbo.")
            data = f.read(data_sz)
            if len(data) != data_sz: raise EOFError(f"Truncated data for {name}")
            out_path = os.path.join(outdir, name.replace("\\", "/"))
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "wb") as w: w.write(data)
            done_files += 1; done_bytes += data_sz
            log_fn(f"✔ {name}  ({data_sz} bytes)")
            frac_files = done_files/total_files if total_files else 1.0
            frac_bytes = (done_bytes/total_bytes) if total_bytes else 1.0
            progress_fn((frac_files + frac_bytes)/2.0)
    log_fn(f"✅ Extracted to: {outdir}")

# =================== cpbo / unRap helpers ======================
def cpbo_extract(pbo_path, outdir, log):
    return run_cmd(["cpbo", "-e", pbo_path, outdir], log, check=True)
def cpbo_pack(folder, out_pbo, log):
    return run_cmd(["cpbo", "-p", folder, out_pbo], log, check=True)
def unrap_file(path, log):
    return run_cmd(["unrap", path], log, check=True)

def inject_respawn_stub(folder, delay=5):
    path = os.path.join(folder, "description.ext")
    lines = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.read().splitlines()
    keys = {"respawn", "respawnDelay", "respawnDialog"}
    new_lines = [ln for ln in lines if not any(ln.strip().startswith(k) for k in keys)]
    stub = [
        "// --- injected by tool ---",
        "respawn = 3;",
        f"respawnDelay = {int(delay)};",
        "respawnDialog = 0;",
        "// --- end injected ---",
    ]
    if new_lines and new_lines[-1].strip(): new_lines.append("")
    new_lines.extend(stub)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines) + "\n")

# ============== Wine scanning & linking (in-place) ==============
def score_candidate(path, target):  # target: "extractpbo" or "derap"
    p = path.replace("\\", "/")
    bn = os.path.basename(p).lower()
    s = 0
    if target == "extractpbo" and bn == "extractpbo.exe": s += 100
    if target == "derap"      and bn == "derap.exe":      s += 100
    if "/bin/" in p.lower(): s += 50
    if "/mikero" in p.lower(): s += 10
    bad_bits = ["docs/", "/doc/", "/downloads/", "uninstall", "unins", "derapgui"]
    if any(b in p.lower() for b in bad_bits): s -= 200
    return s

def find_best_tool(prefix, target, log):
    base_dc = os.path.join(prefix, "drive_c")
    log(f"Using Wine prefix: {prefix}")
    globs = [
        os.path.join(base_dc, "Program Files", "**", "Mikero*", "**", "*.exe"),
        os.path.join(base_dc, "Program Files (x86)", "**", "Mikero*", "**", "*.exe"),
    ]
    hits = []
    for g in globs:
        for hit in glob.iglob(g, recursive=True):
            bn = os.path.basename(hit).lower()
            if target == "extractpbo" and "extractpbo" in bn:
                hits.append(hit)
            elif target == "derap" and ("derap" in bn or bn == "unrap.exe"):
                hits.append(hit)
    if not hits:
        log(f"No candidates found for {target}.")
        return None
    scored = sorted(((score_candidate(h, target), h) for h in hits), reverse=True)
    log(f"Top {min(8, len(scored))} candidates for {target}:")
    for sc, h in scored[:8]:
        log(f"  [{sc}] {h}")
    best = scored[0][1]
    if score_candidate(best, target) < 0:
        log("Best candidate looks wrong (negative score).")
        return None
    return best

# ================= Runtime verification =========================
def file_exists_any(dirpath, names):
    for n in names:
        if os.path.exists(os.path.join(dirpath, n)): return True
    return False

def verify_runtime(exe_path, log, warn_dialog=True):
    """
    Checks for DePbo/DePbo64 and DeOgg/DeOgg64 next to the tool exe.
    Returns True if runtimes look OK, else False (and logs guidance).
    """
    if not exe_path or not os.path.isfile(exe_path):
        log("Runtime check skipped: tool exe not set.")
        return False
    bdir = os.path.dirname(exe_path)
    has_depbo = file_exists_any(bdir, ["DePbo64.dll", "DePbo.dll"])
    has_deogg = file_exists_any(bdir, ["deOgg64.dll", "DeOgg64.dll", "deOgg.dll", "DeOgg.dll"])
    if has_depbo and has_deogg:
        log("Runtime check: OK (DePbo and DeOgg present).")
        return True
    msg = "Missing runtime DLLs detected.\n\n" \
          f"Checked: {bdir}\n" \
          f"Found DePbo*: {has_depbo}\n" \
          f"Found DeOgg*: {has_deogg}\n\n" \
          "Fix:\n" \
          " • Install DePbo runtime and DeOgg runtime (buttons in Setup), or\n" \
          " • Manually place the DLLs next to the EXEs, then Link tools."
    log(msg.replace("\n", " "))
    if warn_dialog:
        messagebox.showwarning("Missing Mikero runtime", msg)
    return False

# ===================== Wrappers with path fix ===================
def create_or_repair_wrappers(log):
    """Wrappers cd into the exe dir, do winepath conversion, and emulate cpbo flags."""
    ensure_dirs()

    # ---------- cpbo ----------
    write_executable(os.path.join(BIN_DIR, "cpbo"), f"""#!/usr/bin/env bash
set -euo pipefail
TOOLS_DIR="{TOOLS_DIR}"
PREF_EXE="$TOOLS_DIR/cpbo.path"
PREF_WP="$TOOLS_DIR/wineprefix.path"
LEG="{CPBO_EXE_LEGACY}"

EXE="$LEG"
if [ -f "$PREF_EXE" ]; then EXE="$(cat "$PREF_EXE")"; fi
if [ ! -f "$EXE" ]; then echo "cpbo exe target not found: $EXE"; exit 3; fi
if ! command -v wine >/dev/null 2>&1; then echo "wine not found."; exit 2; fi
if [ -f "$PREF_WP" ]; then export WINEPREFIX="$(cat "$PREF_WP")"; fi

EXE_DIR="$(dirname "$EXE")"
EXE_BN="$(basename "$EXE" | tr '[:upper:]' '[:lower:]')"
cd "$EXE_DIR"
export WINEDEBUG=-all

conv() {{
  local p="$1"
  if command -v winepath >/dev/null 2>&1; then
    winepath -w "$p" 2>/dev/null || echo "Z:${{p//\\//\\\\}}"
  else
    echo "Z:${{p//\\//\\\\}}"
  fi
}}

echo "[cpbo wrapper] WINEPREFIX=${{WINEPREFIX:-unset}}"
echo "[cpbo wrapper] EXE_DIR=$EXE_DIR"
echo "[cpbo wrapper] EXE=$EXE"
echo "[cpbo wrapper] ARGS: $@"

if [[ "$EXE_BN" == "extractpbo.exe" ]]; then
  # emulate cpbo CLI
  if [[ $# -ge 1 && "$1" == "-e" ]]; then
    shift
    if [[ $# -lt 1 ]]; then echo "usage: cpbo -e <pbo> [outdir]"; exit 64; fi
    SRC="$1"; DST="${2:-}"
    SRCW="$(conv "$SRC")"
    if [[ -n "$DST" ]]; then
      DSTW="$(conv "$DST")"
      exec wine "$EXE" "$SRCW" "$DSTW"
    else
      exec wine "$EXE" "$SRCW"
    fi
  elif [[ $# -ge 1 && "$1" == "-p" ]]; then
    shift
    MAKE="$EXE_DIR/MakePbo.exe"
    if [[ ! -f "$MAKE" ]]; then
      echo "MakePbo.exe not found in $EXE_DIR (install Mikero MakePbo to pack)."; exit 65
    fi
    if [[ $# -lt 2 ]]; then echo "usage: cpbo -p <folder> <out.pbo>"; exit 66; fi
    FOLDW="$(conv "$1")"; OUTW="$(conv "$2")"
    exec wine "$MAKE" "$FOLDW" "$OUTW"
  else
    # allow plain: cpbo <pbo> [outdir]
    if [[ $# -ge 1 ]]; then
      A1W="$(conv "$1")"
      if [[ $# -ge 2 ]]; then A2W="$(conv "$2")"; exec wine "$EXE" "$A1W" "$A2W"; fi
      exec wine "$EXE" "$A1W"
    fi
    exec wine "$EXE" "$@"
  fi
else
  # Real cpbo.exe - pass through
  exec wine "$EXE" "$@"
fi
""")

    # ---------- unrap ----------
    write_executable(os.path.join(BIN_DIR, "unrap"), f"""#!/usr/bin/env bash
set -euo pipefail
TOOLS_DIR="{TOOLS_DIR}"
PREF_EXE="$TOOLS_DIR/unrap.path"
PREF_WP="$TOOLS_DIR/wineprefix.path"
LEG="{UNRAP_EXE_LEGACY}"

EXE="$LEG"
if [ -f "$PREF_EXE" ]; then EXE="$(cat "$PREF_EXE")"; fi
if [ ! -f "$EXE" ]; then echo "unRap exe target not found: $EXE"; exit 3; fi
if ! command -v wine >/dev/null 2>&1; then echo "wine not found."; exit 2; fi
if [ -f "$PREF_WP" ]; then export WINEPREFIX="$(cat "$PREF_WP")"; fi

EXE_DIR="$(dirname "$EXE")"
cd "$EXE_DIR"
export WINEDEBUG=-all

conv() {{
  local p="$1"
  if command -v winepath >/dev/null 2>&1; then
    winepath -w "$p" 2>/dev/null || echo "Z:${{p//\\//\\\\}}"
  else
    echo "Z:${{p//\\//\\\\}}"
  fi
}}

echo "[unrap wrapper] WINEPREFIX=${{WINEPREFIX:-unset}}"
echo "[unrap wrapper] EXE_DIR=$EXE_DIR"
echo "[unrap wrapper] EXE=$EXE"
echo "[unrap wrapper] ARGS: $@"

NEWARGS=()
for a in "$@"; do
  if [[ "$a" == -* ]]; then
    NEWARGS+=("$a")
  else
    NEWARGS+=("$(conv "$a")")
  fi
done
exec wine "$EXE" "${{NEWARGS[@]}}"
""")

    # ---------- unpbo stub ----------
    write_executable(os.path.join(BIN_DIR, "unpbo"), """#!/usr/bin/env bash
set -euo pipefail
echo "No native 'unpbo' bundled. Use cpbo (extract) or MakePbo (pack)."
exit 1
""")

    log(f"Wrappers ready in {BIN_DIR}.")
    if not path_contains_local_bin():
        log("PATH note: ~/.local/bin is NOT in your PATH. Add it for new shells:\n  echo 'export PATH=\"$HOME/.local/bin:$PATH\"' >> ~/.bashrc && source ~/.bashrc")

# ============== Wine scanning & linking (in-place) ==============
def link_installed_tools(log):
    ensure_dirs()
    prefix = get_selected_prefix()
    cp = find_best_tool(prefix, "extractpbo", log)
    ur = find_best_tool(prefix, "derap", log)
    if cp:
        write_text(CPBO_PATH_FILE, cp)
        log(f"Linked cpbo (in-place): {cp}  →  {CPBO_PATH_FILE}")
        verify_runtime(cp, log, warn_dialog=False)
    else:
        log("❌ Could not locate ExtractPbo.exe. Did the installer finish?")
    if ur:
        write_text(UNRAP_PATH_FILE, ur)
        log(f"Linked unRap (in-place): {ur}  →  {UNRAP_PATH_FILE}")
        verify_runtime(ur, log, warn_dialog=False)
    else:
        log("❌ Could not locate DeRap.exe. Did the installer finish?")

# ============================ GUI ===============================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Arma PBO Tools — Install + Extract (cpbo preferred)")
        self.minsize(1080, 780)
        ensure_dirs()
        self.default_mpm = pick_default_mpmissions()
        self.log_q = queue.Queue()
        self._build_ui()
        self.after(150, self.refresh_status)
        self.after(50, self._drain_log)
        self._first_run_notes()

    def _build_ui(self):
        root = ttk.Frame(self); root.pack(fill="both", expand=True)
        for c in range(8): root.columnconfigure(c, weight=1)
        for r in range(11): root.rowconfigure(r, weight=0)
        root.rowconfigure(10, weight=1)

        env = ttk.LabelFrame(root, text="Setup"); env.grid(row=0, column=0, columnspan=8, sticky="ew", padx=10, pady=8)
        for c in range(8): env.columnconfigure(c, weight=1)

        # Status
        self.lbl_wine = ttk.Label(env, text="Wine: ?"); self.lbl_wine.grid(row=0, column=0, sticky="w", padx=8)
        self.lbl_cpbo = ttk.Label(env, text="cpbo: ?"); self.lbl_cpbo.grid(row=0, column=1, sticky="w", padx=8)
        self.lbl_unrap= ttk.Label(env, text="unRap: ?"); self.lbl_unrap.grid(row=0, column=2, sticky="w", padx=8)

        # Prefix controls
        ttk.Label(env, text="Wine prefix:").grid(row=1, column=0, sticky="e", padx=6)
        self.prefix_var = tk.StringVar(value=get_selected_prefix())
        pref_row = ttk.Frame(env); pref_row.grid(row=1, column=1, columnspan=5, sticky="ew", padx=6)
        pref_row.columnconfigure(0, weight=1)
        ttk.Entry(pref_row, textvariable=self.prefix_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(pref_row, text="Browse…", command=self.pick_prefix).grid(row=0, column=1, padx=6)
        ttk.Button(env, text="Use This Prefix", command=self.use_prefix).grid(row=1, column=6, sticky="e", padx=6)
        ttk.Button(env, text="Create 64-bit Prefix (~/.wine64) & Use", command=self.create_prefix_win64).grid(row=1, column=7, sticky="e", padx=6)

        # Installers & tools
        ttk.Button(env, text="Install Wine + helpers", command=self.install_wine).grid(row=0, column=3, sticky="e", padx=6)
        ttk.Button(env, text="Install ExtractPbo", command=self.install_extractpbo).grid(row=0, column=4, sticky="e", padx=6)
        ttk.Button(env, text="Install DeRap", command=self.install_derap).grid(row=0, column=5, sticky="e", padx=6)
        ttk.Button(env, text="Install DePbo (runtime)", command=self.install_depbo).grid(row=0, column=6, sticky="e", padx=6)
        ttk.Button(env, text="Install DeOgg (runtime)", command=self.install_deogg).grid(row=0, column=7, sticky="e", padx=6)

        ttk.Button(env, text="Create/Repair Wrappers", command=self.create_wrappers).grid(row=2, column=6, sticky="e", padx=6, pady=6)
        ttk.Button(env, text="Link ExtractPbo & DeRap", command=self.link_tools).grid(row=2, column=7, sticky="e", padx=6, pady=6)

        # Paths
        ttk.Label(root, text="PBO file:").grid(row=2, column=0, sticky="w", padx=10)
        self.pbo_var = tk.StringVar(value=self.default_mpm)  # start at MPMissions
        pbo_row = ttk.Frame(root); pbo_row.grid(row=2, column=1, columnspan=7, sticky="ew", padx=10)
        pbo_row.columnconfigure(0, weight=1)
        ttk.Entry(pbo_row, textvariable=self.pbo_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(pbo_row, text="Browse…", command=self.pick_pbo).grid(row=0, column=1, padx=6)

        ttk.Label(root, text="Output / Mission folder:").grid(row=3, column=0, sticky="w", padx=10)
        self.out_var = tk.StringVar(value=self.default_mpm)
        out_row = ttk.Frame(root); out_row.grid(row=3, column=1, columnspan=7, sticky="ew", padx=10)
        out_row.columnconfigure(0, weight=1)
        ttk.Entry(out_row, textvariable=self.out_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(out_row, text="Choose…", command=self.pick_out).grid(row=0, column=1, padx=6)

        # Actions
        btns = ttk.LabelFrame(root, text="Actions"); btns.grid(row=4, column=0, columnspan=8, sticky="ew", padx=10, pady=8)
        for c in range(8): btns.columnconfigure(c, weight=1)
        self.progress = ttk.Progressbar(btns, mode="determinate")
        self.progress.grid(row=0, column=7, sticky="ew", padx=6, pady=6)
        self.progress.configure(maximum=1.0, value=0.0)

        ttk.Button(btns, text="Extract via tools (cpbo)", command=self.do_extract_cpbo).grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        ttk.Button(btns, text="Pack folder → .pbo (cpbo)", command=self.do_pack_cpbo).grid(row=0, column=1, sticky="ew", padx=6, pady=6)
        ttk.Button(btns, text="DeRap .bin → .cpp (unRap)", command=self.do_unrap).grid(row=0, column=2, sticky="ew", padx=6, pady=6)
        ttk.Button(btns, text="Inject Respawn (description.ext)", command=self.do_inject_respawn).grid(row=0, column=3, sticky="ew", padx=6, pady=6)
        ttk.Button(btns, text="Fallback: Extract UNCOMPRESSED", command=self.do_extract_fallback).grid(row=0, column=4, sticky="ew", padx=6, pady=6)
        ttk.Button(btns, text="Copy Log", command=self.copy_log).grid(row=0, column=5, sticky="ew", padx=6, pady=6)
        ttk.Button(btns, text="Save Log…", command=self.save_log).grid(row=0, column=6, sticky="ew", padx=6, pady=6)

        # Log
        logf = ttk.LabelFrame(root, text="Log"); logf.grid(row=10, column=0, columnspan=8, sticky="nsew", padx=10, pady=(0,10))
        logf.rowconfigure(0, weight=1); logf.columnconfigure(0, weight=1)
        self.log = tk.Text(logf, wrap="word"); self.log.grid(row=0, column=0, sticky="nsew")
        y = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview); y.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=y.set)
        self._log(f"Default MPMissions: {self.default_mpm}")
        self._log(f"Current Wine prefix: {get_selected_prefix()}")

    # ------------- helpers & status -------------
    def _log(self, msg): self.log.insert("end", msg + "\n"); self.log.see("end")
    def _enqueue(self, msg): self.log_q.put(msg)
    def _drain_log(self):
        try:
            while True: self._log(self.log_q.get_nowait())
        except queue.Empty: pass
        finally: self.after(50, self._drain_log)

    def _first_run_notes(self):
        if not path_contains_local_bin():
            self._log("PATH note: ~/.local/bin is NOT in PATH. Add it for new shells:\n  echo 'export PATH=\"$HOME/.local/bin:$PATH\"' >> ~/.bashrc && source ~/.bashrc")

    def copy_log(self):
        txt = self.log.get("1.0", "end-1c")
        self.clipboard_clear(); self.clipboard_append(txt); self.update()
        messagebox.showinfo("Copied", "Log copied to clipboard.")
    def save_log(self):
        path = filedialog.asksaveasfilename(title="Save Log", defaultextension=".txt",
                                            filetypes=[("Text files","*.txt"), ("All files","*.*")])
        if not path: return
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.log.get("1.0", "end-1c"))
        messagebox.showinfo("Saved", f"Log saved to:\n{path}")

    def refresh_status(self):
        def mark(lbl, ok):
            base = lbl.cget("text").split(":")[0]
            lbl.config(text=f"{base}: {'✓' if ok else '✗'}", foreground=("#0a0" if ok else "#a00"))
        mark(self.lbl_wine, have_cmd("wine"))
        mark(self.lbl_cpbo, have_cmd("cpbo"))
        mark(self.lbl_unrap, have_cmd("unrap"))
        self.after(2000, self.refresh_status)

    # ------------- prefix controls -------------
    def pick_prefix(self):
        d = filedialog.askdirectory(title="Select Wine prefix directory", initialdir=HOME)
        if d: self.prefix_var.set(d)
    def use_prefix(self):
        p = self.prefix_var.get().strip()
        if not p: return
        os.makedirs(p, exist_ok=True)
        set_selected_prefix(p)
        self._log(f"Selected Wine prefix: {p}")
    def create_prefix_win64(self):
        if not have_cmd("wine"):
            messagebox.showerror("Wine not found", "Install Wine first (button above).")
            return
        target = os.path.join(HOME, ".wine64")
        os.makedirs(target, exist_ok=True)
        self._log(f"Creating 64-bit Wine prefix at: {target}")
        env = dict(os.environ); env["WINEARCH"] = "win64"; env["WINEPREFIX"] = target
        run_cmd(["wineboot"], self._log, check=False, env=env)
        set_selected_prefix(target)
        self.prefix_var.set(target)
        self._log("64-bit prefix ready and selected.")

    # ------------- installers -------------
    def install_wine(self):
        if not have_cmd("apt"):
            return messagebox.showerror("Unsupported", "Needs apt (Ubuntu/Pop!_OS).")
        pkgs = " ".join(APT_PKGS)
        cmd = f"echo 'Installing: {pkgs}' && sudo apt update && sudo apt install -y {pkgs}; echo; echo 'Close this window when finished.'; bash"
        self._log("Launching terminal to install Wine + helpers…")
        if shutil.which("gnome-terminal"):
            subprocess.Popen(["gnome-terminal", "--", "bash", "-lc", cmd])
        elif shutil.which("xterm"):
            subprocess.Popen(["xterm", "-e", cmd])
        else:
            self._log("No terminal found; run manually:\n" + cmd)
            messagebox.showinfo("Run manually", cmd)

    def _download_and_run(self, url, local_name):
        ensure_dirs()
        prefix = get_selected_prefix()
        env = dict(os.environ); env["WINEPREFIX"] = prefix
        self._log(f"Downloading:\n{url}")
        def run():
            try:
                http_download(url, local_name, self._enqueue)
                self._enqueue(f"Launching installer with Wine (interactive): {local_name}")
                p = subprocess.Popen(["wine", local_name],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
                for line in iter(p.stdout.readline, ''):
                    if not line: break
                    self._enqueue(line.rstrip())
                p.wait()
                self._enqueue(f"Installer exited with code {p.returncode}. Running link step…")
                self.after(0, self.link_tools)
            except Exception as e:
                self._enqueue(f"ERROR: {e}")
                self.after(0, lambda: messagebox.showerror("Installer error", str(e)))
        threading.Thread(target=run, daemon=True).start()

    def install_extractpbo(self): self._download_and_run(EXTRACTPBO_URL, EXTRACTPBO_LOCAL)
    def install_derap(self):      self._download_and_run(DERAP_URL,      DERAP_LOCAL)
    def install_depbo(self):      self._download_and_run(DEPBO_URL,      DEPBO_LOCAL)
    def install_deogg(self):      self._download_and_run(DEOGG_URL,      DEOGG_LOCAL)

    def link_tools(self):
        try:
            link_installed_tools(self._log)
            create_or_repair_wrappers(self._log)
            # After linking, explicitly verify runtimes so you see a clear status now
            cp = read_text(CPBO_PATH_FILE)
            ur = read_text(UNRAP_PATH_FILE)
            verify_runtime(cp, self._log, warn_dialog=True)
            verify_runtime(ur, self._log, warn_dialog=False)
            messagebox.showinfo("Linked", "Tools linked and wrappers ready.\nIf runtime is missing, install DePbo + DeOgg, then Link again.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def create_wrappers(self):
        try:
            create_or_repair_wrappers(self._log)
            messagebox.showinfo(
                "Wrappers ready",
                f"Wrappers created/updated in:\n{BIN_DIR}\n\n"
                "If new shells don't see them, add to ~/.bashrc and reload:\n"
                '  export PATH="$HOME/.local/bin:$PATH"'
            )
        except Exception as e:
            messagebox.showerror("Error creating wrappers", str(e))

    # ------------- file pickers -------------
    def pick_pbo(self):
        initdir = self.default_mpm if os.path.isdir(self.default_mpm) else HOME
        path = filedialog.askopenfilename(
            title="Select .pbo",
            initialdir=initdir,
            filetypes=[("PBO files", "*.pbo"), ("All files", "*.*")]
        )
        if path:
            self.pbo_var.set(path)
            if not self.out_var.get():
                self.out_var.set(os.path.splitext(path)[0])

    def pick_out(self):
        initdir = self.default_mpm if os.path.isdir(self.default_mpm) else HOME
        path = filedialog.askdirectory(title="Select folder", initialdir=initdir)
        if path: self.out_var.set(path)

    # ------------- actions -------------
    def do_extract_cpbo(self):
        pbo = self.pbo_var.get().strip()
        outdir = self.out_var.get().strip() or (os.path.splitext(pbo)[0] if pbo else "")
        if not pbo or not os.path.isfile(pbo):
            return messagebox.showwarning("Pick file", "Choose a valid .pbo first.")
        if not have_cmd("cpbo"):
            return messagebox.showwarning("cpbo missing", "Install ExtractPbo, Link tools, then try again.")
        # Pre-flight runtime check
        cp = read_text(CPBO_PATH_FILE)
        if not verify_runtime(cp, self._log, warn_dialog=True):
            self._log("Aborting extract due to missing runtime.")
            return
        os.makedirs(outdir, exist_ok=True)
        self.progress['value'] = 0.0
        self._log(f"cpbo -e {pbo} {outdir}")
        def run():
            try:
                cpbo_extract(pbo, outdir, self._enqueue)
                self._enqueue("cpbo extraction complete.")
                self.after(0, lambda: messagebox.showinfo("Done", "cpbo extraction complete."))
            except Exception as e:
                if "DePbo64.dll" in str(e) or "DePbo.dll" in str(e) or "DeOgg" in str(e):
                    self._enqueue("Missing runtime detected. Install DePbo + DeOgg in the same prefix, then Link and retry.")
                self._enqueue(f"ERROR: {e}")
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
        threading.Thread(target=run, daemon=True).start()

    def do_pack_cpbo(self):
        folder = self.out_var.get().strip()
        if not folder or not os.path.isdir(folder):
            return messagebox.showwarning("Pick folder", "Choose a mission folder to pack.")
        if not have_cmd("cpbo"):
            return messagebox.showwarning("cpbo missing", "Install ExtractPbo, Link tools, then try again.")
        out_pbo = filedialog.asksaveasfilename(
            title="Save as .pbo",
            initialdir=self.default_mpm,
            defaultextension=".pbo",
            filetypes=[("PBO files","*.pbo")]
        )
        if not out_pbo: return
        self.progress['value'] = 0.0
        self._log(f"cpbo -p {folder} {out_pbo}")
        def run():
            try:
                cpbo_pack(folder, out_pbo, self._enqueue)
                self._enqueue(f"Packed → {out_pbo}")
                self.after(0, lambda: messagebox.showinfo("Done", f"Packed:\n{out_pbo}"))
            except Exception as e:
                if "MakePbo.exe" in str(e):
                    self._enqueue("MakePbo.exe not found; install Mikero MakePbo (AIO or separate installer) if you need packing.")
                self._enqueue(f"ERROR: {e}")
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
        threading.Thread(target=run, daemon=True).start()

    def do_unrap(self):
        if not have_cmd("unrap"):
            return messagebox.showwarning("unRap missing", "Install DeRap, Link tools, then try again.")
        ur = read_text(UNRAP_PATH_FILE)
        if not verify_runtime(ur, self._log, warn_dialog=True):
            self._log("Aborting unrap due to missing runtime.")
            return
        initdir = self.default_mpm if os.path.isdir(self.default_mpm) else HOME
        target = filedialog.askopenfilename(
            title="Select .bin/.rap/.cfg",
            initialdir=initdir,
            filetypes=[("Binary configs", ("*.bin","*.rap","*.cfg")), ("All files","*.*")]
        )
        if not target: return
        self.progress['value'] = 0.0
        self._log(f"unrap {target}")
        def run():
            try:
                unrap_file(target, self._enqueue)
                self._enqueue("unRap completed.")
                self.after(0, lambda: messagebox.showinfo("Done", "DeRap completed."))
            except Exception as e:
                self._enqueue(f"ERROR: {e}")
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
        threading.Thread(target=run, daemon=True).start()

    def do_inject_respawn(self):
        initdir = self.default_mpm if os.path.isdir(self.default_mpm) else HOME
        folder = filedialog.askdirectory(title="Select extracted mission folder (contains mission.sqm)",
                                         initialdir=initdir)
        if not folder: return
        sqm = os.path.join(folder, "mission.sqm")
        if not os.path.isfile(sqm):
            if not messagebox.askyesno("Continue?", "mission.sqm not found. Continue anyway?"):
                return
        try:
            inject_respawn_stub(folder)
            self._log(f"Injected respawn into {os.path.join(folder, 'description.ext')}")
            messagebox.showinfo("Injected", "Respawn enabled. Place a marker named respawn_west (or respawn_east, etc.) in the editor.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def do_extract_fallback(self):
        pbo = self.pbo_var.get().strip()
        outdir = self.out_var.get().strip() or (os.path.splitext(pbo)[0] if pbo else "")
        if not pbo or not os.path.isfile(pbo):
            return messagebox.showwarning("Pick file", "Choose a valid .pbo first.")
        os.makedirs(outdir, exist_ok=True)
        self.progress['value'] = 0.0
        self._log(f"Fallback extractor (UNCOMPRESSED only) → {outdir}")
        def run():
            try:
                def log_fn(s): self._enqueue(s)
                def prog_fn(frac): self.progress.config(value=max(0.0, min(1.0, frac)))
                extract_uncompressed(pbo, outdir, log_fn, prog_fn)
                self._enqueue("Done (fallback).")
                self.after(0, lambda: messagebox.showinfo("Done", "Extraction complete (fallback)."))
            except Exception as e:
                self._enqueue(f"ERROR: {e}")
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
        threading.Thread(target=run, daemon=True).start()

# ============================ Main ==============================
if __name__ == "__main__":
    app = App()
    app.mainloop()
