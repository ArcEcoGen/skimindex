"""
skimindex.processing — registry of data processing operations.

Each processing operation is a function or class decorated with @data_process.
The decorator registers it by name so that config validation can verify that
[processing.X] sections reference valid, known operations.

Usage:
    from skimindex.processing import data_process, registered_types

    @data_process
    def my_step(params, input_path, output_path):
        ...

    registered_types()  # → frozenset({"split", "kmercount", ..., "my_step"})
"""

from typing import Any

# Global registry: name → callable
_REGISTRY: dict[str, Any] = {}


def data_process(fn_or_class: Any) -> Any:
    """Decorator that registers a processing function or class by its __name__."""
    _REGISTRY[fn_or_class.__name__] = fn_or_class
    return fn_or_class


def registered_types() -> frozenset[str]:
    """Return the set of all registered @data_process names."""
    return frozenset(_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Built-in processing types (placeholder implementations — real logic added later)
# ---------------------------------------------------------------------------

@data_process
def split():
    """Split reference sequences into overlapping fragments."""
    ...


@data_process
def kmercount():
    """Count k-mers in split fragments to build decontamination indices."""
    ...


@data_process
def remove_n_only():
    """Remove sequences composed only of N bases."""
    ...


@data_process
def distribute():
    """Distribute sequences into batches."""
    ...
