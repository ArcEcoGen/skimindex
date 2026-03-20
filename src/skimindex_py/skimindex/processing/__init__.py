"""
skimindex.processing — registry of data processing operation types.

Each processing type is a Python function decorated with @processing_type.
The decorator registers it so that:
  - config validation can verify [processing.X].type values
  - make_step() can build a ready-to-call pipeline step from a TOML config block

Concepts
--------
OutputKind
    Describes what a processing type produces:
    - STREAM    : output on STDOUT, chainable in a plumbum pipe
    - DIRECTORY : output written to a directory of files
    - FILE      : output written to a single file

ProcessingType
    Metadata + builder for one registered type.
    .pipable        → True iff output_kind == STREAM
    .is_runnable()  → True iff params contain a 'directory' key
    .build(params)  → callable configured with params, ready to execute

processing_type(output_kind, ...)
    Decorator that registers a builder function as a ProcessingType.
    Uses __name__ and __doc__ of the decorated function.

make_step(processing_name)
    Builds a runnable callable from a [processing.X] TOML block.
    Raises ValueError if the section is not runnable.

Usage
-----
    # Registering a type (in the module that implements it):
    from skimindex.processing import processing_type, OutputKind

    @processing_type(output_kind=OutputKind.STREAM)
    def split(params: dict):
        \"\"\"Split reference sequences into overlapping fragments.\"\"\"
        size = params.get("size", 200)
        def run(input_cmd):
            ...
        return run

    # Building a step from config:
    from skimindex.processing import make_step
    step = make_step("split_decontam")
    step(input_cmd, output_dir, dry_run=False)
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from collections.abc import Callable
from typing import Any


# ---------------------------------------------------------------------------
# OutputKind
# ---------------------------------------------------------------------------

class OutputKind(Enum):
    STREAM    = auto()   # output on STDOUT — chainable in a plumbum pipe
    DIRECTORY = auto()   # output written to a directory of files
    FILE      = auto()   # output written to a single file


# ---------------------------------------------------------------------------
# ProcessingType
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ProcessingType:
    """Metadata and builder for a registered processing operation type."""

    name: str
    description: str
    output_kind: OutputKind
    needs_tmpdir: bool = False
    is_indexer: bool = False

    # Filename used when output_kind=STREAM or FILE and the step must be
    # persisted to disk (because a 'directory' is declared in config).
    # Set in code by the type implementer — e.g. "filtered.fasta.gz".
    # None means the type cannot be persisted; declaring 'directory' for
    # it is a validation error.
    output_filename: str | None = None

    _builder: Callable[[dict[str, Any]], Callable] = field(repr=False, default=None)

    @property
    def pipable(self) -> bool:
        """True if the output is a STDOUT stream (chainable in a plumbum pipe)."""
        return self.output_kind == OutputKind.STREAM

    def is_runnable(self, params: dict[str, Any]) -> bool:
        """True if this type has an effective output directory with these params.

        A type is runnable when 'directory' is present in params.
        STREAM/FILE types additionally require output_filename to be set.
        """
        if "directory" not in params:
            return False
        if self.output_kind in (OutputKind.STREAM, OutputKind.FILE):
            return self.output_filename is not None
        return True

    def build(self, params: dict[str, Any]) -> Callable:
        """Return a callable configured with params, ready to execute."""
        return self._builder(params)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, ProcessingType] = {}


def register(pt: ProcessingType) -> ProcessingType:
    """Register a ProcessingType by name."""
    _REGISTRY[pt.name] = pt
    return pt


def get_processing_type(name: str) -> ProcessingType:
    """Return a registered ProcessingType by name, or raise KeyError."""
    if name not in _REGISTRY:
        raise KeyError(
            f"Unknown processing type: {name!r}. Known types: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[name]


def registered_types() -> frozenset[str]:
    """Return the set of all registered processing type names."""
    return frozenset(_REGISTRY)


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

def processing_type(
    output_kind: OutputKind,
    needs_tmpdir: bool = False,
    output_filename: str | None = None,
    is_indexer: bool = False,
):
    """Decorator that registers a builder function as a ProcessingType.

    The function's __name__ becomes the type name; __doc__ becomes the
    description. The function itself is the builder: it receives a params
    dict and returns a callable ready to execute.

    Args:
        output_kind:      What the type produces (STREAM / DIRECTORY / FILE).
        needs_tmpdir:     True if the type needs a temporary working directory.
        output_filename:  Filename used when a STREAM/FILE output is persisted.
                          None = type cannot be persisted (must stay temporary).
        is_indexer:       True if this type writes to the indexes tree rather
                          than the processed_data tree.

    Example::

        @processing_type(output_kind=OutputKind.STREAM)
        def split(params: dict):
            \"\"\"Split sequences into overlapping fragments.\"\"\"
            size = params.get("size", 200)
            def run(input_cmd):
                return input_cmd | obiscript(SPLITSEQS_LUA)
            return run
    """
    def decorator(fn: Callable) -> Callable:
        register(ProcessingType(
            name=fn.__name__,
            description=(fn.__doc__ or "").strip(),
            output_kind=output_kind,
            needs_tmpdir=needs_tmpdir,
            output_filename=output_filename,
            is_indexer=is_indexer,
            _builder=fn,
        ))
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _make_atomic(params: dict[str, Any]) -> tuple[ProcessingType, Callable]:
    """Resolve and build an atomic step from a params dict.

    Returns (ProcessingType, callable).  The callable is the builder's return
    value — its signature depends on output_kind.
    """
    type_name = params.get("type")
    if not type_name:
        raise ValueError("Atomic processing params missing 'type' key")
    try:
        pt = get_processing_type(type_name)
    except KeyError as e:
        e.add_note(f"Check [processing.*] sections in your skimindex.toml")
        raise
    return pt, pt.build(params)


# ---------------------------------------------------------------------------
# Public re-exports
# ---------------------------------------------------------------------------
# Data abstractions used throughout the pipeline
from skimindex.processing.data import (  # noqa: F401, E402
    Data, DataKind,
    stream_data, files_data, directory_data,
    to_stream_command,
)

# Processing type registrations — importing these modules triggers @processing_type,
# which registers each type in _REGISTRY so that get_processing_type() and build()
# can find them by name.
from skimindex.processing.split import split, SPLITSEQS_LUA      # noqa: F401, E402
from skimindex.processing.filter_taxid import filter_taxid       # noqa: F401, E402
from skimindex.processing.filter_n_only import filter_n_only     # noqa: F401, E402
from skimindex.processing.distribute import distribute           # noqa: F401, E402
from skimindex.processing.kmercount import kmercount             # noqa: F401, E402

__all__ = [
    "OutputKind", "ProcessingType",
    "register", "get_processing_type", "registered_types",
    "processing_type",
    "build",
    "Data", "DataKind", "stream_data", "files_data", "directory_data", "to_stream_command",
    "split", "SPLITSEQS_LUA",
    "filter_taxid",
    "filter_n_only",
    "distribute",
    "kmercount",
]


def _resolve_output_dir(processing_name: str, terminal_pt: ProcessingType, data: Data) -> Path:
    """Compute the full output directory for a pipeline run.

    Combines three levels:
        {root} / {data.subdir} / {processing.directory}

    where root is processed_data_dir() or indexes_dir() depending on
    terminal_pt.is_indexer, and processing.directory comes from the TOML.
    """
    from skimindex.config import config
    cfg = config()
    root = cfg.indexes_dir() if terminal_pt.is_indexer else cfg.processed_data_dir()
    proc_dir = cfg.processing.get(processing_name, {}).get("directory", processing_name)
    if data.subdir is not None:
        return root / data.subdir / proc_dir
    return root / proc_dir


def _resolve_input(proc_params: dict, input_data: Data) -> Data:
    """Resolve the actual input Data for a processing section.

    If 'input' key is present in proc_params, the input is read from the
    output directory of the referenced processing section.  The subdir from
    input_data is preserved so that output path resolution still works.

    If 'input' is absent, input_data is returned unchanged.
    """
    input_ref = proc_params.get("input")
    if input_ref is None:
        return input_data

    from skimindex.config import config
    cfg = config()
    ref_params = cfg.processing.get(input_ref, {})
    ref_dir = ref_params.get("directory", input_ref)
    root = cfg.processed_data_dir()

    if input_data.subdir is not None:
        path = root / input_data.subdir / ref_dir
    else:
        path = root / ref_dir

    return directory_data(path, subdir=input_data.subdir)


def _step_output_dir(step_params: dict, is_indexer: bool, data: Data) -> Path | None:
    """Return the output directory for a step, or None if no 'directory' declared."""
    step_dir = step_params.get("directory")
    if not step_dir:
        return None
    from skimindex.config import config
    cfg = config()
    root = cfg.indexes_dir() if is_indexer else cfg.processed_data_dir()
    return (root / data.subdir / step_dir) if data.subdir is not None else (root / step_dir)


def make_pipeline(processing_name: str) -> Callable:
    """Build a runnable callable from a composite [processing.X] TOML block.

    Persistence rules (enforced by the runner, not the atomic bricks):
    - STREAM step with directory, non-terminal: tee to file, pipe continues
    - STREAM step with directory, terminal: redirect stdout to file
    - DIRECTORY/FILE step: output_dir passed to brick (step_dir or tmpdir)
    - No directory: STREAM chains without executing; DIRECTORY uses tmpdir (cleaned up)

    Stamp rules:
    - needs_run / stamp on the composite output_dir only
    - Intermediate steps with directory are persisted but not stamped

    Returns a callable: run(input_data: Data, dry_run=False) -> Data
    """
    import shutil
    import tempfile

    from plumbum import local as _local

    from skimindex.config import config  # local import to avoid circular dependency
    from skimindex.stamp import needs_run, remove_if_not_stamped, stamp

    cfg = config()
    params = cfg.processing.get(processing_name, {})
    steps_cfg = params.get("steps")

    if steps_cfg is None:
        raise ValueError(
            f"[processing.{processing_name}] has no 'steps' — use build() for atomics"
        )
    if "directory" not in params:
        raise ValueError(
            f"[processing.{processing_name}] composite has no 'directory' — not runnable"
        )

    # Resolve each step into (step_params, ProcessingType, callable)
    resolved: list[tuple[dict, ProcessingType, Callable]] = []
    for step in steps_cfg:
        if isinstance(step, str):
            ref_params = cfg.processing.get(step, {})
            if not ref_params:
                raise ValueError(f"[processing.{step}] not found (referenced in {processing_name})")
            pt, fn = _make_atomic(ref_params)
            resolved.append((ref_params, pt, fn))
        elif isinstance(step, dict):
            pt, fn = _make_atomic(step)
            resolved.append((step, pt, fn))
        else:
            raise ValueError(f"Invalid step in [processing.{processing_name}]: {step!r}")

    terminal_pt = resolved[-1][1]

    def run(input_data: Data, dry_run: bool = False) -> Data:
        """Execute the composite pipeline with persistence and stamp management."""
        data = _resolve_input(params, input_data)
        composite_output_dir = _resolve_output_dir(processing_name, terminal_pt, data)

        sources = data.paths or ([data.path] if data.path else [])
        if not needs_run(composite_output_dir, *sources, dry_run=dry_run,
                         label=processing_name, action=f"run {processing_name}"):
            return directory_data(composite_output_dir, subdir=data.subdir)
        remove_if_not_stamped(composite_output_dir)

        tmpdirs: list[Path] = []
        try:
            n = len(resolved)
            for i, (step_params, pt, fn) in enumerate(resolved):
                is_last = (i == n - 1)
                step_dir = _step_output_dir(step_params, terminal_pt.is_indexer, data)

                if pt.output_kind == OutputKind.STREAM:
                    if step_dir:
                        step_dir.mkdir(parents=True, exist_ok=True)
                        out_file = step_dir / pt.output_filename
                        if is_last:
                            (data.command > str(out_file))()
                            data = files_data([out_file], format=data.format, subdir=data.subdir)
                        else:
                            tee = _local["tee"][str(out_file)]
                            data = stream_data(data.command | tee, format=data.format, subdir=data.subdir)
                    else:
                        data = fn(data)
                else:
                    if step_dir:
                        effective_dir = step_dir
                    else:
                        tmpdir = Path(tempfile.mkdtemp())
                        tmpdirs.append(tmpdir)
                        effective_dir = tmpdir
                    data = fn(data, effective_dir, dry_run=dry_run)

            stamp(composite_output_dir)
            return data
        finally:
            for t in tmpdirs:
                shutil.rmtree(t, ignore_errors=True)

    return run


def build(processing_name: str) -> Callable:
    """Build a runnable callable from any [processing.X] TOML block.

    Detects atomic vs composite automatically:
    - 'steps' key → make_pipeline()
    - 'type'  key → atomic build (must be runnable)

    The returned callable handles needs_run / stamp automatically.

    Raises:
        ValueError: Section not found, not runnable, or missing type/steps.
    """
    from skimindex.config import config  # local import to avoid circular dependency
    from skimindex.stamp import needs_run, remove_if_not_stamped, stamp

    params = config().processing.get(processing_name, {})
    if not params:
        raise ValueError(f"[processing.{processing_name}] not found in config")

    if "steps" in params:
        return make_pipeline(processing_name)

    # Atomic
    type_name = params.get("type")
    if not type_name:
        raise ValueError(f"[processing.{processing_name}] missing 'type' or 'steps' key")
    pt = get_processing_type(type_name)
    if not pt.is_runnable(params):
        raise ValueError(
            f"[processing.{processing_name}] (type={type_name!r}) is not runnable: "
            f"no effective output directory"
        )
    fn = pt.build(params)

    def run(input_data: Data, dry_run: bool = False) -> Data:
        """Execute the atomic step with needs_run / stamp management."""
        data = _resolve_input(params, input_data)
        output_dir = _resolve_output_dir(processing_name, pt, data)
        sources = data.paths or ([data.path] if data.path else [])
        if not needs_run(output_dir, *sources, dry_run=dry_run,
                         label=processing_name, action=f"run {processing_name}"):
            return directory_data(output_dir, subdir=data.subdir)
        remove_if_not_stamped(output_dir)
        result = fn(data, output_dir, dry_run=dry_run)
        stamp(output_dir)
        return result

    return run
