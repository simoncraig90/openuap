"""Download the raw source files into data/raw/.

Only hosts that publish the data openly are fetched automatically (GitHub).
NUFORC and GEIPAN block automated access from many networks and NUFORC's ToS
forbid scraping, so those loaders also accept files you place by hand.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request

from .db import DEFAULT_RAW
from .sources import geldreich, nuforc, geipan

UA = "openuap/0.1 (+https://github.com/ ; research data consolidation)"

GELDREICH_FILES = list(geldreich.FILES) + geldreich.ENRICHMENT_FILES
RR0_REPO = "https://github.com/RR0/rr0.org.git"
GODSEYE_GEIPAN_URL = geipan.SOURCES["geipan"]["fetched_from"]
UAP_MONITOR_REPO = "https://github.com/mhdSid/uap-monitor.git"
UAP_MONITOR_PATTERNS = ["/public/data/nuforc-*.json", "/public/data/dow-pursue-*.json"]
RR0_PATTERNS = ["**/GEIPAN_Cataloguedecas.csv", "**/GEIPAN_Catalogue-de-cas.csv", "/time/GrossPatrick_URECAT--Les-ovnis-vus-de-pres-.csv"]


def _download(url: str, dest: str, log=print) -> bool:
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return True
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, open(dest + ".part", "wb") as f:
            shutil.copyfileobj(resp, f)
        os.replace(dest + ".part", dest)
        log(f"  fetched {os.path.basename(dest)} ({os.path.getsize(dest)/1e6:.1f} MB)")
        return True
    except Exception as e:  # noqa: BLE001
        log(f"  FAILED {url}: {e}")
        if os.path.exists(dest + ".part"):
            os.remove(dest + ".part")
        return False


def fetch_geldreich(raw_dir: str, log=print) -> int:
    ok = 0
    for fn in GELDREICH_FILES:
        ok += _download(geldreich.RAW_BASE + fn, os.path.join(raw_dir, geldreich.RAW_SUBDIR, fn), log)
    return ok


def fetch_nuforc_mirror(raw_dir: str, log=print) -> int:
    dest = os.path.join(raw_dir, nuforc.RAW_SUBDIR, "planetsig_ufo-complete-geocoded-time-standardized.csv")
    return int(_download(nuforc.SOURCES["nuforc"]["fetched_from"], dest, log))


def _sparse_clone(repo: str, patterns: list[str], dest: str, subdir: str, exts: tuple[str, ...], flatten: bool, log) -> int:
    """Blobless sparse clone of `repo`; copy matching files under `subdir` into `dest`."""
    if os.path.isdir(dest) and any(True for _ in os.scandir(dest)):
        return 1
    tmp = dest + ".clone"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout", "--depth", "1", repo, tmp], check=True)
        subprocess.run(["git", "-C", tmp, "sparse-checkout", "init", "--no-cone"], check=True)
        with open(os.path.join(tmp, ".git", "info", "sparse-checkout"), "w") as f:
            f.write("\n".join(patterns) + "\n")
        subprocess.run(["git", "-C", tmp, "checkout", "-q"], check=True)
        sha = subprocess.run(["git", "-C", tmp, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        os.makedirs(dest, exist_ok=True)
        n = 0
        for root, _dirs, files in os.walk(os.path.join(tmp, subdir)):
            for fn in files:
                if fn.endswith(exts):
                    rel = fn if flatten else os.path.relpath(os.path.join(root, fn), tmp)
                    os.makedirs(os.path.dirname(os.path.join(dest, rel)) or dest, exist_ok=True)
                    shutil.copy2(os.path.join(root, fn), os.path.join(dest, rel))
                    n += 1
        with open(os.path.join(dest, "COMMIT.txt"), "w") as f:
            f.write(sha + "\n")
        log(f"  {repo.rsplit('/', 1)[-1]}: {n} files copied (commit {sha[:10]})")
        return 1
    except subprocess.CalledProcessError as e:
        log(f"  FAILED sparse clone of {repo}: {e}")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def fetch_rr0(raw_dir: str, log=print) -> int:
    """GEIPAN fragments and the URECAT export mirrored at rr0.org."""
    return _sparse_clone(RR0_REPO, RR0_PATTERNS, os.path.join(raw_dir, "rr0"), "time", (".csv",), False, log)


def fetch_geipan(raw_dir: str, log=print) -> int:
    """Full geocoded GEIPAN catalogue (Gods-Eye-UAPs build of the CNES bulk CSVs)."""
    return int(_download(GODSEYE_GEIPAN_URL, os.path.join(raw_dir, "geipan", "geipan_godseye.json"), log))


def fetch_uap_monitor(raw_dir: str, log=print) -> int:
    """NUFORC per-year JSON (full text) and the PURSUE Release 01 index from mhdSid/uap-monitor."""
    return _sparse_clone(UAP_MONITOR_REPO, UAP_MONITOR_PATTERNS, os.path.join(raw_dir, "uap_monitor"), "public/data",
                         (".json",), True, log)


def fetch_all(raw_dir: str = DEFAULT_RAW, log=print) -> None:
    os.makedirs(raw_dir, exist_ok=True)
    log("Geldreich ufo_data JSON timelines:")
    fetch_geldreich(raw_dir, log)
    log("NUFORC development mirror (see licence note in sources/nuforc.py):")
    fetch_nuforc_mirror(raw_dir, log)
    log("rr0.org exports (GEIPAN fragments, URECAT):")
    fetch_rr0(raw_dir, log)
    log("GEIPAN full catalogue (Gods-Eye-UAPs build):")
    fetch_geipan(raw_dir, log)
    log("uap-monitor feeds (NUFORC per-year JSON, PURSUE index):")
    fetch_uap_monitor(raw_dir, log)


if __name__ == "__main__":
    fetch_all(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RAW)
