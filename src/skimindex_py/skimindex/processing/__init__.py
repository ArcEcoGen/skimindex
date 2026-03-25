"""
skimindex.processing — registry of data processing operation types.

Each processing type is a Python function decorated with ``@processing_type``.
The decorator registers it so that config validation can verify
``[processing.X].type`` values and ``build()`` can construct a ready-to-call
pipeline step directly from a TOML config block.

Key concepts:

- ``OutputKind`` — what a type produces: ``STREAM`` (stdout pipe), ``DIRECTORY``,
  or ``FILE``.
- ``ProcessingType`` — metadata + builder for one registered type.
- ``@processing_type`` — registers a builder function by its ``__name__``.
- ``build(name)`` — unified factory: detects atomic vs composite automatically.
- ``make_pipeline(name)`` — builds a composite pipeline from a ``steps`` list.

Example:
    ```python
    from skimindex.processing import processing_type, OutputKind, build

    # Registering a new type:
    @processing_type(output_kind=OutputKind.STREAM)
    def my_filter(params: dict):
        \"\"\"Filter sequences by a custom criterion.\"\"\"
        threshold = params.get("threshold", 10)
        def run(input_data):
            ...
        return run

    # Building and running from config:
    step = build("count_kmers_decontam")
    result = step(input_data, dry_run=False)
    ```
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
    """Metadata and builder for a registered processing operation type.

    Attributes:
        name:            Type name (used as ``type = "…"`` in TOML).
        description:     Human-readable description (from ``__doc__``).
        output_kind:     What the type produces (``STREAM``, ``DIRECTORY``, or ``FILE``).
        needs_tmpdir:    ``True`` if the builder requires a temporary working directory.
        is_indexer:      ``True`` if outputs go to the indexes tree instead of processed_data.
        output_filename: Filename used when a ``STREAM``/``FILE`` output is persisted to disk
                         (e.g. ``"filtered.fasta.gz"``).  ``None`` means the type cannot be
                         persisted; declaring ``output`` for it is a validation error.
    """

    name: str
    description: str
    output_kind: OutputKind
    needs_tmpdir: bool = False
    is_indexer: bool = False
    output_filename: str | None = None

    _builder: Callable[[dict[str, Any]], Callable] = field(repr=False, default=None)

    @property
    def pipable(self) -> bool:
        """True if the output is a STDOUT stream (chainable in a plumbum pipe)."""
        return self.output_kind == OutputKind.STREAM

    def is_runnable(self, params: dict[str, Any]) -> bool:
        """True if this type has an effective output directory with these params.

        A type is runnable when 'output' is present in params.
        STREAM/FILE types additionally require output_filename to be set.
        """
        if "output" not in params:
            return False
        if self.output_kind in (OutputKind.STREAM, OutputKind.FILE):
            return self.output_filename is not None
        return True

    def build(self, params: dict[str, Any]) -> Callable:
        """Return a callable configured with *params*, ready to execute.

        Args:
            params: The ``[processing.X]`` config dict for this step.

        Returns:
            A callable whose signature depends on ``output_kind``:
            ``STREAM`` types return ``run(input_data) -> Data``;
            ``DIRECTORY`` types return ``run(input_data, output_dir, dry_run) -> Data``.
        """
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
    to_stream_command, pipe_through,
)

# Processing type registrations — importing these modules triggers @processing_type,
# which registers each type in _REGISTRY so that get_processing_type() and build()
# can find them by name.
from skimindex.processing.split import split, SPLITSEQS_LUA      # noqa: F401, E402
from skimindex.processing.filter_taxid import filter_taxid       # noqa: F401, E402
from skimindex.processing.filter_n_only import filter_n_only     # noqa: F401, E402
from skimindex.processing.distribute import distribute           # noqa: F401, E402
from skimindex.processing.kmercount import kmercount             # noqa: F401, E402
from skimindex.processing.compress import compress               # noqa: F401, E402
from skimindex.processing.uncompress import uncompress           # noqa: F401, E402

__all__ = [
    "OutputKind", "ProcessingType",
    "register", "get_processing_type", "registered_types",
    "processing_type",
    "build",
    "Data", "DataKind", "stream_data", "files_data", "directory_data", "to_stream_command", "pipe_through",
    "split", "SPLITSEQS_LUA",
    "filter_taxid",
    "filter_n_only",
    "distribute",
    "kmercount",
    "compress",
    "uncompress",
]


def _resolve_output_dir(processing_name: str, data: Data) -> Path:
    """Compute the full output directory for a pipeline run.

    Reads 'output' from the processing config and delegates to resolve_artifact().
    The artifact reference encodes both the role tree (processed_data or indexes)
    and the subdirectory name via the 'dir@[idx:]role' notation.
    """
    from skimindex.config import config
    from skimindex.sources import resolve_artifact
    cfg = config()
    output_ref = cfg.processing.get(processing_name, {}).get("output")
    if not output_ref:
        raise ValueError(f"[processing.{processing_name}] missing 'output'")
    return resolve_artifact(output_ref, data.subdir)


def _step_output_dir(step_params: dict, data: Data) -> Path | None:
    """Return the output directory for an inline step, or None if not declared.

    Inline steps (dict entries in 'steps') use 'directory' for intermediate
    persistence. Named step references may use 'output' instead.
    """
    if "output" in step_params:
        from skimindex.sources import resolve_artifact
        return resolve_artifact(step_params["output"], data.subdir)
    step_dir = step_params.get("directory")
    if not step_dir:
        return None
    from skimindex.config import config
    cfg = config()
    root = cfg.processed_data_dir()
    return (root / data.subdir / step_dir) if data.subdir is not None else (root / step_dir)


def make_pipeline(processing_name: str) -> Callable:
    """Build a runnable callable from a composite ``[processing.X]`` TOML block.

    A composite block has a ``steps`` list and a top-level ``output`` reference.
    Each step is either an inline dict (``{type = "split", size = 200, …}``) or
    a string reference to another named ``[processing.*]`` block.

    Persistence rules (managed by the runner, not the atomic bricks):

    - ``STREAM`` step with ``directory``, non-terminal → tee to file, pipe continues.
    - ``STREAM`` step with ``directory``, terminal → redirect stdout to file.
    - ``DIRECTORY``/``FILE`` step → ``output_dir`` passed to brick (step dir or tmpdir).
    - No ``directory`` → ``STREAM`` chains without executing; ``DIRECTORY`` uses tmpdir.

    Stamp management: ``needs_run`` / ``stamp`` operate on the composite ``output``
    only.  Intermediate steps with a ``directory`` are persisted but not stamped.

    Args:
        processing_name: Key of the ``[processing.X]`` block in the TOML config.

    Returns:
        ``run(input_data: Data, dry_run: bool = False) -> Data``

    Raises:
        ValueError: If the block has no ``steps``, no ``output``, or references
                    an unknown processing name.
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
    if "output" not in params:
        raise ValueError(
            f"[processing.{processing_name}] composite has no 'output' — not runnable"
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

    def run(input_data: Data, dry_run: bool = False) -> Data:
        """Execute the composite pipeline with persistence and stamp management."""
        data = input_data
        composite_output_dir = _resolve_output_dir(processing_name, data)

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
                step_dir = _step_output_dir(step_params, data)

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
    """Build a runnable callable from any ``[processing.X]`` TOML block.

    Dispatches automatically:

    - ``steps`` key present → ``make_pipeline()`` (composite pipeline).
    - ``type`` key present  → atomic build (type must be registered and runnable).

    The returned callable wraps ``needs_run`` / ``stamp`` so callers do not
    need to manage stamps themselves.

    Args:
        processing_name: Key of the ``[processing.X]`` block in the TOML config.

    Returns:
        ``run(input_data: Data, dry_run: bool = False) -> Data``

    Raises:
        ValueError: If the block is not found, is not runnable (no ``output``),
                    or is missing both ``type`` and ``steps``.
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
        data = input_data
        output_dir = _resolve_output_dir(processing_name, data)
        sources = data.paths or ([data.path] if data.path else [])
        if not needs_run(output_dir, *sources, dry_run=dry_run,
                         label=processing_name, action=f"run {processing_name}"):
            return directory_data(output_dir, subdir=data.subdir)
        remove_if_not_stamped(output_dir)
        result = fn(data, output_dir, dry_run=dry_run)
        stamp(output_dir)
        return result

    return run
