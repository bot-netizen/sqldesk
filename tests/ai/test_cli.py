import os
import tempfile

from tests import BaseTestCase


class TestExportWritability(BaseTestCase):
    """
    The usual failure is a bind mount owned by the host's user while the
    container runs as `sqldesk`. Invisible on Docker Desktop, immediate on
    Linux, and a traceback either way unless it is checked.
    """

    def test_an_unwritable_directory_is_said_plainly(self):
        from sqldesk.cli.ai import _must_be_writable

        directory = tempfile.mkdtemp()
        os.chmod(directory, 0o500)
        self.addCleanup(os.chmod, directory, 0o700)

        with self.assertRaises(SystemExit) as raised:
            _must_be_writable(directory)

        self.assertIn("not writable", str(raised.exception))
        self.assertIn("chown", str(raised.exception))

    def test_a_writable_one_passes_quietly(self):
        from sqldesk.cli.ai import _must_be_writable

        _must_be_writable(tempfile.mkdtemp())

    def test_it_creates_the_directory_if_it_is_missing(self):
        from sqldesk.cli.ai import _must_be_writable

        directory = os.path.join(tempfile.mkdtemp(), "semantic")
        _must_be_writable(directory)

        self.assertTrue(os.path.isdir(directory))
