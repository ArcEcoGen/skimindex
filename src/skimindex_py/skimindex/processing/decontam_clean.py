"""
skimindex.processing.decontam_clean — 'decontam_clean' processing type.

Decontaminates genome sequences (FASTA or FASTQ, single-end or paired-end)
by querying them against the contamination k-mer index via kmquery.lua, then
filtering with obigrep.

Output kind: DIRECTORY.
  {output_dir}/{sample}_good.fasta.gz      — sequences that pass (not contaminated)
  {output_dir}/{sample}_discarded.fasta.gz — sequences that fail (contaminated)
"""

import json as _json
import multiprocessing
import os
import socket
import subprocess
import tempfile
import time
import urllib.request
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from skimindex.processing import OutputKind, processing_type
from skimindex.processing.data import Data, directory_data
from skimindex.unix.obitools import obigrep, obiscript

KMQUERY_LUA    = "/app/obiluascripts/kmquery.lua"
KMINDEX_SERVER = os.environ.get("KMINDEX_SERVER", "kmindex-server")
KMINDEX_HOST   = os.environ.get("KMINDEX_HOST", "127.0.0.1")


def _find_free_port(start: int = 8080) -> int:
    for port in range(start, start + 1000):
        with socket.socket() as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}–{start + 999}")


def _probe_server(host: str, port: int) -> bool:
    url   = f"http://{host}:{port}/kmindex/query"
    probe = _json.dumps({"index": [], "id": ["probe"], "seq": ["A"], "z": 0, "format": "json", "r": 0.0}).encode()
    try:
        req = urllib.request.Request(url, data=probe, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=0.5)
        return True
    except Exception:
        return False


