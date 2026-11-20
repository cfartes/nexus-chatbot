import argparse
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

from scripts import install_vps


class RoutingTest(unittest.TestCase):
    def test_reuses_rotafy_route(self) -> None:
        proxy = {"Name": "/gateway", "Config": {"Image": "traefik:v3", "Cmd": [
            "--entrypoints.other.address=:443", "--certificatesresolvers.other.acme.email=test@example.test",
        ]}, "NetworkSettings": {"Networks": {"shared": {"IPAddress": "172.21.0.2"}, "other": {}}}}
        rotafy = {"Name": "/rotafy", "Config": {"Image": "rotafy", "Labels": {
            "traefik.http.routers.rotafy.rule": 'Host(`rotafy.nexusdataanalytics.tech`)',
            "traefik.http.routers.rotafy.entrypoints": "websecure",
            "traefik.http.routers.rotafy.tls.certresolver": "production",
            "traefik.docker.network": "shared",
        }}, "NetworkSettings": {"Networks": {"shared": {}}}}
        args = argparse.Namespace(traefik_container=None, network=None, entrypoint=None, resolver=None)
        with patch.object(install_vps, "output", side_effect=["proxy\nrotafy", json.dumps([proxy, rotafy]), '[{"Driver":"bridge"}]']):
            routing = install_vps.detect_routing(args)
        self.assertEqual(routing, {"NEXUS_DEPLOY_PROXY_IP": "172.21.0.2", "NEXUS_DEPLOY_NETWORK": "shared",
                                  "NEXUS_DEPLOY_ENTRYPOINT": "websecure", "NEXUS_DEPLOY_RESOLVER": "production"})

    def test_ambiguous_options_are_not_guessed(self) -> None:
        with patch.object(install_vps.sys.stdin, "isatty", return_value=False):
            with self.assertRaisesRegex(ValueError, "first, second"):
                install_vps.choose("--resolver", None, {"first", "second"})

    def test_public_check_can_be_inconclusive(self) -> None:
        with (patch.object(install_vps.urllib.request, "urlopen", side_effect=URLError("DNS indisponível")),
              patch.object(install_vps.time, "sleep"), patch("builtins.print") as warn):
            self.assertFalse(install_vps.public_check())
        self.assertIn("DNS indisponível", warn.call_args.args[0])
