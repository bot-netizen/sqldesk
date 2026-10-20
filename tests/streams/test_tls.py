"""
Kafka over TLS with a certificate SQLDesk was given, proved with real handshakes.

Until 0.7.4 a Kafka data source could only use TLS when the system trust store
already trusted the broker -- so a cluster on an internal PKI, a self-signed
one, or one that wants client certificates could not be reached at all.

No broker is needed to prove it: a TLS server holding a certificate signed by
a test CA is enough, because the handshake is the part being tested. The
server records whether a handshake completed and whether a client certificate
came with it; what happens after (it speaks no Kafka) does not matter.
"""

import base64
import datetime
import socket
import ssl
import tempfile
import threading
import time
import unittest

from sqldesk.query_runner import installed
from sqldesk.streams.consumer import _pem, _security

HAVE_KAFKA = installed("confluent_kafka")
WHY_NOT = "confluent_kafka is not installed here; CI installs it"


def _certificates(server_name="localhost"):
    """A CA, a server certificate for `server_name`, and a client certificate, as PEM."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    now = datetime.datetime.now(datetime.timezone.utc)

    def key():
        return ec.generate_private_key(ec.SECP256R1())

    def pem_key(k):
        return k.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode()

    def name(common):
        return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common)])

    ca_key = key()
    ca = (
        x509.CertificateBuilder()
        .subject_name(name("SQLDesk test CA"))
        .issuer_name(name("SQLDesk test CA"))
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    def issue(common, san=None):
        k = key()
        builder = (
            x509.CertificateBuilder()
            .subject_name(name(common))
            .issuer_name(ca.subject)
            .public_key(k.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(days=1))
        )
        if san:
            builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(san)]), critical=False)
        return builder.sign(ca_key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM).decode(), pem_key(k)

    server_cert, server_key = issue(server_name, san=server_name)
    client_cert, client_key = issue("sqldesk-client")
    return {
        "ca": ca.public_bytes(serialization.Encoding.PEM).decode(),
        "server_cert": server_cert,
        "server_key": server_key,
        "client_cert": client_cert,
        "client_key": client_key,
    }


class TlsServer:
    """Accepts TLS connections and remembers what each handshake looked like."""

    def __init__(self, certs, require_client_cert=False):
        self.handshakes = []
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as chain:
            chain.write(certs["server_cert"] + certs["server_key"])
        self.context.load_cert_chain(chain.name)
        if require_client_cert:
            with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as cafile:
                cafile.write(certs["ca"])
            self.context.load_verify_locations(cafile.name)
            self.context.verify_mode = ssl.CERT_REQUIRED
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.sock.settimeout(0.5)
        self.port = self.sock.getsockname()[1]
        self.running = True
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while self.running:
            try:
                raw, _ = self.sock.accept()
            except (socket.timeout, OSError):
                continue
            try:
                wrapped = self.context.wrap_socket(raw, server_side=True)
                self.handshakes.append({"ok": True, "client_cert": bool(wrapped.getpeercert())})
                wrapped.close()
            except (ssl.SSLError, OSError) as error:
                self.handshakes.append({"ok": False, "why": str(error)})
                raw.close()

    def stop(self):
        self.running = False
        self.thread.join(timeout=2)
        self.sock.close()


def _b64(text):
    return base64.b64encode(text.encode()).decode()


@unittest.skipUnless(HAVE_KAFKA, WHY_NOT)
class TestRealHandshakes(unittest.TestCase):
    def connect(self, server, options, host="localhost"):
        """Let librdkafka try for a few seconds; the server records what it saw."""
        from confluent_kafka.admin import AdminClient

        config = {"bootstrap.servers": "{}:{}".format(host, server.port), **_security(options)}
        try:
            AdminClient(config).list_topics(timeout=3)
        except Exception:
            pass  # it speaks no Kafka; the handshake is what is being tested
        time.sleep(0.3)
        return server.handshakes

    def serve(self, certs, **kwargs):
        server = TlsServer(certs, **kwargs)
        self.addCleanup(server.stop)
        return server

    def test_a_private_ca_is_trusted_when_given(self):
        certs = _certificates()
        server = self.serve(certs)

        seen = self.connect(server, {"security_protocol": "SSL", "ssl_ca_File": _b64(certs["ca"])})

        self.assertTrue(any(h["ok"] for h in seen), seen)

    def test_and_refused_when_it_is_the_wrong_one(self):
        # Proof the CA is actually used to verify, rather than verification
        # being off: a different CA must fail the handshake.
        certs = _certificates()
        stranger = _certificates()
        server = self.serve(certs)

        seen = self.connect(server, {"security_protocol": "SSL", "ssl_ca_File": _b64(stranger["ca"])})

        self.assertTrue(seen, "librdkafka never connected")
        self.assertFalse(any(h["ok"] for h in seen), seen)

    def test_mutual_tls_presents_the_client_certificate(self):
        certs = _certificates()
        server = self.serve(certs, require_client_cert=True)

        seen = self.connect(
            server,
            {
                "security_protocol": "SSL",
                "ssl_ca_File": _b64(certs["ca"]),
                "ssl_certificate_File": _b64(certs["client_cert"]),
                "ssl_key_File": _b64(certs["client_key"]),
            },
        )

        self.assertTrue(any(h["ok"] and h["client_cert"] for h in seen), seen)

    def test_without_one_a_broker_that_wants_it_refuses(self):
        certs = _certificates()
        server = self.serve(certs, require_client_cert=True)

        seen = self.connect(server, {"security_protocol": "SSL", "ssl_ca_File": _b64(certs["ca"])})

        self.assertTrue(seen, "librdkafka never connected")
        self.assertFalse(any(h["ok"] for h in seen), seen)

    def test_a_certificate_for_another_name_is_refused_by_default(self):
        certs = _certificates(server_name="kafka.internal.example")
        server = self.serve(certs)

        seen = self.connect(server, {"security_protocol": "SSL", "ssl_ca_File": _b64(certs["ca"])})

        self.assertTrue(seen, "librdkafka never connected")
        self.assertFalse(any(h["ok"] for h in seen), seen)

    def test_unless_the_name_check_is_turned_off(self):
        # A broker reached by an address its certificate does not name. The CA
        # is still checked; only whose certificate it is, is not.
        certs = _certificates(server_name="kafka.internal.example")
        server = self.serve(certs)

        seen = self.connect(
            server,
            {"security_protocol": "SSL", "ssl_ca_File": _b64(certs["ca"]), "ssl_verify_hostname": False},
        )

        self.assertTrue(any(h["ok"] for h in seen), seen)


class TestTheSettings(unittest.TestCase):
    def test_nothing_is_added_for_a_plaintext_broker(self):
        self.assertEqual({}, _security({"brokers": "b:9092"}))

    def test_an_upload_is_decoded_to_pem(self):
        pem = "-----BEGIN CERTIFICATE-----\\nMIIB\\n-----END CERTIFICATE-----"
        self.assertEqual(pem, _security({"ssl_ca_File": _b64(pem)})["ssl.ca.pem"])

    def test_pem_text_is_taken_as_it_is(self):
        pem = "-----BEGIN CERTIFICATE-----\\nMIIB\\n-----END CERTIFICATE-----"
        self.assertEqual(pem, _pem(pem))

    def test_something_that_is_not_a_certificate_says_so(self):
        with self.assertRaises(ValueError):
            _pem("%%% not base64 and not pem %%%")

    def test_the_name_check_stays_on_unless_turned_off(self):
        self.assertNotIn("ssl.endpoint.identification.algorithm", _security({"security_protocol": "SSL"}))
        self.assertNotIn(
            "ssl.endpoint.identification.algorithm",
            _security({"security_protocol": "SSL", "ssl_verify_hostname": True}),
        )
        self.assertEqual(
            "none",
            _security({"security_protocol": "SSL", "ssl_verify_hostname": False})[
                "ssl.endpoint.identification.algorithm"
            ],
        )

    def test_the_key_and_its_password_are_secret(self):
        from sqldesk.query_runner.kafka_stream import KafkaStream

        secret = KafkaStream.configuration_schema()["secret"]
        self.assertIn("ssl_key_File", secret)
        self.assertIn("ssl_key_password", secret)
