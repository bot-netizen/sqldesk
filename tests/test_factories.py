"""
The factories themselves, because two of this release's hardest bugs were
tests leaving state behind rather than code being wrong.

`ModelFactory` keeps its defaults on the instance and copied them shallowly,
so the `options={}` on the alert, visualization and widget factories and the
`data={"columns": {}, "rows": []}` on the query result factory were each one
object shared by every model that factory ever made. Nothing had tripped over
it yet; it needs one test that writes into `options` rather than replacing it,
and then the test that pays for it is a different one in a different file.
"""

from unittest import TestCase

from tests.factories import ModelFactory, Sequence


class TestTheFactoriesDoNotShareTheirDefaults(TestCase):
    def test_each_call_gets_its_own_copy_of_a_default(self):
        factory = ModelFactory(dict, options={}, data={"columns": {}, "rows": []})

        first = factory._get_kwargs({})
        second = factory._get_kwargs({})
        first["options"]["mine"] = True
        first["data"]["rows"].append({"a": 1})

        self.assertEqual({}, second["options"])
        self.assertEqual([], second["data"]["rows"])

    def test_and_the_default_on_the_factory_is_never_written_to(self):
        factory = ModelFactory(dict, options={})

        factory._get_kwargs({})["options"]["mine"] = True

        self.assertEqual({}, factory.kwargs["options"])

    def test_what_the_caller_passes_is_handed_through_as_it_is(self):
        """Only the factory's own defaults are copied: the caller's dict is the caller's."""
        factory = ModelFactory(dict, options={})
        mine = {"position": {"col": 1, "row": 2}}

        self.assertIs(mine, factory._get_kwargs({"options": mine})["options"])

    def test_a_callable_default_still_runs_once_per_call(self):
        """
        Which is why the copy is narrow. Deep-copying every default would copy
        the Sequence too, and each call would get a counter back at the value
        the one before it started from -- two users named "John Doe 1".
        """
        factory = ModelFactory(dict, name=Sequence("Alert {}"))

        self.assertEqual("Alert 1", factory._get_kwargs({})["name"])
        self.assertEqual("Alert 2", factory._get_kwargs({})["name"])
