import json
from pathlib import Path

import pytest

from scripts.runtime_build import prepare_runtime


def _prepare(tmp_path: Path, stack: dict, files: dict[str, str] | None = None) -> tuple[dict, str]:
    source = tmp_path / "source"
    source.mkdir()
    for name, content in (files or {}).items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    stack_file = tmp_path / "stack.json"
    stack_file.write_text(json.dumps(stack), encoding="utf-8")
    metadata_file = tmp_path / "runtime.json"
    metadata = prepare_runtime(stack_file, source, metadata_file)
    return metadata, (source / metadata["dockerfile"]).read_text(encoding="utf-8") if metadata["dockerfile"] != "Dockerfile" else ""


@pytest.mark.parametrize(
    ("language", "version", "files", "expected_port", "dockerfile_contains"),
    [
        (
            "Node.js",
            "22.4.1",
            {"package.json": '{"scripts":{"start":"node server.js"}}', "server.js": ""},
            3000,
            "FROM node:22.4.1-bookworm-slim",
        ),
        (
            "Python",
            "3.12.3",
            {"requirements.txt": "fastapi\n", "main.py": ""},
            8000,
            "FROM python:3.12.3-slim",
        ),
        (
            "Go",
            "1.23.1",
            {"go.mod": "module example.com/app\n", "main.go": "package main\nfunc main() {}"},
            8080,
            "FROM golang:1.23.1-alpine",
        ),
        (
            "Ruby",
            "3.2.4",
            {"Gemfile": "source 'https://rubygems.org'\n", "app.rb": ""},
            3000,
            "FROM ruby:3.2.4-slim",
        ),
        (
            "Java",
            "21",
            {"pom.xml": "<project><artifactId>spring-boot</artifactId></project>"},
            8080,
            "FROM maven:3-eclipse-temurin-21",
        ),
    ],
)
def test_generates_language_specific_dockerfile_and_port(
    tmp_path, language, version, files, expected_port, dockerfile_contains
):
    metadata, dockerfile = _prepare(
        tmp_path,
        {
            "primary_language": language,
            "runtime_version": version,
            "framework": (
                "FastAPI"
                if language == "Python"
                else "Spring Boot"
                if language == "Java"
                else "Native"
            ),
        },
        files,
    )

    assert metadata["language"] == language
    assert metadata["version"] == version
    assert metadata["container_port"] == expected_port
    assert not metadata["custom_dockerfile"]
    assert dockerfile_contains in dockerfile


def test_project_dockerfile_takes_precedence_for_detected_runtime(tmp_path):
    metadata, _ = _prepare(
        tmp_path,
        {"primary_language": "Node.js", "runtime_version": "20"},
        {"Dockerfile": "FROM node:20\n"},
    )

    assert metadata["custom_dockerfile"]
    assert metadata["dockerfile"] == "Dockerfile"
    assert metadata["container_port"] == 3000


@pytest.mark.parametrize(
    ("files", "expected_document_root"),
    [
        ({"index.php": "<?php"}, "/var/www"),
        ({"public/index.php": "<?php"}, "/var/www/public"),
        ({"web/index.php": "<?php"}, "/var/www/web"),
    ],
)
def test_php_document_root_follows_application_entrypoint(
    tmp_path, files, expected_document_root
):
    metadata, _ = _prepare(
        tmp_path,
        {"primary_language": "PHP", "runtime_version": "8.2"},
        files,
    )

    assert metadata["document_root"] == expected_document_root


def test_custom_dockerfile_can_build_unsupported_detected_language(tmp_path):
    metadata, _ = _prepare(
        tmp_path,
        {"primary_language": "Unknown", "runtime_version": "Unknown"},
        {"Dockerfile": "FROM alpine:3.20\n"},
    )

    assert metadata["custom_dockerfile"]
    assert metadata["container_port"] == 80


def test_custom_dockerfile_can_declare_an_unpinned_runtime_version(tmp_path):
    metadata, _ = _prepare(
        tmp_path,
        {"primary_language": "Node.js", "runtime_version": "Unknown"},
        {"Dockerfile": "FROM node:latest\n"},
    )

    assert metadata["custom_dockerfile"]
    assert metadata["version"] == "Unknown"
    assert metadata["container_port"] == 3000


def test_node_requires_a_detectable_start_command(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "package.json").write_text('{"name":"missing-start"}', encoding="utf-8")
    stack_file = tmp_path / "stack.json"
    stack_file.write_text(
        json.dumps({"primary_language": "Node.js", "runtime_version": "20"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="scripts.start"):
        prepare_runtime(stack_file, source, tmp_path / "runtime.json")


def test_container_port_can_be_overridden_in_dotenv(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "package.json").write_text(
        '{"scripts":{"start":"node server.js"}}', encoding="utf-8"
    )
    (source / "server.js").write_text("", encoding="utf-8")
    (source / ".env").write_text("PORT=3100\n", encoding="utf-8")
    stack_file = tmp_path / "stack.json"
    stack_file.write_text(
        json.dumps({"primary_language": "Node.js", "runtime_version": "20"}),
        encoding="utf-8",
    )

    metadata = prepare_runtime(stack_file, source, tmp_path / "runtime.json")

    assert metadata["container_port"] == 3100


def test_invalid_dotenv_container_port_is_rejected(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "Dockerfile").write_text("FROM node:20\n", encoding="utf-8")
    (source / ".env").write_text("LADOCK_CONTAINER_PORT=invalid\n", encoding="utf-8")
    stack_file = tmp_path / "stack.json"
    stack_file.write_text(
        json.dumps({"primary_language": "Node.js", "runtime_version": "20"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Port runtime tidak valid"):
        prepare_runtime(stack_file, source, tmp_path / "runtime.json")


def test_generated_dockerignore_keeps_environment_secrets_out_of_images(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "package.json").write_text(
        '{"scripts":{"start":"node server.js"}}', encoding="utf-8"
    )
    (source / "server.js").write_text("", encoding="utf-8")
    stack_file = tmp_path / "stack.json"
    stack_file.write_text(
        json.dumps({"primary_language": "Node.js", "runtime_version": "20"}),
        encoding="utf-8",
    )

    prepare_runtime(stack_file, source, tmp_path / "runtime.json")

    dockerignore = (source / ".dockerignore").read_text(encoding="utf-8")
    assert ".env\n" in dockerignore
    assert "**/.env\n" in dockerignore
    assert "node_modules\n" in dockerignore


def test_existing_dockerignore_is_preserved_and_protected_from_env_leaks(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "Dockerfile").write_text("FROM node:20\n", encoding="utf-8")
    (source / ".dockerignore").write_text("custom-cache\n", encoding="utf-8")
    stack_file = tmp_path / "stack.json"
    stack_file.write_text(
        json.dumps({"primary_language": "Node.js", "runtime_version": "20"}),
        encoding="utf-8",
    )

    prepare_runtime(stack_file, source, tmp_path / "runtime.json")

    dockerignore = (source / ".dockerignore").read_text(encoding="utf-8")
    assert dockerignore.startswith("custom-cache\n")
    assert ".env\n" in dockerignore
