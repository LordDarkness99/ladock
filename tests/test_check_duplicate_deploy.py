from pathlib import Path

from scripts.check_duplicate_deploy import is_project_deployed, project_slug


def test_project_slug_matches_deploy_name_normalization():
    assert project_slug("My Project---API") == "my_project_api"


def test_detects_monolith_and_microservice_deployment_markers(tmp_path: Path):
    deploy_root = tmp_path / "apps"
    legacy_root = tmp_path / "legacy"
    (deploy_root / "monolith").mkdir(parents=True)
    (deploy_root / "monolith" / "docker-compose.yml").touch()
    (legacy_root / "micro").mkdir(parents=True)
    (legacy_root / "micro" / ".docker-compose-app.yml").touch()

    assert is_project_deployed("monolith", deploy_root, legacy_root, [])
    assert is_project_deployed("micro", deploy_root, legacy_root, [])


def test_detects_running_or_stopped_project_container_names(tmp_path: Path):
    deploy_root = tmp_path / "apps"
    legacy_root = tmp_path / "legacy"

    assert is_project_deployed("store", deploy_root, legacy_root, ["store_catalog_app"])
    assert is_project_deployed("store", deploy_root, legacy_root, ["store_gateway"])
    assert is_project_deployed("store", deploy_root, legacy_root, ["app_store"])


def test_does_not_match_another_projects_containers(tmp_path: Path):
    assert not is_project_deployed(
        "store",
        tmp_path / "apps",
        tmp_path / "legacy",
        ["storefront_app", "other_store_api_app"],
    )
