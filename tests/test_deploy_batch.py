import json
from pathlib import Path

from scripts.deploy_batch import create_state, run_state


def test_resume_skips_successful_jobs_and_retries_failed_archive(tmp_path, monkeypatch):
    deploy_log = tmp_path / "deploy.log"
    marker = tmp_path / "first-attempt"
    monkeypatch.setenv("DEPLOY_TEST_LOG", str(deploy_log))
    monkeypatch.setenv("DEPLOY_TEST_MARKER", str(marker))

    deploy_script = tmp_path / "fake-deploy.sh"
    deploy_script.write_text(
        """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$DEPLOY_TEST_LOG"
echo '--> Checkpoint: target arsip lolos pemeriksaan dan siap diekstrak.'
if [[ "$1" == "archive.tar.gz" && ! -f "$DEPLOY_TEST_MARKER" ]]; then
  touch "$DEPLOY_TEST_MARKER"
  exit 1
fi
""",
        encoding="utf-8",
    )
    deploy_script.chmod(0o755)
    state_path = create_state(
        tmp_path / "queues",
        deploy_script,
        [
            {"target": "archive.tar.gz", "archive": True, "args": ["archive.tar.gz"]},
            {"target": "second-project", "args": ["second-project"]},
        ],
        options=["--force-import"],
    )

    assert run_state(state_path) == 1
    first_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert [job["status"] for job in first_state["jobs"]] == ["failed", "success"]

    assert run_state(state_path) == 0
    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert [job["status"] for job in final_state["jobs"]] == ["success", "success"]
    assert [job["attempts"] for job in final_state["jobs"]] == [2, 1]

    invocations = deploy_log.read_text(encoding="utf-8").splitlines()
    assert len(invocations) == 3
    assert invocations[0] == "archive.tar.gz --force-import"
    assert "--resume-existing" in invocations[2]
    assert "--replace-existing" not in invocations[2]
    assert invocations[1] == "second-project --force-import"
    assert "--force-import" in invocations[2]
