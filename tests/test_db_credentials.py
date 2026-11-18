from scripts.db_credentials import service_db_username


def test_service_usernames_are_unique_for_long_project_names():
    project_name = "541b66b4d6fcd95b_cpmove_imunisasijtm"

    individu = service_db_username(project_name, "individu")
    tesis = service_db_username(project_name, "tesis")

    assert individu != tesis
    assert len(individu) <= 32
    assert len(tesis) <= 32
    assert individu == service_db_username(project_name, "individu")


def test_service_username_replaces_a_legacy_user_that_collides():
    project_name = "541b66b4d6fcd95b_cpmove_imunisasijtm"
    legacy_username = "541b66b4d6fcd95b_cpm_u"

    first = service_db_username(
        project_name,
        "individu",
        preferred=legacy_username,
    )
    second = service_db_username(
        project_name,
        "tesis",
        preferred=legacy_username,
        used=[first],
    )

    assert first == legacy_username
    assert second != first
    assert second == service_db_username(project_name, "tesis")
