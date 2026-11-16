#!/usr/bin/env python3
"""Persist and resume sequential LaDock deployment batches."""

import argparse
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ARCHIVE_SUFFIXES = (".zip", ".tar.gz", ".tgz", ".tar.bz2", ".tar")
_active_process: subprocess.Popen[str] | None = None
_interrupted = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_state(state_path: Path, state: dict) -> None:
    state["updated_at"] = _now()
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=state_path.parent, delete=False
    ) as state_file:
        json.dump(state, state_file, ensure_ascii=False, indent=2)
        state_file.write("\n")
        temp_path = Path(state_file.name)
    os.chmod(temp_path, 0o600)
    os.replace(temp_path, state_path)


def _load_state(state_path: Path) -> dict:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Tidak dapat membaca checkpoint {state_path}: {exc}") from exc
    if not isinstance(state, dict) or not isinstance(state.get("jobs"), list):
        raise ValueError(f"Format checkpoint tidak valid: {state_path}")
    for job in state["jobs"]:
        if (
            not isinstance(job, dict)
            or not isinstance(job.get("args"), list)
            or not all(isinstance(arg, str) for arg in job["args"])
        ):
            raise ValueError(f"Data project pada checkpoint tidak valid: {state_path}")
    return state


def create_state(
    state_dir: Path,
    deploy_script: Path,
    jobs: list[dict],
    options: list[str] | None = None,
    queue_id: str | None = None,
) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    if queue_id is None:
        queue_id = f"queue_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
    if not re.fullmatch(r"[A-Za-z0-9_-]+", queue_id):
        raise ValueError("ID checkpoint tidak valid.")
    if not jobs:
        raise ValueError("Masukkan minimal satu project untuk dideploy.")

    state_path = state_dir / f"{queue_id}.json"
    state = {
        "id": queue_id,
        "created_at": _now(),
        "updated_at": _now(),
        "started_at": None,
        "finished_at": None,
        "status": "pending",
        "deploy_script": str(deploy_script.resolve()),
        "options": options or [],
        "jobs": [
            {
                "target": job["target"],
                "archive": bool(job.get("archive", False)),
                "args": [*job["args"], *(options or [])],
                "status": "pending",
                "attempts": 0,
                "started_at": None,
                "finished_at": None,
                "exit_code": None,
                "deploy_started": False,
            }
            for job in jobs
        ],
    }
    _save_state(state_path, state)
    return state_path


def _select_checkpoint(state_dir: Path, queue_id: str | None) -> Path:
    if queue_id:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", queue_id):
            raise ValueError("ID checkpoint tidak valid.")
        state_path = state_dir / f"{queue_id}.json"
        if not state_path.is_file():
            raise ValueError(f"Checkpoint '{queue_id}' tidak ditemukan.")
        return state_path

    candidates = []
    for state_path in state_dir.glob("queue_*.json"):
        try:
            state = _load_state(state_path)
        except ValueError:
            continue
        if state.get("status") != "success":
            candidates.append((state.get("updated_at", ""), state_path))
    if not candidates:
        raise ValueError("Tidak ada checkpoint gagal atau terhenti untuk dilanjutkan.")
    return max(candidates, key=lambda item: item[0])[1]


