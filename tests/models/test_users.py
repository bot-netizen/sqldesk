from sqldesk import redis_connection
from sqldesk.models import ApiUser, User, db
from sqldesk.models.users import LAST_ACTIVE_KEY, sync_last_active_at
from sqldesk.utils import dt_from_timestamp, json_dumps
from tests import BaseTestCase, authenticated_user


class TestUserUpdateGroupAssignments(BaseTestCase):
    def test_default_group_always_added(self):
        user = self.factory.create_user()

        user.update_group_assignments(["g_unknown"])
        db.session.refresh(user)

        self.assertCountEqual([user.org.default_group.id], user.group_ids)

    def test_update_group_assignments(self):
        user = self.factory.user
        new_group = self.factory.create_group(name="g1")

        user.update_group_assignments(["g1"])
        db.session.refresh(user)

        self.assertCountEqual([user.org.default_group.id, new_group.id], user.group_ids)


class TestUserFindByEmail(BaseTestCase):
    def test_finds_users(self):
        user = self.factory.create_user(email="test@example.com")
        user2 = self.factory.create_user(email="test@example.com", org=self.factory.create_org())

        users = User.find_by_email(user.email)
        self.assertIn(user, users)
        self.assertIn(user2, users)

    def test_finds_users_case_insensitive(self):
        user = self.factory.create_user(email="test@example.com")

        users = User.find_by_email("test@EXAMPLE.com")
        self.assertIn(user, users)


class TestUserGetByEmailAndOrg(BaseTestCase):
    def test_get_user_by_email_and_org(self):
        user = self.factory.create_user(email="test@example.com")

        found_user = User.get_by_email_and_org(user.email, user.org)
        self.assertEqual(user, found_user)

    def test_get_user_by_email_and_org_case_insensitive(self):
        user = self.factory.create_user(email="test@example.com")

        found_user = User.get_by_email_and_org("TEST@example.com", user.org)
        self.assertEqual(user, found_user)


class TestUserSearch(BaseTestCase):
    def test_non_unicode_search_string(self):
        user = self.factory.create_user(name="אריק")

        assert user in User.search(User.all(user.org), term="א")


class TestUserRegenerateApiKey(BaseTestCase):
    def test_regenerate_api_key(self):
        user = self.factory.user
        before_api_key = user.api_key
        user.regenerate_api_key()

        # check committed by research
        user = User.query.get(user.id)
        self.assertNotEqual(user.api_key, before_api_key)


class TestUserDetail(BaseTestCase):
    # def setUp(self):
    #     super(TestUserDetail, self).setUp()
    #     # redis_connection.flushdb()

    def test_userdetail_db_default(self):
        with authenticated_user(self.client) as user:
            self.assertEqual(user.details, {})
            self.assertIsNone(user.active_at)

    def test_userdetail_db_default_save(self):
        with authenticated_user(self.client) as user:
            user.details["test"] = 1
            db.session.commit()

            user_reloaded = User.query.filter_by(id=user.id).first()
            self.assertEqual(user.details["test"], 1)
            self.assertEqual(
                user_reloaded,
                User.query.filter(User.details["test"].astext.cast(db.Integer) == 1).first(),
            )

    def test_sync(self):
        with authenticated_user(self.client) as user:
            self.client.get("/default/")
            timestamp = dt_from_timestamp(redis_connection.hget(LAST_ACTIVE_KEY, user.id))
            sync_last_active_at()

            user_reloaded = User.query.filter(User.id == user.id).first()
            self.assertIn("active_at", user_reloaded.details)
            self.assertEqual(user_reloaded.active_at, timestamp)


class TestUserGetActualUser(BaseTestCase):
    def test_default_user(self):
        user_email = "test@example.com"
        user = self.factory.create_user(email=user_email)
        self.assertEqual(user.get_actual_user(), user_email)

    def test_api_user(self):
        user_email = "test@example.com"
        user = self.factory.create_user(email=user_email)
        api_user = ApiUser(user.api_key, user.org, user.group_ids)
        self.assertEqual(api_user.get_actual_user(), repr(api_user))


class TestWhatAProfilePictureIs(BaseTestCase):
    """
    It used to be a gravatar URL built from an MD5 of the email address.

    Offline that drew a broken image beside every query and logged a failed
    request for each. Online it told gravatar.com the MD5 of every address
    here, on every page load, from a tool whose point is running on your own
    machines. And almost nobody has one, so what came back was the identicon:
    an abstract pattern no more recognisable than initials, a round trip more
    expensive.
    """

    def test_nobody_is_given_a_picture_they_did_not_set(self):
        user = self.factory.create_user()

        self.assertIsNone(user.profile_image_url)

    def test_the_email_address_does_not_leave_the_install(self):
        user = self.factory.create_user(email="someone@example.com")

        self.assertNotIn("gravatar", str(user.profile_image_url or ""))
        self.assertNotIn("gravatar", json_dumps(user.to_dict()))

    def test_a_picture_somebody_set_is_kept(self):
        user = self.factory.create_user()
        user._profile_image_url = "https://example.com/me.png"
        db.session.commit()

        self.assertEqual("https://example.com/me.png", user.profile_image_url)
        self.assertEqual("https://example.com/me.png", user.to_dict()["profile_image_url"])

    def test_a_disabled_account_still_says_so_in_its_picture(self):
        # That image is making a statement, and it outranks both of the above.
        user = self.factory.create_user()
        user.disable()
        db.session.commit()

        # A request context because that path is built with `url_for`, which
        # is how it has always been -- the point here is which image wins.
        with self.app.test_request_context():
            self.assertIn("avatar", user.to_dict()["profile_image_url"])
