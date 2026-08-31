"""Phase 15 P3: derived AUTH_SECRET persistence under DATA_DIR.

A per-process random secret broke multi-worker uvicorn (each worker signed
with a different key) and logged every user out on restart. The derived
secret now lives in DATA_DIR/auth_secret.key (0600) and is reused.
"""

import os

from app.config import Settings


def _settings(tmp_path, **overrides) -> Settings:
    kwargs = {
        "DATA_DIR": str(tmp_path),
        "AUTH_ENABLED": True,
        "AUTH_SECRET": "",
        "API_KEYS": ["test-key"],
        "_env_file": None,
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


def test_derives_and_persists_secret(tmp_path):
    settings = _settings(tmp_path)

    key_file = tmp_path / "auth_secret.key"
    assert key_file.exists()
    assert settings.AUTH_SECRET == key_file.read_text().strip()
    assert len(settings.AUTH_SECRET) >= 64
    assert os.stat(key_file).st_mode & 0o777 == 0o600


def test_reuses_persisted_secret_across_instances(tmp_path):
    first = _settings(tmp_path)
    second = _settings(tmp_path)

    assert first.AUTH_SECRET == second.AUTH_SECRET


def test_existing_file_wins_over_regeneration(tmp_path):
    key_file = tmp_path / "auth_secret.key"
    key_file.write_text("a" * 64)

    settings = _settings(tmp_path)

    assert settings.AUTH_SECRET == "a" * 64


def test_explicit_secret_skips_derivation(tmp_path):
    settings = _settings(tmp_path, AUTH_SECRET="explicitly-set")

    assert settings.AUTH_SECRET == "explicitly-set"
    assert not (tmp_path / "auth_secret.key").exists()


def test_unusable_data_dir_still_yields_a_secret(tmp_path):
    # DATA_DIR points at a regular file: the key path cannot be created.
    not_a_dir = tmp_path / "not-a-dir"
    not_a_dir.write_text("x")

    settings = _settings(not_a_dir)

    assert len(settings.AUTH_SECRET) >= 64
