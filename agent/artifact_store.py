"""Publish complete artifacts atomically with normal workspace-inherited permissions."""
from pathlib import Path
import shutil
import uuid


def publish(destination, files):
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / (".staging-" + uuid.uuid4().hex)
    # Unlike mkdtemp's private ACL, ordinary mkdir inherits workspace access on Windows.
    staging.mkdir()
    try:
        for name, content in files.items():
            if Path(name).name != name:
                raise ValueError("Artifact names must be plain filenames")
            (staging / name).write_bytes(content)
        staging.rename(destination)
    finally:
        if staging.exists():
            if staging.resolve().parent != destination.parent or not staging.name.startswith(".staging-"):
                raise ValueError("Unsafe staging cleanup path")
            shutil.rmtree(staging)
