"""The PostgreSQL schema fixture must give each test a private, reachable schema."""

import psycopg


def test_schema_fixture_pins_search_path(pg_target):
    with psycopg.connect(pg_target.libpq_dsn) as conn:
        assert conn.execute("select current_schema()").fetchone()[0] == pg_target.name
        conn.execute("create table probe (id int primary key)")
        conn.execute("insert into probe values (1)")
        conn.commit()

    with psycopg.connect(pg_target.libpq_dsn) as conn:
        assert conn.execute("select count(*) from probe").fetchone()[0] == 1


def test_two_schemas_do_not_share_tables(pg_target, postgres_dsn):
    with psycopg.connect(pg_target.libpq_dsn) as conn:
        conn.execute("create table only_here (id int)")
        conn.commit()

    with psycopg.connect(postgres_dsn) as conn:
        in_public = conn.execute(
            "select count(*) from information_schema.tables"
            " where table_name = 'only_here' and table_schema = 'public'"
        ).fetchone()[0]
        in_throwaway = conn.execute(
            "select count(*) from information_schema.tables"
            " where table_name = 'only_here' and table_schema = %s",
            (pg_target.name,),
        ).fetchone()[0]
    assert in_public == 0
    assert in_throwaway == 1


def test_pg_target_repr_hides_credential(pg_target):
    assert "postgres" not in repr(pg_target)
    assert repr(pg_target) == f"PgTarget(name={pg_target.name!r})"
