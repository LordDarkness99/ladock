from scripts.db_import import prepare_dump_sql


def test_dump_database_directives_are_removed_without_changing_insert_literals():
    dump = (
        "CREATE DATABASE `old_db`;\n"
        "USE `old_db`;\n"
        "INSERT INTO `wp_options` VALUES (1, 'string says USE other_db; keep it');\n"
        "/*!40100 CREATE DATABASE `conditional_db` */;\n"
        "/*!40100 USE `conditional_db` */;\n"
    )

    prepared = prepare_dump_sql(dump, "target_db")

    assert prepared.startswith("USE `target_db`;\n")
    assert "CREATE DATABASE `old_db`;" not in prepared
    assert "USE `old_db`;" not in prepared
    assert "CREATE DATABASE `conditional_db`" not in prepared
    assert "USE `conditional_db`" not in prepared
    assert "'string says USE other_db; keep it'" in prepared
