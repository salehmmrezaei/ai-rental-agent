"""Neon CLI environment compatibility without a network/database dependency."""
import os
from unittest.mock import patch

from app.config import Settings


def settings(**values):
    with patch.dict(os.environ, {}, clear=True):
        return Settings(_env_file=None, database_url='postgresql://localhost/casa', **values)


def test_neon_unpooled_url_is_used_for_migrations():
    with patch.dict(os.environ, {
        'DATABASE_URL': 'postgresql://runtime@pooler/casa',
        'DATABASE_URL_UNPOOLED': 'postgresql://owner@direct/casa',
    }, clear=True):
        config = Settings(_env_file=None)
    assert config.database_direct_url.get_secret_value() == 'postgresql://owner@direct/casa'
    assert config.database_url == 'postgresql://runtime@pooler/casa'


def test_explicit_direct_url_takes_precedence_over_neon_cli_alias():
    with patch.dict(os.environ, {
        'DATABASE_URL': 'postgresql://runtime@pooler/casa',
        'DATABASE_DIRECT_URL': 'postgresql://owner@preferred/casa',
        'DATABASE_URL_UNPOOLED': 'postgresql://owner@fallback/casa',
    }, clear=True):
        config = Settings(_env_file=None)
    assert config.database_direct_url.get_secret_value() == 'postgresql://owner@preferred/casa'


def test_existing_python_field_name_remains_supported():
    config = settings(database_direct_url='postgresql://owner@direct/casa')
    assert config.database_direct_url.get_secret_value() == 'postgresql://owner@direct/casa'


def test_runtime_does_not_require_owner_credentials():
    assert settings().database_direct_url is None
