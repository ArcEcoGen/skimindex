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
from typing import Any, Callable


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

@dataclass
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
    pt = get_processing_type(type_name)
    return pt, pt.build(params)


from skimindex.processing.data import (  # noqa: F401, E402
    Data, DataKind,
    stream_data, files_data, directory_data,
    to_stream_command,
)
from skimindex.processing.split import split, SPLITSEQS_LUA      # noqa: F401, E402
from skimindex.processing.filter_taxid import filter_taxid       # noqa: F401, E402
from skimindex.processing.filter_n_only import filter_n_only     # noqa: F401, E402
from skimindex.processing.distribute import distribute           # noqa: F401, E402

__all__ = [
    "OutputKind", "ProcessingType",
    "register", "get_processing_type", "registered_types",
    "processing_type",
    "make_pipeline", "build",
    "Data", "DataKind", "stream_data", "files_data", "directory_data", "to_stream_command",
    "split", "SPLITSEQS_LUA",
    "filter_taxid",
    "filter_n_only",
    "distribute",
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


def make_pipeline(processing_name: str) -> Callable:
    """Build a runnable callable from a composite [processing.X] TOML block.

    Steps are chained via the uniform Data → Data interface:
    - STREAM steps transform Data and pass it to the next step (no execution yet)
    - The terminal step (DIRECTORY/FILE) executes the pipeline and returns Data

    The output directory is resolved from data.subdir at runtime:
        {root} / {data.subdir} / {processing.directory}

    Returns a callable: run(input_data: Data, dry_run=False) -> Data

    Raises:
        ValueError: Not a composite, not runnable, or invalid step definition.
    """
    from skimindex.config import config  # local import to avoid circular dependency

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

    # Resolve each step into (ProcessingType, callable)
    resolved: list[tuple[ProcessingType, Callable]] = []
    for step in steps_cfg:
        if isinstance(step, str):
            ref_params = cfg.processing.get(step, {})
            if not ref_params:
                raise ValueError(f"[processing.{step}] not found (referenced in {processing_name})")
            pt, fn = _make_atomic(ref_params)
        elif isinstance(step, dict):
            pt, fn = _make_atomic(step)
        else:
            raise ValueError(f"Invalid step in [processing.{processing_name}]: {step!r}")
        resolved.append((pt, fn))

    # The terminal step determines is_indexer
    terminal_pt = resolved[-1][0]

    def run(input_data: Data, dry_run: bool = False) -> Data:
        """Execute the composite pipeline via Data → Data chaining."""
        output_dir = _resolve_output_dir(processing_name, terminal_pt, input_data)
        data = input_data
        for pt, fn in resolved:
            if pt.output_kind == OutputKind.STREAM:
                data = fn(data)
            else:
                data = fn(data, output_dir, dry_run=dry_run)  # terminal — executes
        return data

    return run


def build(processing_name: str) -> Callable:
    """Build a runnable callable from any [processing.X] TOML block.

    Detects atomic vs composite automatically:
    - 'steps' key → make_pipeline()
    - 'type'  key → atomic build (must be runnable)

    Raises:
        ValueError: Section not found, not runnable, or missing type/steps.
    """
    from skimindex.config import config  # local import to avoid circular dependency

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
    return pt.build(params)
