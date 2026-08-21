import re


def _normalize_sql(query: str) -> str:
    value = re.sub(r"/\*.*?\*/", " ", query, flags=re.DOTALL)
    value = re.sub(r"--[^\n]*", " ", value)
    return value.strip()


def validate_read_only_sql(query: str) -> str:
    normalized = _normalize_sql(str(query).strip())
    statement = normalized.rstrip(";").strip()
    if not statement or ";" in statement:
        raise ValueError("Read-only SQL must contain exactly one statement")
    if not re.match(r"^(SELECT|EXPLAIN|SHOW|DESCRIBE|DESC)\b", statement, flags=re.IGNORECASE):
        raise ValueError("This SQL tool only permits read-only statements")
    return statement
