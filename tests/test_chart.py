"""
The Helm chart, checked as text.

Read rather than rendered because helm is not in the container this suite runs
in -- a test that skips itself wherever it actually runs is not a test. `helm
lint` and `helm template` cover the rendering; these hold the few properties
that a real cluster depends on and a laptop never exercises.
"""

import re
import unittest

TEMPLATES = "charts/sqldesk/templates/{}"


def template(name):
    return open(TEMPLATES.format(name)).read()


class TestTheMigrationJob(unittest.TestCase):
    """
    Helm's `before-hook-creation` removes the previous Job of the same name
    before making the next one. 0.7.4 and earlier put the release revision in
    the name, so no two were ever the same and nothing was removed: a cluster
    upgraded eighty times had eighty Jobs and eighty pods left behind.
    """

    def metadata_name(self):
        return re.search(r"^  name: (.+)$", template("migrate-job.yaml"), re.M).group(1)

    def test_its_name_is_the_same_on_every_upgrade(self):
        name = self.metadata_name()

        self.assertNotIn("Revision", name)
        self.assertEqual('{{ include "sqldesk.fullname" . }}-migrate', name)

    def test_the_previous_one_is_removed_before_the_next(self):
        self.assertRegex(
            template("migrate-job.yaml"),
            r'"helm.sh/hook-delete-policy": [^\n]*before-hook-creation',
        )


class TestTheRestrictedPodSecurityStandard(unittest.TestCase):
    """
    A namespace enforcing "restricted" rejects a pod at admission unless it runs
    as non-root with a seccomp profile and every container drops all
    capabilities and privilege escalation. 0.7.3 was refused outright by one.

    The bundled Postgres is left out on purpose: run non-root from the start, it
    makes its data directory group-writable and then refuses to start. A real
    cluster uses a managed one.
    """

    COMPLIANT = ("server.yaml", "worker.yaml", "migrate-job.yaml", "screenshots.yaml", "redis.yaml")

    def test_every_container_drops_privileges(self):
        for name in self.COMPLIANT:
            text = template(name)
            containers = len(re.findall(r"^\s+image:", text, re.M))
            secured = text.count('include "sqldesk.containerSecurity"')
            self.assertEqual(containers, secured, name)

    def test_every_pod_runs_non_root_under_a_seccomp_profile(self):
        for name in self.COMPLIANT:
            text = template(name)
            pods = len(re.findall(r"^kind: (?:Deployment|Job)$", text, re.M))
            secured = text.count('include "sqldesk.podSecurity"') + text.count("type: RuntimeDefault")
            self.assertEqual(pods, secured, name)
            if 'include "sqldesk.podSecurity"' not in text:
                self.assertIn("runAsNonRoot: true", text, name)

    def test_the_shared_pod_settings_are_what_restricted_asks_for(self):
        helpers = template("_helpers.tpl")
        pod = helpers[helpers.index('define "sqldesk.podSecurity"') :]
        pod = pod[: pod.index("{{- end -}}")]
        container = helpers[helpers.index('define "sqldesk.containerSecurity"') :]
        container = container[: container.index("{{- end -}}")]

        self.assertIn("runAsNonRoot: true", pod)
        self.assertIn("type: RuntimeDefault", pod)
        self.assertIn("allowPrivilegeEscalation: false", container)
        self.assertIn('drop: ["ALL"]', container)
