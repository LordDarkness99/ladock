import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MAINTENANCE_SCRIPT = ROOT / "scripts" / "laravel_maintenance.sh"


def _fake_php(tmp_path: Path, commands: str, fail_command: str = ""):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    command_log = tmp_path / "commands.log"
    php = bin_dir / "php"
    php.write_text(
        """#!/usr/bin/env bash
if [[ "$*" == "artisan list" ]]; then
  printf '%s\\n' "$ARTISAN_COMMANDS"
  exit 0
fi
printf '%s\\n' "$*" >> "$COMMAND_LOG"
[[ "$*" != "$FAIL_COMMAND" ]] || exit 23
""",
        encoding="utf-8",
    )
    php.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ARTISAN_COMMANDS": commands,
            "COMMAND_LOG": str(command_log),
            "FAIL_COMMAND": fail_command,
        }
    )
    return env, command_log


def test_legacy_artisan_runs_supported_commands_without_force_options(tmp_path: Path):
    (tmp_path / "artisan").touch()
    migrations = tmp_path / "database" / "migrations"
    migrations.mkdir(parents=True)
    (migrations / "001_create_table.php").touch()
    env, command_log = _fake_php(
        tmp_path, "cache:clear\nkey:generate\nmigrate"
    )

    result = subprocess.run(
        ["bash", str(MAINTENANCE_SCRIPT), "1"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    commands = command_log.read_text(encoding="utf-8").splitlines()
    assert "artisan cache:clear" in commands
    assert "artisan key:generate" in commands
    assert "artisan migrate" in commands
    assert all("--force" not in command for command in commands)
    assert "config:clear" not in result.stdout
    assert "route:clear" not in result.stdout
    assert "view:clear" not in result.stdout
    assert "storage:link" in result.stdout


def test_artisan_command_failure_is_not_silenced(tmp_path: Path):
    (tmp_path / "artisan").touch()
    env, _ = _fake_php(tmp_path, "cache:clear", "artisan cache:clear")

    result = subprocess.run(
        ["bash", str(MAINTENANCE_SCRIPT), "0"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 23
