import pytest

from src.sql_safety import check_sql


@pytest.mark.parametrize("sql", [
    "SELECT * FROM data",
    "select region, sum(sales) from data group by 1",
    "WITH a AS (SELECT 1) SELECT * FROM a",
    "SELECT update_count FROM data",                       # keyword inside a column name
    "SELECT replace(city, 'a', 'b') FROM data",            # replace() is a normal function
    "SELECT * FROM data;",                                 # one trailing semicolon is fine
])
def test_safe_queries_are_allowed(sql):
    assert check_sql(sql)[0] is True


@pytest.mark.parametrize("sql", [
    "DROP TABLE data",
    "DELETE FROM data",
    "UPDATE data SET sales = 0",
    "INSERT INTO data VALUES (1)",
    "SELECT 1; DELETE FROM data",                          # second statement
    "COPY data TO 'x.csv'",
    "CREATE TABLE x AS SELECT 1",
    "PRAGMA database_list",
    "",
])
def test_dangerous_queries_are_blocked(sql):
    assert check_sql(sql)[0] is False


def test_keywords_hidden_in_comments_do_not_confuse_the_check():
    assert check_sql("SELECT * FROM data -- drop table data")[0] is True
    assert check_sql("/* harmless */ DROP TABLE data")[0] is False