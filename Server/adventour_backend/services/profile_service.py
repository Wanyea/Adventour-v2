"""Validation for user-authored profile fields."""

import unicodedata

from sqlalchemy import inspect, text


HOME_CITY_MAX_LENGTH = 160


def normalize_home_city(value):
    """Return a trimmed locality or ``None``; reject invalid client input.

    A home city is deliberately free-form user text. It is not geocoded or
    matched to a provider, so localities outside a particular country work too.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("home_city must be a string or null")

    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > HOME_CITY_MAX_LENGTH:
        raise ValueError(f"home_city must be at most {HOME_CITY_MAX_LENGTH} characters")
    if any(unicodedata.category(character) == "Cc" for character in normalized):
        raise ValueError("home_city must not contain control characters")
    return normalized


def ensure_user_profile_columns(engine, table_name):
    """Add profile columns independently for legacy local schemas."""
    columns = {column["name"] for column in inspect(engine).get_columns(table_name)}
    quoted_table = engine.dialect.identifier_preparer.quote(table_name)
    with engine.begin() as connection:
        if "date_of_birth" not in columns:
            connection.execute(text(f"ALTER TABLE {quoted_table} ADD COLUMN date_of_birth DATE"))
        if "home_city" not in columns:
            connection.execute(text(f"ALTER TABLE {quoted_table} ADD COLUMN home_city VARCHAR(160)"))
