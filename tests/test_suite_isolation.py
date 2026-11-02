from sqldesk.models import User, db
from tests import BaseTestCase


class TestEachTestStartsWithAnEmptyDatabase(BaseTestCase):
    """
    `BaseTestCase.setUp` builds the schema once per process and empties the
    tables per test, so the part that can fail quietly is the emptying. A
    reset that stops resetting does not raise: the suite goes on passing in
    most places and failing in the few that count rows, which reads like
    flakiness rather than a broken harness.

    unittest runs a class's methods in alphabetical order, so the first of
    these leaves a committed row behind and the second is the one that says
    whether the reset took it away.
    """

    EMAIL = "leftover@example.com"

    def test_a_commits_a_user_that_the_next_test_must_not_see(self):
        self.factory.create_user(email=self.EMAIL)
        db.session.commit()
        self.assertIsNotNone(User.query.filter(User.email == self.EMAIL).first())

    def test_b_does_not_see_the_user_the_previous_test_committed(self):
        self.assertIsNone(
            User.query.filter(User.email == self.EMAIL).first(),
            "a row committed by the previous test survived into this one",
        )

    def test_sequences_restart_so_ids_do_not_drift_across_the_suite(self):
        """
        `RESTART IDENTITY` is what keeps this equivalent to a fresh schema.
        Without it the ids climb all run, and a test that happens to assume a
        low id passes early in the suite and fails late in it.
        """
        user = self.factory.create_user(email="first@example.com")
        db.session.commit()
        self.assertEqual(1, user.id)
