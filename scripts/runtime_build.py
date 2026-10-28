#!/usr/bin/env python3
"""Prepare a project-specific runtime Dockerfile and deployment metadata."""

import argparse
import json
import re
from pathlib import Path

if __package__:
    from .env_config import read_env_file
else:
    from env_config import read_env_file


PORTS = {
    "PHP": 80,
    "Node.js": 3000,
    "Python": 8000,
    "Go": 8080,
    "Ruby": 3000,
    "Java": 8080,
}


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _json_command(command: list[str]) -> str:
    return json.dumps(command)


def _node_dockerfile(source_dir: Path, version: str) -> str:
    package = _read_json(source_dir / "package.json")
    scripts = package.get("scripts", {})
    package_manager = "npm"
    if (source_dir / "pnpm-lock.yaml").is_file():
        package_manager = "pnpm"
        install = "RUN corepack enable && pnpm install --frozen-lockfile"
    elif (source_dir / "yarn.lock").is_file():
        package_manager = "yarn"
        install = "RUN corepack enable && yarn install --frozen-lockfile"
    elif (source_dir / "package-lock.json").is_file():
        install = "RUN npm ci"
    else:
        install = "RUN npm install"

    start_script = scripts.get("start")
    if start_script:
        command = [package_manager, "start"]
    elif package.get("dependencies", {}).get("next"):
        command = ["npx", "next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
    elif (source_dir / "server.js").is_file():
        command = ["node", "server.js"]
    elif (source_dir / "index.js").is_file():
        command = ["node", "index.js"]
    else:
        raise ValueError(
            "Service Node.js tidak memiliki scripts.start, server.js, atau index.js; "
            "tambahkan perintah start di package.json atau sediakan Dockerfile."
        )

    build = f"RUN {package_manager} run build\n" if scripts.get("build") else ""
    if package_manager != "npm" and command[0] == "npm":
        command[0] = package_manager
    return (
        f"FROM node:{version}-bookworm-slim\n"
        "WORKDIR /app\n"
        "COPY . .\n"
        f"{install}\n"
        f"{build}"
        "ENV NODE_ENV=production\n"
        "ENV PORT=3000\n"
        "EXPOSE 3000\n"
        f"CMD {_json_command(command)}\n"
    )


def _python_dockerfile(source_dir: Path, version: str, stack: dict) -> str:
    package_manager = stack.get("package_manager")
    if package_manager == "poetry":
        install = (
            "RUN pip install --no-cache-dir poetry && "
            "poetry config virtualenvs.create false && "
            "poetry install --only main --no-interaction --no-root\n"
            "RUN pip install --no-cache-dir gunicorn uvicorn\n"
        )
    elif package_manager == "pipenv":
        lock_option = "--deploy" if (source_dir / "Pipfile.lock").is_file() else ""
        install = (
            "RUN pip install --no-cache-dir pipenv && "
            f"pipenv install --system {lock_option} && "
            "pip install --no-cache-dir gunicorn uvicorn\n"
        )
    elif (source_dir / "requirements.txt").is_file():
        install = (
            "RUN pip install --no-cache-dir -r requirements.txt\n"
        )
    elif (source_dir / "pyproject.toml").is_file():
        install = "RUN pip install --no-cache-dir .\n"
    else:
        raise ValueError(
            "Service Python memerlukan requirements.txt, pyproject.toml, atau Pipfile."
        )
    if package_manager not in {"poetry", "pipenv"}:
        install += "RUN pip install --no-cache-dir gunicorn uvicorn\n"

    framework = stack.get("framework")
    if framework == "Django":
        manage_py = (source_dir / "manage.py").read_text(encoding="utf-8", errors="ignore")
        settings = re.search(
            r"DJANGO_SETTINGS_MODULE['\"]?\s*,\s*['\"]([^'\"]+)['\"]", manage_py
        )
        if not settings or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", settings.group(1)):
            raise ValueError(
                "Modul settings Django tidak dapat dideteksi dari manage.py; "
                "sediakan Dockerfile proyek."
            )
        wsgi_module = f"{settings.group(1).rsplit('.', 1)[0]}.wsgi:application"
        command = [
            "sh",
            "-c",
            f'exec gunicorn {wsgi_module} --bind "0.0.0.0:${{PORT:-8000}}"',
        ]
    elif framework == "FastAPI":
        module = "main" if (source_dir / "main.py").is_file() else "app"
        command = [
            "sh",
            "-c",
            f'exec uvicorn {module}:app --host 0.0.0.0 --port "${{PORT:-8000}}"',
        ]
    elif framework == "Flask":
        module = "app" if (source_dir / "app.py").is_file() else "main"
        command = [
            "sh",
            "-c",
            f'exec gunicorn --bind "0.0.0.0:${{PORT:-8000}}" {module}:app',
        ]
    elif (source_dir / "main.py").is_file():
        command = ["python", "main.py"]
    else:
        raise ValueError(
            "Entrypoint service Python tidak terdeteksi; sediakan Dockerfile proyek."
        )

    return (
        f"FROM python:{version}-slim\n"
        "WORKDIR /app\n"
        "ENV PYTHONDONTWRITEBYTECODE=1\n"
        "ENV PYTHONUNBUFFERED=1\n"
        "COPY . .\n"
        f"{install}"
        "ENV PORT=8000\n"
        "EXPOSE 8000\n"
        f"CMD {_json_command(command)}\n"
    )


def _go_dockerfile(version: str) -> str:
    return (
        f"FROM golang:{version}-alpine AS build\n"
        "WORKDIR /src\n"
        "COPY . .\n"
        "RUN CGO_ENABLED=0 go build -o /app ./\n"
        "FROM alpine:3.20\n"
        "RUN apk add --no-cache ca-certificates\n"
        "WORKDIR /app\n"
        "COPY --from=build /app /app/server\n"
        "ENV PORT=8080\n"
        "EXPOSE 8080\n"
        'CMD ["/app/server"]\n'
    )


def _ruby_dockerfile(source_dir: Path, version: str, stack: dict) -> str:
    if stack.get("framework") == "Ruby on Rails":
        command = [
            "sh",
            "-c",
            'exec bundle exec rails server -b 0.0.0.0 -p "${PORT:-3000}"',
        ]
        env = "ENV RAILS_ENV=production\n"
    elif (source_dir / "config.ru").is_file():
        command = [
            "sh",
            "-c",
            'exec bundle exec rackup --host 0.0.0.0 --port "${PORT:-3000}"',
        ]
        env = ""
    elif (source_dir / "app.rb").is_file():
        command = ["bundle", "exec", "ruby", "app.rb"]
        env = ""
    else:
        raise ValueError(
            "Entrypoint Ruby tidak terdeteksi; sediakan Dockerfile proyek."
        )
    return (
        f"FROM ruby:{version}-slim\n"
        "WORKDIR /app\n"
        "COPY . .\n"
        "RUN bundle install\n"
        f"{env}"
        "ENV PORT=3000\n"
        "EXPOSE 3000\n"
        f"CMD {_json_command(command)}\n"
    )


def _java_dockerfile(source_dir: Path, version: str, stack: dict) -> str:
    if stack.get("framework") != "Spring Boot":
        raise ValueError(
            "Build Java otomatis saat ini memerlukan Spring Boot; "
            "untuk aplikasi Java lain, sediakan Dockerfile proyek."
        )
    if (source_dir / "pom.xml").is_file():
        return (
            f"FROM maven:3-eclipse-temurin-{version} AS build\n"
            "WORKDIR /app\n"
            "COPY . .\n"
            "RUN mvn -B package -DskipTests\n"
            f"FROM eclipse-temurin:{version}-jre\n"
            "WORKDIR /app\n"
            "COPY --from=build /app/target /tmp/target\n"
            "RUN set -e; for jar in /tmp/target/*.jar; do "
            "case \"$jar\" in *-sources.jar|*-javadoc.jar|*/original-*) continue ;; esac; "
            "cp \"$jar\" /app/app.jar; break; done; test -s /app/app.jar\n"
            "ENV PORT=8080\n"
            "EXPOSE 8080\n"
            'CMD ["java", "-jar", "/app/app.jar"]\n'
        )
    if (source_dir / "gradlew").is_file():
        properties = (source_dir / "gradle/wrapper/gradle-wrapper.properties").read_text(
            encoding="utf-8", errors="ignore"
        )
        gradle_version = re.search(r"gradle-(\d+(?:\.\d+){1,2})-", properties)
        if not gradle_version:
            raise ValueError(
                "Versi Gradle wrapper tidak terdeteksi; sediakan Dockerfile proyek."
            )
        gradle_major = gradle_version.group(1).split(".", 1)[0]
        return (
            f"FROM gradle:{gradle_major}-jdk{version} AS build\n"
            "WORKDIR /app\n"
            "COPY . .\n"
            "RUN chmod +x gradlew && ./gradlew bootJar --no-daemon\n"
            f"FROM eclipse-temurin:{version}-jre\n"
            "WORKDIR /app\n"
            "COPY --from=build /app/build/libs /tmp/libs\n"
            "RUN set -e; for jar in /tmp/libs/*.jar; do "
            "case \"$jar\" in *-sources.jar|*-javadoc.jar|*/original-*) continue ;; esac; "
            "cp \"$jar\" /app/app.jar; break; done; test -s /app/app.jar\n"
            "ENV PORT=8080\n"
            "EXPOSE 8080\n"
            'CMD ["java", "-jar", "/app/app.jar"]\n'
        )
    raise ValueError(
        "Build Java otomatis memerlukan pom.xml atau Gradle wrapper (gradlew); "
        "sediakan Dockerfile proyek."
    )


def prepare_runtime(stack_path: Path, source_dir: Path, metadata_path: Path) -> dict:
    stack = _read_json(stack_path)
    if not stack:
        raise ValueError(f"Stack spec tidak dapat dibaca: {stack_path}")
    language = stack.get("primary_language", "Unknown")
    version = str(stack.get("runtime_version", ""))
    custom_dockerfile = (source_dir / "Dockerfile").is_file()
    if language not in PORTS and not custom_dockerfile:
        raise ValueError(f"Runtime belum didukung untuk build otomatis: {language}")
    if (
        language in PORTS
        and not custom_dockerfile
        and not re.fullmatch(r"\d+(?:\.\d+){0,2}", version)
    ):
        raise ValueError(f"Versi runtime tidak valid untuk {language}: {version!r}")

    env_values = read_env_file(source_dir / ".env")
    port_override = ""
    if language != "PHP" or custom_dockerfile:
        port_override = (
            env_values.get("LADOCK_CONTAINER_PORT")
            or env_values.get("PORT")
            or env_values.get("SERVER_PORT")
        )
    try:
        container_port = int(port_override) if port_override else PORTS.get(language, 80)
    except ValueError as exc:
        raise ValueError(f"Port runtime tidak valid di .env: {port_override!r}") from exc
    if not 1 <= container_port <= 65535:
        raise ValueError(f"Port runtime di luar rentang: {container_port}")

    document_root = "/var/www/public"
    if language == "PHP":
        if (source_dir / "public/index.php").is_file():
            document_root = "/var/www/public"
        elif (source_dir / "web/index.php").is_file():
            document_root = "/var/www/web"
        else:
            document_root = "/var/www"

    metadata = {
        "language": language,
        "version": version or "Unknown",
        "container_port": int(stack.get("container_port") or container_port),
        "working_dir": "/var/www" if language == "PHP" else "/app",
        "document_root": document_root,
        "custom_dockerfile": custom_dockerfile,
    }

    if language != "PHP" or custom_dockerfile:
        ignore_file = source_dir / ".dockerignore"
        ignore_content = (
            ignore_file.read_text(encoding="utf-8")
            if ignore_file.exists()
            else ".git\nnode_modules\nvendor\n.venv\nvenv\n__pycache__\ntarget\nbuild\n.gradle\n*.log\n"
        )
        required_ignores = (
            ".env",
            ".env.*",
            "**/.env",
            "**/.env.*",
        )
        missing_ignores = [pattern for pattern in required_ignores if pattern not in ignore_content.splitlines()]
        if missing_ignores:
            separator = "" if not ignore_content or ignore_content.endswith("\n") else "\n"
            ignore_file.write_text(
                ignore_content + separator + "\n".join(missing_ignores) + "\n",
                encoding="utf-8",
            )

    if metadata["custom_dockerfile"]:
        metadata["dockerfile"] = "Dockerfile"
    elif language == "PHP":
        metadata["dockerfile"] = "Dockerfile"
    else:
        dockerfile_path = source_dir / ".ladock.Dockerfile"
        builders = {
            "Node.js": lambda: _node_dockerfile(source_dir, version),
            "Python": lambda: _python_dockerfile(source_dir, version, stack),
            "Go": lambda: _go_dockerfile(version),
            "Ruby": lambda: _ruby_dockerfile(source_dir, version, stack),
            "Java": lambda: _java_dockerfile(source_dir, version, stack),
        }
        dockerfile_path.write_text(builders[language](), encoding="utf-8")
        metadata["dockerfile"] = ".ladock.Dockerfile"

    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    args = parser.parse_args()
    try:
        metadata = prepare_runtime(args.stack, args.source, args.metadata)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(
        f"Runtime build disiapkan: {metadata['language']} {metadata['version']} "
        f"({'Dockerfile proyek' if metadata['custom_dockerfile'] else metadata['dockerfile']})"
    )


if __name__ == "__main__":
    main()
