"""
Decontamination pipeline for skimindex.

Groups all logic related to building and applying decontamination indices:

  sections   — directory helpers specific to decontamination sections
  split      — split reference genomes into overlapping fragments
  kmercount  — count k-mers in fragments to build indices
"""
