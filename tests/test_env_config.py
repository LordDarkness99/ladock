from pathlib import Path

from scripts.env_config import read_env_file, set_env_value


def test_reads_existing_dotenv_credentials_without_evaluating_contents(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        'DB_USERNAME="existing_user"\n'
        "DB_PASSWORD='p@ss # word'\n"
        "APP_KEY=base64:keep-this-key # comment\n"
        "VALUE=$(touch /tmp/should-not-run)\n",
        encoding="utf-8",
    )

    values = read_env_file(env_file)

    assert values["DB_USERNAME"] == "existing_user"
    assert values["DB_PASSWORD"] == "p@ss # word"
    assert values["APP_KEY"] == "base64:keep-this-key"
    assert values["VALUE"] == "$(touch /tmp/should-not-run)"


def test_updates_only_requested_environment_values_and_round_trips_special_chars(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("APP_KEY=keep-this-key\nDB_PASSWORD=old\n", encoding="utf-8")

    set_env_value(env_file, "DB_PASSWORD", 'new$pass\\"word#')

    values = read_env_file(env_file)
    assert values["APP_KEY"] == "keep-this-key"
    assert values["DB_PASSWORD"] == 'new$pass\\"word#'


def test_updates_every_duplicate_occurrence_of_an_environment_key(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("DB_HOST=old\nDB_HOST=older\n", encoding="utf-8")

    set_env_value(env_file, "DB_HOST", "central")

    assert read_env_file(env_file)["DB_HOST"] == "central"
    assert env_file.read_text(encoding="utf-8").count('DB_HOST="central"') == 2


def test_normalizes_existing_unquoted_dollar_value_for_compose(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("DB_PASSWORD=literal$pass\n", encoding="utf-8")

    set_env_value(env_file, "DB_PASSWORD", "literal$pass")

    assert read_env_file(env_file)["DB_PASSWORD"] == "literal$pass"
    assert env_file.read_text(encoding="utf-8") == 'DB_PASSWORD="literal\\$pass"\n'
