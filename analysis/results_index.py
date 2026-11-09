"""Resolve run tags and the legacy machine paths used by the analysis scripts to this repository's results/ tree.

Every run lives at results/<platform>/<tag>/ with the files listed in results/MANIFEST.json. Logs and the larger
benchmark.json files are gzipped; `path()` returns a readable plain path, decompressing into results/.cache/ on
first use so the scripts' own open()/json.load() calls need no change.
"""
import gzip, json, os, re, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
CACHE = RESULTS / ".cache"
LEGACY = Path.home() / "kaggle_local"          # the machine the experiments ran on; used when no results tree exists
HAVE_TREE = (RESULTS / "MANIFEST.json").exists()

def manifest():
    return json.load(open(RESULTS / "MANIFEST.json"))

_RUNS = None
def runs():
    global _RUNS
    if _RUNS is None:
        _RUNS = {(r["platform"], r["tag"]): r for r in manifest()["runs"]}
    return _RUNS

def run_dir(tag, platform=None):
    hits = [k for k in runs() if k[1] == tag and (platform is None or k[0] == platform)]
    if not hits:
        raise FileNotFoundError(f"no run tagged {tag!r}" + (f" on {platform}" if platform else ""))
    if len(hits) > 1:
        raise KeyError(f"tag {tag!r} exists on {[h[0] for h in hits]}; pass platform=")
    return RESULTS / hits[0][0] / hits[0][1]

def log(tag, platform=None, which="stdout.log"):
    """The run's stdout.log (or launcher log), readable."""
    if not HAVE_TREE:
        base = {"vast": LEGACY / "vast_runs" / tag / "working", "kaggle": LEGACY / "kaggle_runs" / tag}.get(platform, LEGACY / f"working_{tag}")
        return str(LEGACY / which) if which.startswith("run_synesthesia_") else str(base / which)
    return path(which, tag, platform)

def path(rel, tag=None, platform=None):
    """A readable path for `rel` (e.g. 'synesthesia/benchmark.json' or 'stdout.log') inside a run, gunzipped if stored .gz."""
    base = run_dir(tag, platform) if tag else RESULTS
    p = base / rel
    if p.exists():
        return str(p)
    gz = Path(str(p) + ".gz")
    if gz.exists():
        c = CACHE / gz.relative_to(RESULTS).with_suffix("")
        if not c.exists() or c.stat().st_mtime < gz.stat().st_mtime:
            c.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(gz, "rb") as fi, open(c, "wb") as fo:
                shutil.copyfileobj(fi, fo)
        return str(c)
    raise FileNotFoundError(str(p))

def benchmark(tag, platform=None):
    if not HAVE_TREE:
        if platform == "vast":
            return str(LEGACY / "vast_runs" / tag / "benchmark.json")
        if platform == "kaggle":
            return str(LEGACY / "kaggle_runs" / tag / "synesthesia" / "benchmark.json")
        return str(LEGACY / f"working_{tag}" / "synesthesia" / "benchmark.json")
    for rel in ("synesthesia/benchmark.json", "benchmark.json"):
        try:
            return path(rel, tag, platform)
        except FileNotFoundError:
            continue
    raise FileNotFoundError(f"no benchmark.json for {tag}")

