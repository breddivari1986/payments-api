"""Trusted private-runner adapter. Install on the protected delivery ref, not application source.

No model text becomes a command. Arguments are bounded, the target must exactly match the
runner's configured target, and kubectl always uses an explicit context and namespace.
"""
import json
import os
import re
import subprocess
import urllib.request


def ensure_namespace(target, recovery, command):
    """Create only the exact approved namespace; never alter or delete an existing one."""
    policy = target.get('namespacePolicy', 'require-existing')
    if policy not in {'require-existing', 'create-if-missing'}:
        raise ValueError('Unsupported namespace policy')
    prefix = ['kubectl', '--context', target['context']]
    read = prefix + ['get', 'namespace', target['namespace'], '--ignore-not-found', '-o', 'json']
    value = command(read).strip()  # Forbidden, timeouts and unknown reads fail before creation.
    created = False
    if not value:
        if recovery or policy != 'create-if-missing':
            raise ValueError('Target namespace is absent; namespace creation is not approved')
        try:
            command(prefix + ['create', 'namespace', target['namespace'], '-o', 'json'])
            created = True
        except subprocess.CalledProcessError as exc:
            # Only a definite create race can be reconciled; other failures stay failures.
            if '(AlreadyExists)' not in (exc.stderr or ''):
                raise
        value = command(read).strip()
    observed = json.loads(value or '{}')
    metadata = observed.get('metadata', {})
    if (observed.get('kind') != 'Namespace' or metadata.get('name') != target['namespace']
            or not metadata.get('uid') or metadata.get('deletionTimestamp')
            or observed.get('status', {}).get('phase') != 'Active'):
        raise ValueError('Target namespace is not verifiably active')
    return {'namespace': target['namespace'], 'uid': metadata['uid'],
            'status': 'created' if created else 'existing', 'phase': 'Active'}


def execute(release, request_key, allowed_target, allowed_image, health_url, command, probe):
    plan, artifact = release['plan'], release['artifact']
    target = plan['target']
    if target != allowed_target or artifact['location'] != allowed_image:
        raise ValueError('Release is outside the private runner target')
    if not re.fullmatch(r'delivery-[a-f0-9]{32}:(deploy|rollback)', request_key):
        raise ValueError('Invalid request identity')
    if not re.fullmatch(r'[a-f0-9]{64}', release['binding']):
        raise ValueError('Missing release binding')
    if plan['verification'].get('healthUrl') != health_url or not health_url.startswith('https://'):
        raise ValueError('Approved health criterion differs from the runner configuration')
    recovery = request_key.endswith(':rollback')
    digest = plan['recovery'].get('previousDigest', '') if recovery else artifact['digest']
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
        raise ValueError('Immutable image digest is required')
    for field in ('namespace', 'deployment', 'container'):
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,62}', target[field]):
            raise ValueError('Invalid Kubernetes target')
    if not re.fullmatch(r'[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?', target['namespace']):
        raise ValueError('Invalid namespace name')
    namespace = ensure_namespace(target, recovery, command)
    prefix = ['kubectl', '--context', target['context'], '--namespace', target['namespace']]
    image = allowed_image + '@' + digest
    current = json.loads(command(prefix + ['get', 'deployment', target['deployment'], '-o', 'json']))
    previous = next(c['image'] for c in current['spec']['template']['spec']['containers'] if c['name'] == target['container'])
    if not recovery and plan['recovery'].get('automatic') and previous not in {allowed_image + '@' + plan['recovery']['previousDigest'], image}:
        raise ValueError('Observed previous image differs from the approved recovery target')
    # Setting an exact image is idempotent. A reconciled duplicate already at that image does not write.
    if previous != image:
        command(prefix + ['set', 'image', 'deployment/' + target['deployment'], target['container'] + '=' + image])
    command(prefix + ['rollout', 'status', 'deployment/' + target['deployment'], '--timeout=300s'])
    observed = json.loads(command(prefix + ['get', 'deployment', target['deployment'], '-o', 'json']))
    desired = int(observed['spec'].get('replicas', 1))
    status = observed.get('status', {})
    exact = next(c['image'] for c in observed['spec']['template']['spec']['containers'] if c['name'] == target['container']) == image
    healthy = (desired > 0 and status.get('observedGeneration', 0) >= observed['metadata']['generation']
               and status.get('readyReplicas', 0) == desired and status.get('updatedReplicas', 0) == desired)
    http_status = probe(health_url)
    if not exact or not healthy or http_status != 200:
        raise ValueError('Exact image, rollout readiness and health endpoint did not all pass')
    return {'binding': release['binding'], 'target': target, 'artifactDigest': digest, 'verified': True,
            'checks': [{'passed': True, 'observation': namespace},
                       {'passed': True, 'observation': {'image': image, 'readyReplicas': desired, 'generation': observed['metadata']['generation']}},
                       {'passed': True, 'observation': {'url': health_url, 'status': http_status}}]}


def main():
    def command(args):
        return subprocess.run(args, check=True, capture_output=True, text=True, timeout=330).stdout
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    def probe(url):
        with urllib.request.build_opener(NoRedirect()).open(url, timeout=20) as response:
            return response.status
    key = os.environ['ORBITWARD_REQUEST_KEY']
    result = execute(json.loads(os.environ['ORBITWARD_RELEASE']), key, json.loads(os.environ['ORBITWARD_ALLOWED_TARGET']),
                     os.environ['ORBITWARD_ALLOWED_IMAGE'], os.environ['ORBITWARD_HEALTH_URL'], command, probe)
    with open('verification.json', 'w') as stream:
        json.dump(result, stream)
    with open(os.environ['GITHUB_ENV'], 'a') as stream:
        stream.write('ORBITWARD_EVIDENCE_NAME=orbitward-evidence-' + key.replace(':', '-') + '\n')


if __name__ == '__main__':
    main()
