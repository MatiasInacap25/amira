import shutil
import subprocess
import tempfile
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).parents[2]


def revision_from_filename(filename: str) -> str:
    # Migration files are named "<revision>_<slug>.py", where the revision is "YYYYMMDD_NNNN".
    return "_".join(Path(filename).stem.split("_")[:2])


def test_tracked_migrations_form_one_resolvable_history_without_untracked_revisions():
    tracked = subprocess.run(
        [
            "git", "-c", f"safe.directory={ROOT}", "ls-files",
            "--", "backend/alembic/versions/*.py",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    with tempfile.TemporaryDirectory(prefix="amira-tracked-alembic-") as temp_dir:
        versions = Path(temp_dir) / "versions"
        versions.mkdir()
        for relative_path in tracked:
            shutil.copy2(ROOT / relative_path, versions / Path(relative_path).name)

        config = Config()
        config.set_main_option("script_location", temp_dir)
        scripts = ScriptDirectory.from_config(config)

        assert len(scripts.get_heads()) == 1
        history = list(scripts.walk_revisions())
        tracked_revisions = {revision_from_filename(Path(path).name) for path in tracked}
        assert {revision.revision for revision in history} == tracked_revisions
