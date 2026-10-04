import shutil
import subprocess
import tempfile
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).parents[2]
EXPECTED_REVISIONS = {
    "20260926_0001",
    "20260927_0002",
    "20260928_0003",
    "20261003_0001",
    "20261003_0002",
}


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

        assert set(scripts.get_heads()) == {"20261003_0002"}
        history = list(scripts.walk_revisions())
        assert {revision.revision for revision in history} == EXPECTED_REVISIONS
