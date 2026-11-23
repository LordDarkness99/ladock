import pytest

from scripts.select_composer_version import select_composer_version


@pytest.mark.parametrize(
    ("php_version", "composer_version"),
    [
        ("5.6", "2.2"),
        ("7.2.4", "2.2"),
        ("7.2.5", "2"),
        ("8.2", "2"),
    ],
)
def test_composer_version_matches_php_compatibility(php_version, composer_version):
    assert select_composer_version(php_version) == composer_version


def test_invalid_php_version_is_rejected():
    with pytest.raises(ValueError, match="Versi PHP tidak valid"):
        select_composer_version("5.x")
