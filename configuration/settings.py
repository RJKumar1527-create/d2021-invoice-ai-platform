from __future__ import annotations

import os

from dataclasses import dataclass


TRUE_VALUES = {
    "1",
    "true",
    "yes",
    "on",
}

FALSE_VALUES = {
    "0",
    "false",
    "no",
    "off",
}

SUPPORTED_ENVIRONMENTS = {
    "development",
    "test",
    "production",
}


def read_boolean(
    name: str,
    default: bool,
) -> bool:
    raw_value = os.getenv(
        name
    )

    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()

    if normalized in TRUE_VALUES:
        return True

    if normalized in FALSE_VALUES:
        return False

    raise ValueError(
        f"{name} must be one of: "
        "true, false, 1, 0, yes, no, on, off."
    )


def read_positive_integer(
    name: str,
    default: int,
) -> int:
    raw_value = os.getenv(
        name
    )

    if raw_value is None:
        return default

    try:
        value = int(
            raw_value
        )

    except ValueError as error:
        raise ValueError(
            f"{name} must be an integer."
        ) from error

    if value < 1:
        raise ValueError(
            f"{name} must be greater than zero."
        )

    return value


def read_extensions(
    demo_mode: bool,
) -> tuple[str, ...]:
    default_value = (
        ".uff,.txt"
        if demo_mode
        else ".uff"
    )

    raw_value = os.getenv(
        "ALLOWED_FILE_EXTENSIONS",
        default_value,
    )

    extensions = []

    for item in raw_value.split(","):
        extension = (
            item.strip().lower()
        )

        if not extension:
            continue

        if not extension.startswith("."):
            extension = "." + extension

        if (
            not demo_mode
            and extension == ".txt"
        ):
            continue

        extensions.append(
            extension
        )

    unique_extensions = tuple(
        dict.fromkeys(
            extensions
        )
    )

    if not unique_extensions:
        raise ValueError(
            "At least one file extension "
            "must be allowed."
        )

    return unique_extensions


@dataclass(
    frozen=True
)
class ApplicationSettings:
    app_environment: str
    demo_mode: bool
    max_file_size_mb: int
    allowed_file_extensions: tuple[str, ...]
    stale_processing_minutes: int
    app_host: str
    app_port: int

    @property
    def max_file_size_bytes(
        self,
    ) -> int:
        return (
            self.max_file_size_mb
            * 1024
            * 1024
        )

    def public_configuration(
        self,
    ) -> dict:
        return {
            "app_environment": (
                self.app_environment
            ),
            "demo_mode": (
                self.demo_mode
            ),
            "max_file_size_mb": (
                self.max_file_size_mb
            ),
            "allowed_file_extensions": list(
                self.allowed_file_extensions
            ),
        }


def load_settings() -> ApplicationSettings:
    environment = os.getenv(
        "APP_ENV",
        "development",
    ).strip().lower()

    if (
        environment
        not in SUPPORTED_ENVIRONMENTS
    ):
        raise ValueError(
            "APP_ENV must be development, "
            "test, or production."
        )

    demo_mode = read_boolean(
        "DEMO_MODE",
        environment != "production",
    )

    if (
        environment == "production"
        and demo_mode
    ):
        raise ValueError(
            "DEMO_MODE must be false when "
            "APP_ENV is production."
        )

    return ApplicationSettings(
        app_environment=environment,
        demo_mode=demo_mode,
        max_file_size_mb=(
            read_positive_integer(
                "MAX_FILE_SIZE_MB",
                25,
            )
        ),
        allowed_file_extensions=(
            read_extensions(
                demo_mode
            )
        ),
        stale_processing_minutes=(
            read_positive_integer(
                "STALE_PROCESSING_MINUTES",
                30,
            )
        ),
        app_host=os.getenv(
            "APP_HOST",
            "127.0.0.1",
        ).strip(),
        app_port=read_positive_integer(
            "APP_PORT",
            8620,
        ),
    )


settings = load_settings()