from scripts.generate_compose import build_db_compose


def test_db_compose_uses_separate_database_data_directory():
    compose = build_db_compose(
        project="sample",
        services=[{"name": "web", "http_port": 8081}],
        base_db_port=3308,
        db_creds={},
        db_root_pass="root-secret",
    )

    assert "../../db/sample/web/data:/var/lib/mysql" in compose
    assert "sample_web_dbdata" not in compose
    assert "\nvolumes:\n" not in compose
