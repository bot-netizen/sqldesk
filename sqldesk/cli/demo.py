from click import argument, option
from flask.cli import AppGroup

manager = AppGroup(help="Demo content: data, every visualization, a dashboard and a notebook.")


def _org_and_user(org_slug, email):
    from sqldesk import models

    org = models.Organization.get_by_slug(org_slug)
    if org is None:
        raise SystemExit("No organization with slug {!r}.".format(org_slug))

    if email:
        user = models.User.query.filter(models.User.org == org, models.User.email == email).first()
        if user is None:
            raise SystemExit("No user {!r} in {}.".format(email, org_slug))
    else:
        # Whoever set the install up. A demo belongs to somebody, and an
        # admin is the one person certain to be able to see all of it.
        user = models.User.query.filter(models.User.org == org).order_by(models.User.id.asc()).first()
        if user is None:
            raise SystemExit("{} has no users yet.".format(org_slug))
    return org, user


@manager.command(name="seed")
@argument("org_slug", default="default", required=False)
@option("--user", "email", default=None, help="Who owns it. The first user by default.")
def seed(org_slug, email):
    """Build the demo. Safe to run again: it updates rather than duplicates."""
    from sqldesk import demo

    org, user = _org_and_user(org_slug, email)
    made = demo.seed(org, user)

    print("Demo seeded in {} as {}.".format(org.slug, user.email))
    print("  data source  {}".format(made["data_source"].name))
    print("  queries      {}".format(len(made["queries"])))
    print("  charts       {} (one of every type)".format(len(made["visualizations"])))
    print("  dashboard    {}".format(made["dashboard"].name))
    print("  notebook     {}".format(made["notebook"].name))
    print()
    print("Nothing has been run yet -- open the dashboard and press Refresh, or")
    print("run `manage demo run` to fill in the results first.")


@manager.command(name="remove")
@argument("org_slug", default="default", required=False)
def remove(org_slug):
    """Take it all away again, by tag rather than by name."""
    from sqldesk import demo, models

    org = models.Organization.get_by_slug(org_slug)
    if org is None:
        raise SystemExit("No organization with slug {!r}.".format(org_slug))

    gone = demo.remove(org)
    print(
        "Removed {queries} queries, {dashboards} dashboards, {notebooks} notebooks "
        "and {data_sources} data source.".format(**gone)
    )


@manager.command(name="run")
@argument("org_slug", default="default", required=False)
def run(org_slug):
    """
    Execute every demo query once, so the dashboard opens with numbers on it.

    Here rather than left to the browser because a dashboard whose widgets
    all say "never run" demonstrates nothing, and because this is also the
    check that every query in the demo is valid SQL against the data the
    demo built -- which is the half of "does it work" that a seeder cannot
    answer by writing rows.
    """
    from datetime import datetime

    from sqldesk import demo, models

    org = models.Organization.get_by_slug(org_slug)
    if org is None:
        raise SystemExit("No organization with slug {!r}.".format(org_slug))

    queries = [
        one
        for one in models.Query.query.filter(models.Query.org == org, models.Query.is_archived.is_(False)).all()
        if demo.TAG in (one.tags or [])
    ]
    if not queries:
        raise SystemExit("Nothing to run. Seed the demo first.")

    failed = 0
    for query in queries:
        runner = query.data_source.query_runner
        rows, error = runner.run_query(query.query_text, query.user)
        if error:
            failed += 1
            print("  FAILED  {}: {}".format(query.name, error))
            continue
        result = models.QueryResult.store_result(
            org.id, query.data_source, query.query_hash, query.query_text, rows, 0, datetime.utcnow()
        )
        query.latest_query_data = result
        models.db.session.add(query)
        print("  ok      {}".format(query.name))
    models.db.session.commit()

    print()
    if failed:
        raise SystemExit("{} of {} demo queries failed.".format(failed, len(queries)))
    print("All {} demo queries ran.".format(len(queries)))
