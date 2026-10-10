import unittest
from unittest.mock import patch

import fork_publish as publish


class PublishingRules(unittest.TestCase):
    def manifest(self):
        return {'digest': 'sha256:' + 'a' * 64,
                'annotations': {publish.REVISION: 'b' * 40},
                'manifests': [{'digest': 'sha256:' + digit * 64,
                               'platform': {'os': 'linux', 'architecture': arch}}
                              for arch, digit in (('amd64', 'c'), ('arm64', 'd'))]}

    def test_matching_commit_and_platforms(self):
        manifest = self.manifest()
        self.assertEqual(publish.validate(manifest, 'b' * 40, publish.platforms(manifest)), manifest['digest'])

    def test_different_revision_or_content_cannot_replace_commit_image(self):
        manifest = self.manifest()
        with self.assertRaises(ValueError):
            publish.validate(manifest, 'e' * 40, publish.platforms(manifest))
        with self.assertRaises(ValueError):
            publish.validate(manifest, 'b' * 40, {'linux/amd64': 'sha256:' + 'e' * 64})

    def test_duplicate_or_unexpected_platform_is_rejected(self):
        manifest = self.manifest()
        manifest['manifests'].append(manifest['manifests'][0])
        with self.assertRaises(ValueError):
            publish.platforms(manifest)
        manifest = self.manifest()
        manifest['manifests'][0]['platform']['architecture'] = '386'
        with self.assertRaises(ValueError):
            publish.platforms(manifest)

    def test_attestations_are_not_runtime_platforms(self):
        manifest = self.manifest()
        manifest['manifests'].append({'platform': {'os': 'unknown', 'architecture': 'unknown'}})
        self.assertEqual(set(publish.platforms(manifest)), publish.PLATFORMS)

    def test_latest_only_follows_current_development_push(self):
        sha = 'b' * 40
        self.assertTrue(publish.can_promote('push', 'refs/heads/development', sha, sha))
        for event, ref, head in [('pull_request', 'refs/heads/development', sha),
                                 ('push', 'refs/heads/build/telemetry-ghcr', sha),
                                 ('push', 'refs/heads/master', sha),
                                 ('push', 'refs/heads/development', 'c' * 40)]:
            self.assertFalse(publish.can_promote(event, ref, sha, head))

    def test_publishing_requires_fork_actions_push(self):
        for env in ({}, {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'mikebrady/shairport-sync'},
                    {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'leonroy/shairport-sync',
                     'GITHUB_EVENT_NAME': 'pull_request'}):
            with patch.dict(publish.os.environ, env, clear=True), self.assertRaises(RuntimeError):
                publish.publish()


if __name__ == '__main__':
    unittest.main()
