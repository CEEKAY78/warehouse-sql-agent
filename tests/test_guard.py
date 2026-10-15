import duckdb
import pytest

from wsa.guard import GuardError, QueryTimeout, guard_sql, run_readonly


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("g") / "g.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE t AS SELECT range AS x FROM range(500)")
    con.close()
    return path


def test_select_and_with_are_wrapped_in_a_row_cap():
    assert guard_sql("SELECT x FROM t;", max_rows=50) == (
        "SELECT * FROM (SELECT x FROM t) AS q LIMIT 50"
    )
    assert guard_sql("  with a as (select 1) select * from a", max_rows=5).startswith(
        "SELECT * FROM (with a as (select 1) select * from a) AS q LIMIT 5"
    )


def test_markdown_fences_are_stripped():
    assert guard_sql("```sql\nSELECT 1\n```", max_rows=10) == (
        "SELECT * FROM (SELECT 1) AS q LIMIT 10"
    )


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE t",
        "INSERT INTO t VALUES (1)",
        "UPDATE t SET x = 1",
        "DELETE FROM t",
        "CREATE TABLE z AS SELECT 1",
        "COPY t TO 'out.csv'",
        "ATTACH 'other.db'",
        "SET enable_external_access = true",
        "PRAGMA database_list",
        "SELECT 1; DROP TABLE t",
        "",
        "SELEC x FROM t",
    ],
)
def test_anything_but_one_read_query_is_rejected(sql):
    with pytest.raises(GuardError):
        guard_sql(sql)


def test_run_readonly_returns_columns_and_rows(db):
    result = run_readonly(db, "SELECT x, x * 2 AS y FROM t WHERE x < 3 ORDER BY x")
    assert result.columns == ["x", "y"]
    assert result.rows == [(0, 0), (1, 2), (2, 4)]


def test_run_readonly_caps_rows(db):
    assert len(run_readonly(db, "SELECT x FROM t", max_rows=20).rows) == 20


def test_files_on_disk_cannot_be_read(db, tmp_path):
    secret = tmp_path / "secret.csv"
    secret.write_text("a\n1\n")
    with pytest.raises(GuardError):
        run_readonly(db, f"SELECT * FROM read_csv('{secret.as_posix()}')")


def test_database_cannot_be_written(db):
    with pytest.raises(GuardError):
        run_readonly(db, "CREATE TABLE z AS SELECT 1")


def test_slow_query_times_out(db):
    with pytest.raises(QueryTimeout):
        run_readonly(
            db, "SELECT sum(a.range * b.range) FROM range(200000) a, range(200000) b",
            timeout_s=0.5,
        )