_LEGACY = [
    (re.compile(r"^/home/ignaz/kaggle_local/working_([^/]+)/synesthesia/benchmark\.json$"), lambda m: benchmark(m.group(1), "local")),
    (re.compile(r"^/home/ignaz/kaggle_local/working_([^/]+)/stdout\.log$"), lambda m: path("stdout.log", m.group(1), "local")),
    (re.compile(r"^/home/ignaz/kaggle_local/run_synesthesia_([^/]+)\.log$"), lambda m: path(f"run_synesthesia_{m.group(1)}.log", m.group(1), "local")),
    (re.compile(r"^/home/ignaz/kaggle_local/vast_runs/([^/]+)/(?:working/)?(?:synesthesia/)?benchmark\.json$"), lambda m: benchmark(m.group(1), "vast")),
    (re.compile(r"^/home/ignaz/kaggle_local/vast_runs/([^/]+)/(?:working/)?stdout\.log$"), lambda m: path("stdout.log", m.group(1), "vast")),
    (re.compile(r"^/home/ignaz/kaggle_local/kaggle_runs/([^/]+)/(.+)$"), lambda m: path(m.group(2), m.group(1), "kaggle")),
]
def run_glob(tag, platform, pattern):
    """Readable paths of the files in a run whose name matches `pattern` (a glob over the run directory's top level;
    stored .gz copies match on their plain name). Works in both modes."""
    import fnmatch
    if not HAVE_TREE:
        base = {"vast": LEGACY / "vast_runs" / tag / "working", "kaggle": LEGACY / "kaggle_runs" / tag,
                "server": LEGACY / "server_runs" / tag}.get(platform, LEGACY / f"working_{tag}")
        hits = sorted(str(q) for q in base.glob(pattern) if q.is_file())
        if platform == "local":
            hits += sorted(str(q) for q in LEGACY.glob(pattern) if q.is_file() and q.name == f"run_synesthesia_{tag}.log")
        return hits
    d = run_dir(tag, platform)
    names = sorted({q.name[:-3] if q.name.endswith(".gz") else q.name for q in d.iterdir() if q.is_file()})
    return [path(n, tag, platform) for n in names if fnmatch.fnmatch(n, pattern)]

def platform_of(tag):
    """The platform a run tag lives on (local, vast, kaggle, server, archive), in either mode; None if unknown or ambiguous."""
    if HAVE_TREE:
        hits = [k[0] for k in runs() if k[1] == tag]
        return hits[0] if len(hits) == 1 else None
    cands = [("local", LEGACY / f"working_{tag}"), ("vast", LEGACY / "vast_runs" / tag), ("kaggle", LEGACY / "kaggle_runs" / tag),
             ("kaggle", Path("/mnt/data/kaggle_runs_kas") / tag), ("server", LEGACY / "server_runs" / tag)]
    hits = sorted({plat for plat, d in cands if d.is_dir()})
    return hits[0] if len(hits) == 1 else None

# A run file's identity: platform/tag/file, the same whether the path is this tree's (results/ or results/.cache/, .gz or
# not) or the machine the experiments ran on. reproduce.py compares path-valued strings in the committed JSONs by this.
_IDENT = [
    (re.compile(r"(?:^|/)results/(?:\.cache/)?(local|vast|kaggle|server|archive)/([^/]+)/(.+?)(?:\.gz)?$"), lambda m: (m.group(1), m.group(2), m.group(3))),
    (re.compile(r"(?:^|/)kaggle_local/working_([^/]+)/(.+)$"), lambda m: ("local", m.group(1), m.group(2))),
    (re.compile(r"(?:^|/)kaggle_local/run_synesthesia_([^/]+)\.log$"), lambda m: ("local", m.group(1), f"run_synesthesia_{m.group(1)}.log")),
    (re.compile(r"(?:^|/)kaggle_local/vast_runs/([^/]+)/(?:working/)?(.+)$"), lambda m: ("vast", m.group(1), m.group(2))),
    (re.compile(r"(?:^|/)kaggle_local/server_runs/([^/]+)/(?:working/)?(.+)$"), lambda m: ("server", m.group(1), m.group(2))),
    (re.compile(r"(?:^|/)kaggle_local/kaggle_runs/([^/]+)/(.+)$"), lambda m: ("kaggle", m.group(1), m.group(2))),
    (re.compile(r"(?:^|/)kaggle_runs_kas/([^/]+)/(.+)$"), lambda m: ("kaggle", m.group(1), m.group(2))),
]
def identity(s):
    """'platform/tag/file' for a path to a run's file (either layout); any other string is returned unchanged."""
    s = str(s)
    for rx, fn in _IDENT:
        m = rx.search(s)
        if m:
            return "/".join(fn(m))
    return s

def resolve(legacy_path):
    """Map a path as it was on the machine that ran the experiments to this tree; unknown paths are returned unchanged."""
    for rx, fn in _LEGACY:
        m = rx.match(str(legacy_path))
        if m:
            try:
                return fn(m)
            except FileNotFoundError:
                return str(legacy_path)
    return str(legacy_path)
