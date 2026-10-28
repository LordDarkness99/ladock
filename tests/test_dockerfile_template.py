from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_php_image_includes_mysqli_and_relies_on_compose_source_mounts():
    dockerfile = (ROOT / "templates" / "Dockerfile").read_text(encoding="utf-8")
    monolith_compose = (ROOT / "templates" / "docker-compose-app.yml.tpl").read_text(
        encoding="utf-8"
    )

    assert "RUN docker-php-ext-install mysqli" in dockerfile
    assert "COPY src/" not in dockerfile
    assert "./src:/var/www" in monolith_compose


def test_gateway_image_includes_generated_root_dashboard():
    dockerfile = (ROOT / "templates" / "gateway.Dockerfile").read_text(
        encoding="utf-8"
    )
    httpd_config = (ROOT / "templates" / "gateway-httpd.conf").read_text(
        encoding="utf-8"
    )

    assert "COPY dashboard.html /usr/local/apache2/htdocs/dashboard.html" in dockerfile
    assert "LoadModule dir_module" in httpd_config
    assert "LoadModule mime_module" in httpd_config
    assert "TypesConfig conf/mime.types" in httpd_config
    assert "AddDefaultCharset UTF-8" in httpd_config
    assert "DirectoryIndex dashboard.html" in httpd_config
