"""Project namespace; keeps the local agents directory separate from SDK `agents`."""
from pathlib import Path

__path__.append(str(Path(__file__).resolve().parent.parent))
