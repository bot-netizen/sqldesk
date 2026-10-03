import re
from pathlib import Path

from tests import BaseTestCase

ROOT = Path(__file__).resolve().parent.parent

"""
What may not get into a published image.

This exists because of one afternoon. `.dockerignore` listed `*.pyc` and
`__pycache__/`, which reads like "no bytecode" and is not: Docker matches those
patterns against the context root only, unlike .gitignore, so every nested
`sqldesk/**/__pycache__` was shipping.

That is worse than noise. The development compose file mounts the repository at
`/app`, which is also where the image puts it -- so a `.pyc` written by a local
test run records `/app/...` as its source path and matches perfectly inside the
image. Python then loads it in preference to the `.py` beside it whenever the
source mtime it recorded still matches, which is the normal case. The code that
runs is not the code in the image, and nothing anywhere says so.

On 2026-10-03 that shipped a *mutant*: a mutation-testing run had briefly
changed `Dashboard.is_streaming` to `self.kind != "streaming"`, the run compiled
it, the source was restored seconds later, and the built image carried source
saying `==` with bytecode saying `!=`. Every streaming dashboard reported itself
as ordinary. Eleven modules in that image disagreed with their own source.
"""


class TestNoBytecodeInTheImage(BaseTestCase):
    def dockerignore(self):
        return (ROOT / ".dockerignore").read_text().splitlines()

    def test_bytecode_is_excluded_at_every_depth(self):
        lines = {line.strip() for line in self.dockerignore()}

        # `**/` and not a bare name: a bare `__pycache__/` matches the context
        # root and nothing below it.
        self.assertIn("**/__pycache__/", lines)
        self.assertIn("**/*.pyc", lines)

    def test_and_a_bare_pattern_is_not_relied_on(self):
        lines = {line.strip() for line in self.dockerignore()}

        self.assertNotIn("__pycache__/", lines)
        self.assertNotIn("*.pyc", lines)

    def test_the_build_removes_any_that_still_arrive(self):
        # Belt and braces, because getting a .dockerignore pattern subtly wrong
        # is exactly what happened: the image should be unable to carry
        # bytecode it did not compile itself.
        dockerfile = (ROOT / "Dockerfile").read_text()
        copy = dockerfile.index("COPY --chown=sqldesk . /app")
        after = dockerfile[copy:]

        self.assertTrue(
            re.search(r"find /app .*__pycache__.*rm -rf", after),
            "the Dockerfile should delete bytecode after copying the source in",
        )

    def test_agent_scratch_space_stays_out(self):
        # `.claude/` had a full git worktree in it -- a second copy of the
        # project, 17 MB, inside every published image.
        lines = {line.strip() for line in self.dockerignore()}

        self.assertIn(".claude/", lines)
        self.assertIn(".wolf/", lines)
