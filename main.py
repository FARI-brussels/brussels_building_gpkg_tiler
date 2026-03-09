"""Legacy-compatible entrypoint.

Use `uv run gpkg-tiler run --config configs/default.yaml` for the structured pipeline.
"""

from src.cli import main


if __name__ == "__main__":
    main()