def _terminate_active_process() -> None:
    global _active_process
    if _active_process is not None and _active_process.poll() is None:
        try:
            os.killpg(_active_process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def _handle_signal(signum, _frame) -> None:
    global _interrupted
    _interrupted = True
    _terminate_active_process()


def run_state(state_path: Path) -> int:
    global _active_process, _interrupted
    state_path = state_path.resolve()
    state = _load_state(state_path)
    lock_path = state_path.with_suffix(".lock")
    with lock_path.open("a", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError(f"Checkpoint '{state['id']}' sedang berjalan.") from exc

        if state.get("status") == "success":
            raise ValueError(f"Checkpoint '{state['id']}' sudah selesai.")
        if not state.get("deploy_script") or not Path(state["deploy_script"]).is_file():
            raise ValueError("Script deploy pada checkpoint tidak ditemukan.")

        _interrupted = False
        prior_handlers = {
            signum: signal.signal(signum, _handle_signal)
            for signum in (signal.SIGINT, signal.SIGTERM)
        }
        try:
            state["status"] = "running"
            state["started_at"] = state.get("started_at") or _now()
            state["finished_at"] = None
            for job in state["jobs"]:
                if job["status"] == "running":
                    job["status"] = "pending"
            _save_state(state_path, state)

            total = len(state["jobs"])
            for index, job in enumerate(state["jobs"], start=1):
                if job["status"] == "success":
                    print(
                        f"[{index}/{total}] ✓ Lewati {job['target']} (sudah berhasil).",
                        flush=True,
                    )
                    continue
                if _interrupted:
                    break

                retrying = job["status"] == "failed" or job["attempts"] > 0
                command_args = list(job["args"])
                if retrying and job.get("deploy_started"):
                    command_args = [
                        arg for arg in command_args if arg != "--replace-existing"
                    ]
                    if "--resume-existing" not in command_args:
                        command_args.append("--resume-existing")

                job["status"] = "running"
                job["attempts"] += 1
                job["started_at"] = _now()
                job["finished_at"] = None
                job["exit_code"] = None
                _save_state(state_path, state)
                action = "Ulangi" if retrying else "Deploy"
                print(f"\n[{index}/{total}] {action}: {job['target']}", flush=True)

                try:
                    _active_process = subprocess.Popen(
                        ["bash", state["deploy_script"], *command_args],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        start_new_session=True,
                    )
                    assert _active_process.stdout is not None
                    for line in _active_process.stdout:
                        print(line, end="", flush=True)
                        if (
                            "Checkpoint: target " in line
                            and " lolos pemeriksaan " in line
                            and not job.get("deploy_started")
                        ):
                            job["deploy_started"] = True
                            _save_state(state_path, state)
                    try:
                        exit_code = _active_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        _terminate_active_process()
                        exit_code = _active_process.wait()
                except OSError as exc:
                    print(f"❌ Gagal menjalankan deploy: {exc}", file=sys.stderr, flush=True)
                    exit_code = 127
                finally:
                    _active_process = None

                if _interrupted:
                    job["status"] = "pending"
                    job["exit_code"] = None
                    _save_state(state_path, state)
                    break

                job["exit_code"] = exit_code
                job["status"] = "success" if exit_code == 0 else "failed"
                job["finished_at"] = _now()
                _save_state(state_path, state)
                marker = "✓" if exit_code == 0 else "❌"
                print(
                    f"[{index}/{total}] {marker} Checkpoint {job['status']}: {job['target']}",
                    flush=True,
                )

            if _interrupted:
                state["status"] = "interrupted"
                print(
                    "\n⏸ Deploy terhenti. Project yang sudah berhasil tersimpan; "
                    "project aktif akan diulang dari awal saat resume.",
                    flush=True,
                )
                return 130

            state["status"] = (
                "success"
                if all(job["status"] == "success" for job in state["jobs"])
                else "failed"
            )
            print(f"\nCheckpoint {state['id']}: {state['status']}", flush=True)
            return 0 if state["status"] == "success" else 1
        finally:
            state["finished_at"] = _now()
            _save_state(state_path, state)
            for signum, previous_handler in prior_handlers.items():
                signal.signal(signum, previous_handler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("run-new", help="Create and run a deployment batch")
    new_parser.add_argument("--state-dir", type=Path, required=True)
    new_parser.add_argument("--deploy-script", type=Path, required=True)
    new_parser.add_argument("--target", action="append", required=True)
    new_parser.add_argument("--deploy-option", action="append", default=[])

    run_parser = subparsers.add_parser("run", help="Run or resume a saved checkpoint")
    run_parser.add_argument("--state-file", type=Path, required=True)

    resume_parser = subparsers.add_parser("resume", help="Resume a saved checkpoint")
    resume_parser.add_argument("--state-dir", type=Path, required=True)
    resume_parser.add_argument("--id", default="")

    args = parser.parse_args()
    try:
        if args.command == "run-new":
            jobs = []
            for target in args.target:
                if not target.strip():
                    raise ValueError("Path project tidak boleh kosong.")
                lower_target = target.lower()
                jobs.append(
                    {
                        "target": target,
                        "archive": lower_target.endswith(ARCHIVE_SUFFIXES),
                        "args": [target],
                    }
                )
            state_path = create_state(
                args.state_dir, args.deploy_script, jobs, args.deploy_option
            )
            print(f"Checkpoint ID: {state_path.stem}", flush=True)
            return run_state(state_path)
        if args.command == "resume":
            state_path = _select_checkpoint(args.state_dir, args.id or None)
            print(f"Melanjutkan checkpoint: {state_path.stem}", flush=True)
            return run_state(state_path)
        return run_state(args.state_file)
    except ValueError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
