from pathlib import Path

def find_project_root() -> Path:
    """Find project root by looking for .project_root marker"""
    current = Path(__file__).resolve()
    while current.parent != current:
        if (current / ".project_root").exists():
            return current
        current = current.parent
    raise FileNotFoundError(
        "Could not find project root. "
        "Make sure .project_root file exists in project root directory."
    ) 