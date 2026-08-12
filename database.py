import re


FORBIDDEN = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|GRANT|REVOKE|CALL)\b", re.I)


def normalize_select(sql):
    if not isinstance(sql, str):
        raise ValueError("SQL 必须是文本")
    sql = sql.strip()
    if not sql.upper().startswith("SELECT"):
        raise ValueError("Agent 只允许执行 SELECT 查询")
    if FORBIDDEN.search(sql) or "--" in sql or "/*" in sql:
        raise ValueError("SQL 包含不允许的操作或注释")
    body = sql.rstrip(";").strip()
    if ";" in body:
        raise ValueError("一次只能执行一条 SQL")
    return body + ";"


def execute_select(settings, sql, max_rows=100):
    import pymysql

    sql = normalize_select(sql)
    connection = pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            columns = [column[0] for column in cursor.description or []]
            rows = list(cursor.fetchmany(max_rows + 1))
            truncated = len(rows) > max_rows
            return columns, rows[:max_rows], truncated
    finally:
        connection.close()


def split_top_level(text):
    parts = []
    start = depth = 0
    for index, character in enumerate(text):
        if character == "(":
            depth += 1
        elif character == ")":
            depth = max(0, depth - 1)
        elif character == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return [part for part in parts if part]


def format_sql(sql):
    """将单行 SQL 排版为更适合终端阅读的多行形式。"""
    normalized = re.sub(r"\s+", " ", sql.strip())
    from_match = re.search(r"\sFROM\s", normalized, flags=re.I)
    if not from_match or not normalized.upper().startswith("SELECT "):
        return normalized
    select_body = normalized[len("SELECT "):from_match.start()].strip()
    rest = normalized[from_match.start() + 1 :]
    lines = ["SELECT"]
    fields = split_top_level(select_body)
    for index, field in enumerate(fields):
        lines.append(f"    {field}{',' if index < len(fields) - 1 else ''}")
    rest = re.sub(
        r"\s+(LEFT JOIN|RIGHT JOIN|INNER JOIN|JOIN|WHERE|GROUP BY|HAVING|ORDER BY|LIMIT|OFFSET)\s+",
        lambda match: f"\n{match.group(1).upper()} ",
        rest,
        flags=re.I,
    )
    return "\n".join(lines + rest.splitlines())


def format_table(columns, rows):
    if not columns:
        return "查询未返回列。"
    values = [[str(value) for value in row] for row in rows]
    widths = [len(str(column)) for column in columns]
    for row in values:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))
    header = " | ".join(str(column).ljust(widths[index]) for index, column in enumerate(columns))
    separator = "-+-".join("-" * width for width in widths)
    body = [" | ".join(value.ljust(widths[index]) for index, value in enumerate(row)) for row in values]
    return "\n".join([header, separator] + (body or ["0 行"]))