@contextmanager
def _kmindex_server_ctx():
    index_dir = os.environ.get("KMINDEX_INDEX_DIR", "/indexes/decontamination")
    log_dir   = os.environ.get("KMINDEX_LOG_DIR", "/log")
    threads   = int(os.environ.get("KMINDEX_THREADS", multiprocessing.cpu_count() * 2))
    port      = _find_free_port()

    proc = subprocess.Popen(
        [KMINDEX_SERVER, "-i", index_dir, "-d", log_dir, "--threads", str(threads), "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(300):
            if proc.poll() is not None:
                raise RuntimeError(f"kmindex-server crashed on startup (exit {proc.returncode}, port {port})")
            if _probe_server(KMINDEX_HOST, port):
                break
            time.sleep(0.1)
        else:
            proc.terminate()
            raise RuntimeError(f"kmindex-server did not become ready within 30 seconds (port {port})")
        yield port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

_STEM_SUFFIXES = (
    "_1.fastq.gz", "_2.fastq.gz",
    "_R1_001.fastq.gz", "_R2_001.fastq.gz",
    "_R1.fastq.gz", "_R2.fastq.gz",
    "_R1_001.fastq", "_R2_001.fastq",
    "_R1.fastq", "_R2.fastq",
    "_1.fastq", "_2.fastq",
    ".fastq.gz", ".fastq",
    ".fasta.gz", ".fasta",
    ".fa.gz", ".fa",
)


def _file_stem(path: Path) -> str:
    name = path.name
    for suffix in _STEM_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def _auto_libs() -> tuple[str, str]:
    """Derive NOT_OK / OK library lists from decontamination dataset configs.

    Datasets with ``example = true``  → contaminating (NOT_OK).
    Datasets with ``example = false`` → counter-examples (OK, must not be removed).
    """
    from skimindex.datasets import datasets_for_role
    not_ok, ok = [], []
    for ds in datasets_for_role("decontamination"):
        directory = ds.get("directory") or ds.name
        if ds.get("example", True):
            not_ok.append(directory)
        else:
            ok.append(directory)
    return ",".join(not_ok), ",".join(ok)


@processing_type(output_kind=OutputKind.DIRECTORY)
def decontam_clean(params: dict) -> Callable[[Data, Path, bool], Data]:
    """Decontaminate genome sequences using the contamination k-mer index.

    Accepts FILES data with 1 path (single-end / FASTA) or 2 paths (R1 + R2
    paired-end FASTQ).  Paired mode adds ``--paired-with R2 --paired-mode or``
    to obigrep so that a pair is discarded when *either* read is contaminated.

    Parameters (from TOML config):
        batch_size:  obiscript --batch-size-max (default 50).
        min_score:   Minimum kmindex_score to call contamination (default 0.03).
        not_ok_libs: Comma-separated contaminating library names.
                     Default: auto-derived from decontamination datasets
                     where ``example = true``.
        ok_libs:     Comma-separated target library names.
                     Default: auto-derived from decontamination datasets
                     where ``example = false``.
    """
    batch_size  = int(params.get("batch_size", 50))
    min_score   = float(params.get("min_score", 0.03))
    _not_ok_cfg = params.get("not_ok_libs", "")
    _ok_cfg     = params.get("ok_libs", "")

    def run(input_data: Data, output_dir: Path, dry_run: bool = False) -> Data:
        from skimindex.log import loginfo

        paths = input_data.paths or []
        if not paths:
            raise ValueError("decontam_clean: no input paths in Data")

        r1     = paths[0]
        r2     = paths[1] if len(paths) >= 2 else None
        paired = r2 is not None
        sample = _file_stem(r1)

        # Library resolution: param > env > auto-derived from config
        auto_not_ok, auto_ok = _auto_libs()
        not_ok = _not_ok_cfg or os.environ.get("KMINDEX_CONTAM_NOT_OK_LIBS", "") or auto_not_ok
        ok     = _ok_cfg     or os.environ.get("KMINDEX_CONTAM_OK_LIBS",     "") or auto_ok

        output_dir.mkdir(parents=True, exist_ok=True)
        good_out      = output_dir / f"{sample}_good.fasta.gz"
        discarded_out = output_dir / f"{sample}_discarded.fasta.gz"

        loginfo(f"Sample: {sample}")
        loginfo(f"R1: {r1}")
        if paired:
            loginfo(f"R2: {r2}")
        if not_ok:
            loginfo(f"NOT_OK libs: {not_ok}")
        if ok:
            loginfo(f"OK    libs: {ok}")

        if dry_run:
            loginfo(f"[DRY-RUN] obiscript + obigrep → {output_dir}")
            return directory_data(output_dir, subdir=input_data.subdir,
                                  per_species=input_data.per_species)

        with _kmindex_server_ctx() as port:
                from plumbum import local as _local
                env_kwargs: dict[str, str] = {"KMINDEX_MANAGE_SERVER": "false", "KMINDEX_PORT": str(port)}
                if not_ok:
                    env_kwargs["KMINDEX_CONTAM_NOT_OK_LIBS"] = not_ok
                if ok:
                    env_kwargs["KMINDEX_CONTAM_OK_LIBS"] = ok
                with _local.env(**env_kwargs), tempfile.TemporaryDirectory() as tmpdir:
                    tmp_r1 = Path(tmpdir) / f"{sample}_R1_annotated.fasta.gz"
                    tmp_r2 = (Path(tmpdir) / f"{sample}_R2_annotated.fasta.gz") if paired else None

                    loginfo("Annotating R1...")
                    (obiscript(KMQUERY_LUA, "--fasta-output", "-Z",
                               "--batch-size-max", str(batch_size),
                               str(r1)) > str(tmp_r1))()

                    if paired:
                        loginfo("Annotating R2...")
                        (obiscript(KMQUERY_LUA, "--fasta-output", "-Z",
                                   "--batch-size-max", str(batch_size),
                                   str(r2)) > str(tmp_r2))()

                    loginfo("Filtering contaminated reads...")
                    filter_expr = (
                        f"annotations.contamination && "
                        f"annotations.kmindex_score >= {min_score}"
                    )
                    grep_args = [
                        "-p", filter_expr,
                        "-Z",
                        "--fasta-output",
                        "--save-discarded", str(good_out),
                        "--out", str(discarded_out),
                    ]
                    if paired:
                        grep_args += ["--paired-with", str(tmp_r2), "--paired-mode", "or"]
                    grep_args.append(str(tmp_r1))

                    obigrep(*grep_args)()

        loginfo(f"Clean reads    : {good_out}")
        loginfo(f"Discarded reads: {discarded_out}")
        return directory_data(output_dir, subdir=input_data.subdir,
                              per_species=input_data.per_species)

    return run
