"""Publish tested fork images and promote only the current development commit."""
import json
import os
from pathlib import Path
import re
import subprocess

IMAGE = 'ghcr.io/leonroy/shairport-sync'
SOURCE = 'https://github.com/leonroy/shairport-sync'
PLATFORMS = {'linux/amd64', 'linux/arm64'}
REVISION = 'org.opencontainers.image.revision'
DIGEST = re.compile(r'sha256:[0-9a-f]{64}\Z')


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=120).stdout


def inspect(ref):
    result = subprocess.run(['docker', 'buildx', 'imagetools', 'inspect', ref,
                             '--format', '{{.Manifest.Digest}}'],
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        if re.search(rf'(?m)^(?:ERROR: )?{re.escape(ref)}: (?:not found|manifest unknown)\s*$', result.stderr):
            return None
        result.check_returncode()
    digest = result.stdout.strip()
    if not DIGEST.fullmatch(digest):
        raise ValueError('Registry returned an invalid image digest')
    manifest = json.loads(run('docker', 'buildx', 'imagetools', 'inspect',
                              f'{IMAGE}@{digest}', '--raw'))
    if 'manifests' not in manifest:
        config = json.loads(run('docker', 'buildx', 'imagetools', 'inspect',
                                f'{IMAGE}@{digest}', '--format', '{{json .Image}}'))
        manifest['manifests'] = [{'digest': digest, 'platform': {
            'os': config['os'], 'architecture': config['architecture']}}]
    manifest['digest'] = digest
    return manifest


def platforms(manifest):
    entries = manifest.get('manifests', [])
    if not entries:
        raise ValueError('Expected an image index')
    result = {}
    for entry in entries:
        info = entry.get('platform', {})
        platform = f"{info.get('os')}/{info.get('architecture')}"
        if platform == 'unknown/unknown':
            continue
        digest = entry.get('digest', '')
        if platform not in PLATFORMS or platform in result or not DIGEST.fullmatch(digest):
            raise ValueError('Unexpected, duplicate, or invalid image platform')
        result[platform] = digest
    return result


def validate(manifest, sha, expected):
    if manifest.get('annotations', {}).get(REVISION) != sha:
        raise ValueError('Existing commit image has a different source revision')
    if platforms(manifest) != expected or set(expected) != PLATFORMS:
        raise ValueError('Existing commit image differs; refusing to overwrite it')
    return manifest['digest']


def can_promote(event, ref, sha, development_head):
    return event == 'push' and ref == 'refs/heads/development' and sha == development_head


def publish():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REPOSITORY') != 'leonroy/shairport-sync':
        raise RuntimeError('Publishing is only enabled in this fork\'s GitHub Actions')
    if os.environ.get('GITHUB_EVENT_NAME') != 'push':
        raise RuntimeError('Pull requests cannot publish images')
    sha = os.environ['GITHUB_SHA']
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('A full source commit is required')
    build = f"build-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
    refs = [f'{IMAGE}:{build}-{arch}' for arch in ('amd64', 'arm64')]
    expected = {}
    for arch, ref in zip(('amd64', 'arm64'), refs):
        manifest = inspect(ref)
        if manifest is None:
            raise RuntimeError(f'Missing tested image: {ref}')
        children = platforms(manifest)
        if set(children) != {f'linux/{arch}'}:
            raise ValueError(f'Unexpected architecture image: {ref}')
        expected.update(children)
    candidate = f'{IMAGE}:sha-{sha}'
    manifest = inspect(candidate)
    if manifest is None:
        run('docker', 'buildx', 'imagetools', 'create', '--tag', candidate,
            '--annotation', f'index:{REVISION}={sha}',
            '--annotation', f'index:org.opencontainers.image.source={SOURCE}', *refs)
        manifest = inspect(candidate)
    if manifest is None:
        raise RuntimeError('Commit image is missing after publishing')
    digest = validate(manifest, sha, expected)
    head = run('git', 'ls-remote', SOURCE + '.git', 'refs/heads/development').split()
    development_head = head[0] if head else ''
    if can_promote(os.environ['GITHUB_EVENT_NAME'], os.environ['GITHUB_REF'], sha, development_head):
        for tag in ('development', 'latest'):
            run('docker', 'buildx', 'imagetools', 'create', '--tag', f'{IMAGE}:{tag}', f'{IMAGE}@{digest}')
            promoted = inspect(f'{IMAGE}:{tag}')
            if promoted is None or promoted['digest'] != digest:
                raise ValueError(f'{tag} promotion changed the tested manifest digest')
        print(f'Promoted current development image to latest: {IMAGE}@{digest}', flush=True)
    else:
        print('Published commit image; latest only follows the current development branch', flush=True)
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with Path(summary).open('a') as output:
            output.write(f'\n### Receiver image\n\n- `{candidate}`\n- `{IMAGE}@{digest}`\n- Platforms: linux/amd64, linux/arm64\n')


if __name__ == '__main__':
    publish()
