"""
Small shared SQL fragments.

Kept in one place so the several list endpoints that return a script's tags
agree on how those tags are aggregated and split apart again.
"""

# ASCII unit separator. SQLite's `GROUP_CONCAT(DISTINCT x)` only supports the
# single-argument form, which joins with a comma, so a tag named "prod, eu"
# came back as two tags. The correlated subquery below can pass an explicit
# separator, and a control character cannot appear in a tag name.
TAG_SEPARATOR = "\x1f"

# Correlated subquery returning a script's tag names.
# Besides fixing the separator, this removes the script_tags/tags joins from
# the outer SELECT, so a script with N tags no longer produces N duplicate rows
# that GROUP BY then has to collapse.
TAGS_SUBQUERY = """(
    SELECT GROUP_CONCAT(tag_names.name, char(31))
    FROM (
        SELECT DISTINCT t2.name AS name
        FROM script_tags st2
        JOIN tags t2 ON t2.id = st2.tag_id
        WHERE st2.script_id = s.id
        ORDER BY t2.name
    ) AS tag_names
)"""


def split_tags(value) -> list:
    """Split an aggregated tag string back into a list."""
    if not value:
        return []
    return [tag for tag in str(value).split(TAG_SEPARATOR) if tag]
