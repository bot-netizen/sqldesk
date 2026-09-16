from unittest import TestCase

from tealdash.authentication.saml_auth import get_group_names


class SamlGroupAttributeTest(TestCase):
    """Group sync must keep working for identity providers configured for Redash.

    A regression here is silent: login still succeeds, the user simply loses
    every group assignment and with it their data source access.
    """

    def test_reads_the_tealdash_attribute(self):
        self.assertEqual(get_group_names({"TealdashGroups": ["analysts"]}), ["analysts"])

    def test_still_reads_the_attribute_existing_identity_providers_send(self):
        self.assertEqual(get_group_names({"RedashGroups": ["analysts"]}), ["analysts"])

    def test_the_new_name_wins_when_both_are_present(self):
        ava = {"TealdashGroups": ["new"], "RedashGroups": ["old"]}
        self.assertEqual(get_group_names(ava), ["new"])

    def test_no_attribute_means_no_group_change(self):
        self.assertIsNone(get_group_names({"FirstName": ["Ada"]}))

    def test_an_empty_list_is_still_an_assignment(self):
        # An IdP that sends the attribute with no groups is saying "none", which
        # must still be applied rather than treated as if it were absent.
        self.assertEqual(get_group_names({"RedashGroups": []}), [])
