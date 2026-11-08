"""Parametric 3D models of the printed pieces, built with build123d.

The CAD libraries (build123d, trimesh) come from the optional ``cad`` extra
(``uv sync --extra cad``). This package imports neither, so ``import
acequias.cad`` works on a plain install; only its submodules, such as
``acequias.cad.hex_tile``, need the extra. The game logic never imports
this package.
"""
