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


class TestWhatRunsTheHousekeeping(unittest.TestCase):
    """
    Scheduling, alerts, mail and the cleanups sat on the same worker as
    queries. A query can hold a worker for minutes, so two slow ones meant
    nothing was deciding what to refresh, nothing was evaluating alerts and
    nothing was sending mail -- while every probe still passed.
    """

    def setUp(self):
        self.worker = template("worker.yaml")
        self.values = open("charts/sqldesk/values.yaml").read()

    def test_the_query_worker_takes_only_query_queues(self):
        queues = re.search(r'^  queues: "([^"]+)"', self.values, re.M).group(1)

        self.assertEqual("queries,scheduled_queries,schemas", queues)

    def test_there_is_a_deployment_for_the_rest(self):
        self.assertIn("component: periodic-worker", self.worker)
        self.assertIn(".Values.periodicWorker.queues", self.worker)

    def test_and_its_queues_are_not_stranded_when_it_is_switched_off(self):
        # No scheduling, no alerts and no mail is a worse failure than a slow
        # query, because nothing reports it.
        self.assertIn("{{- if not .Values.periodicWorker.enabled }}", self.worker)

    def test_it_is_on_by_default(self):
        self.assertRegex(self.values, r"periodicWorker:\n  enabled: true")

    def test_it_is_not_given_a_five_minute_grace_period(self):
        # The query worker needs one: somebody's four-minute query. A job
        # here is seconds.
        periodic = self.worker.split("component: periodic-worker", 1)[1]
        self.assertIn("terminationGracePeriodSeconds: 60", periodic)


class TestWhatAClusterMayTakeAway(unittest.TestCase):
    """
    A node drain or a cluster upgrade is allowed to evict every pod of a
    deployment at once -- nothing is unhealthy, so nothing stops it -- and the
    install is then simply down until the replacements start.
    """

    def test_there_is_a_budget_for_the_web_pods(self):
        pdb = template("pdb.yaml")

        self.assertIn("kind: PodDisruptionBudget", pdb)
        self.assertIn("minAvailable: 1", pdb)

    def test_but_only_above_one_replica(self):
        # Insisting on keeping one of one blocks the drain outright, which
        # turns a routine node upgrade into something somebody has to
        # override by hand.
        self.assertIn("{{- if gt (int .Values.server.replicas) 1 }}", template("pdb.yaml"))


class TestTheBundledRedis(unittest.TestCase):
    """
    Redis holds the queues. Two things about it decide whether a query
    somebody submitted actually runs.
    """

    def setUp(self):
        self.redis = template("redis.yaml")
        self.values = open("charts/sqldesk/values.yaml").read()

    def test_it_is_replaced_rather_than_rolled(self):
        # Rolling runs two Redises behind one Service, so workers divide
        # between two sets of queues and jobs enqueued through one are
        # invisible to the workers reading the other.
        self.assertIn("type: Recreate", self.redis)

    def test_it_has_a_memory_ceiling(self):
        self.assertIn("--maxmemory", self.redis)
        self.assertRegex(self.values, r'maxmemory: "\d+[a-z]+"')

    def test_and_refuses_writes_rather_than_evicting_queued_work(self):
        # allkeys-lru would quietly evict queue entries and job records: the
        # query never runs and nothing says so. Refusing is the honest
        # failure -- the enqueue reports it.
        self.assertIn('- "noeviction"', self.redis)
        self.assertNotIn('- "allkeys-lru"', self.redis)

    def test_it_asks_for_resources(self):
        self.assertIn(".Values.redis.resources", self.redis)


class TestTheScheduler(unittest.TestCase):
    def test_its_replicas_can_be_raised(self):
        # rq-scheduler enqueues only while holding a Redis lock, so a second
        # pod is a warm spare rather than a second copy of every due job.
        self.assertIn("replicas: {{ .Values.scheduler.replicas }}", template("worker.yaml"))
