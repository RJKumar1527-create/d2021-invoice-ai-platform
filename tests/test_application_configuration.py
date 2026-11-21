import importlib

import pytest


ENVIRONMENT_VARIABLES = [
    "APP_ENV",
    "DEMO_MODE",
    "MAX_FILE_SIZE_MB",
    "ALLOWED_FILE_EXTENSIONS",
    "STALE_PROCESSING_MINUTES",
    "APP_HOST",
    "APP_PORT",
]


def load_settings_module(
    monkeypatch,
    **values,
):
    for name in ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(
            name,
            raising=False,
        )

    for name, value in values.items():
        monkeypatch.setenv(
            name,
            str(value),
        )

    import configuration.settings as module

    return importlib.reload(
        module
    )


def test_development_defaults_enable_demo(
    monkeypatch,
):
    module = load_settings_module(
        monkeypatch
    )

    assert module.settings.demo_mode

    assert (
        module.settings.allowed_file_extensions
        == (
            ".uff",
            ".txt",
        )
    )

    assert (
        module.settings.max_file_size_mb
        == 25
    )


def test_production_removes_text_extension(
    monkeypatch,
):
    module = load_settings_module(
        monkeypatch,
        APP_ENV="production",
        DEMO_MODE="false",
        ALLOWED_FILE_EXTENSIONS=(
            ".uff,.txt"
        ),
    )

    assert not module.settings.demo_mode

    assert (
        module.settings.allowed_file_extensions
        == (
            ".uff",
        )
    )


def test_production_rejects_demo_mode(
    monkeypatch,
):
    with pytest.raises(
        ValueError,
        match="DEMO_MODE must be false",
    ):
        load_settings_module(
            monkeypatch,
            APP_ENV="production",
            DEMO_MODE="true",
        )


def test_invalid_file_size_is_rejected(
    monkeypatch,
):
    with pytest.raises(
        ValueError,
        match="MAX_FILE_SIZE_MB",
    ):
        load_settings_module(
            monkeypatch,
            MAX_FILE_SIZE_MB="0",
        )


def test_public_configuration_is_safe(
    monkeypatch,
):
    module = load_settings_module(
        monkeypatch
    )

    public = (
        module.settings
        .public_configuration()
    )

    assert set(public) == {
        "app_environment",
        "demo_mode",
        "max_file_size_mb",
        "allowed_file_extensions",
    }