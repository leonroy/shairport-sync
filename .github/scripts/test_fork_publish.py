import unittest
import subprocess
from unittest.mock import call, patch

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

    def test_failed_publishing_retry_reuses_successful_image_outputs(self):
        manifest = self.manifest()
        sha = 'b' * 40
        refs = {arch: f'{publish.IMAGE}@sha256:{digit * 64}'
                for arch, digit in (('amd64', 'c'), ('arm64', 'd'))}
        images = {f'{publish.IMAGE}:sha-{sha}': manifest,
                  f'{publish.IMAGE}:development': manifest,
                  f'{publish.IMAGE}:latest': manifest}
        for entry in manifest['manifests']:
            arch = entry['platform']['architecture']
            image = {'digest': entry['digest'], 'manifests': [entry]}
            images[refs[arch]] = image
            images[f'{publish.IMAGE}:build-100-1-{arch}'] = image
        env = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'leonroy/shairport-sync',
               'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/development',
               'GITHUB_SHA': sha, 'GITHUB_RUN_ID': '100', 'GITHUB_RUN_ATTEMPT': '1',
               'AMD64_IMAGE': refs['amd64'], 'ARM64_IMAGE': refs['arm64']}
        with patch.dict(publish.os.environ, env, clear=True), \
                patch.object(publish, 'inspect', side_effect=images.get) as inspect, \
                patch.object(publish, 'run', side_effect=[
                    subprocess.CalledProcessError(1, ['git', 'ls-remote']),
                    f'{sha}\trefs/heads/development\n', '', '']) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                publish.publish()
            inspect.reset_mock()
            run.reset_mock()
            publish.os.environ['GITHUB_RUN_ATTEMPT'] = '2'
            publish.publish()
            self.assertEqual(inspect.call_args_list[:2],
                             [call(refs['amd64']), call(refs['arm64'])])
            for tag in ('development', 'latest'):
                run.assert_any_call('docker', 'buildx', 'imagetools', 'create',
                                    '--tag', f'{publish.IMAGE}:{tag}',
                                    f"{publish.IMAGE}@{manifest['digest']}")

    def test_publishing_requires_tested_digest_outputs(self):
        env = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'leonroy/shairport-sync',
               'GITHUB_EVENT_NAME': 'push', 'GITHUB_SHA': 'b' * 40,
               'GITHUB_RUN_ID': '100', 'GITHUB_RUN_ATTEMPT': '2',
               'ARM64_IMAGE': f"{publish.IMAGE}@sha256:{'d' * 64}"}
        for ref in ('', f'{publish.IMAGE}:build-100-1-amd64',
                    'ghcr.io/other/receiver@sha256:' + 'c' * 64,
                    f'{publish.IMAGE}@sha256:invalid'):
            with self.subTest(ref=ref), \
                    patch.dict(publish.os.environ, dict(env, AMD64_IMAGE=ref), clear=True), \
                    patch.object(publish, 'inspect') as inspect, \
                    self.assertRaises(ValueError):
                publish.publish()
            inspect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
