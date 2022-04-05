#!/usr/bin/env python

from flask import Flask, request, jsonify
import base64
from enum import Enum
import jsonpatch
import argparse
import sys
import pprint

CI_OPERATOR_NAMESPACE_PREFIX = 'ci-op-'
CI_LN_NAMESPACE_PREFIX = 'ci-ln-'
BUILD_LABEL_NAME = 'openshift.io/build.name'

VERSION = '0.5'

builds_scheduler = None
tests_scheduler = None
allow_cpu_overcommit = False

# Python modeled on https://medium.com/analytics-vidhya/how-to-write-validating-and-mutating-admission-controller-webhooks-in-python-for-kubernetes-1e27862cb798
admission_controller = Flask(__name__)


@admission_controller.route('/ping', methods=['GET'])
def pods_webhook_ping():
    return jsonify(
        ['ok', VERSION]
    )


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


class PodTarget(Enum):
    TESTS_WORKLOAD = 'tests'
    BUILD_WORKLOAD = 'builds'
    NONE = 'none'


@admission_controller.route('/mutate/pods', methods=['POST'])
def pods_webhook_mutate():
    request_info = request.get_json()['request']

    request_uid = request_info['uid']
    metadata = request_info["object"]["metadata"]
    namespace = request_info["namespace"]
    spec = request_info["object"]['spec']

    eprint(pprint.pformat(request_info["object"], indent=4))

    pod_target = PodTarget.NONE

    if namespace == "ci":
        labels = metadata.get('labels', {})
        if labels.get('created-by-prow', '') == 'true':
            pod_target = PodTarget.TESTS_WORKLOAD

    # OSD has so. many. operators which aren't using replicasets. Just setup prefix based matching.
    if namespace.startswith('openshift-') or namespace in ['openshift-marketplace', 'openshift-monitoring', 'rh-corp-logging', 'ocp', 'openshift-splunk-forwarder-operator', 'openshift-route-monitor-operator', 'openshift-velero', 'openshift-osd-metrics', 'openshift-cloud-ingress-operator', 'openshift-rbac-permissions', 'openshift-network-diagnostics', 'cert-manager', 'openshift-user-workload-monitoring', 'openshift-managed-upgrade-operator', 'openshift-must-gather-operator', 'openshift-addon-operator']:
        # Two categories of pods are evading packing:
        # 1. Those with local storage. We should consider setting `skipNodesWithLocalStorage: false` in the clusterautoscaler
        # 2. Those without replicasets. Some operators create pods directly and it impedes the autoscaler making the right decision. (rh-corp-logging, openshift-marketplace)
        # To help the scaler for the time being, mark them with an annotation saying they are safe to evict.
        # To achieve this without killing a bunch of pods in a given namespace:
        #    $ oc --as system:admin annotate pods --all cluster-autoscaler.kubernetes.io/safe-to-evict=true
        annotations = metadata.get('annotations', {})
        annotations['cluster-autoscaler.kubernetes.io/safe-to-evict'] = 'true'
        eprint(f'Pod in {namespace} has been selected for safe eviction')

        return admission_response_patch(
            request_uid,
            allowed=True,
            message="Adding safe to evict attribute",
            json_patch=jsonpatch.JsonPatch(
                [
                    # https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/
                    {"op": "add", "path": "/metadata/annotations", "value": annotations},
                ]
            )
        )

    if namespace.startswith((CI_OPERATOR_NAMESPACE_PREFIX, CI_LN_NAMESPACE_PREFIX)):
        labels = metadata.get('labels', {})

        skip_pod = False

        # Ensure that no special resources are required by this pod
        containers = spec.get('containers', []) + spec.get('initContainers', [])
        for container in containers:
            resources = container.get('resources', {})
            requests = resources.get('requests', {})
            requests.pop('cpu', None)
            requests.pop('memory', None)
            if requests:
                # Do not adjust any pod that requires special resources (i.e. something other than cpu or memory)
                skip_pod = True
                break

        if skip_pod:
            # If anything is left, this pod has special resource requirements. Do not alter it.
            pass
        elif BUILD_LABEL_NAME in labels:
            pod_target = PodTarget.BUILD_WORKLOAD
        else:
            pod_target = PodTarget.TESTS_WORKLOAD

    if pod_target is not PodTarget.NONE:
        tolerations = spec.get('tolerations', [])
        node_selector = spec.get('nodeSelector', {})
        labels = metadata.get('labels', {})
        annotations = metadata.get('annotations', {})
        affinity = spec.get('affinity', {})

        # Add a label that will help pod affinity pack pods
        # onto nodes in stead of spreading them.
        labels['ci-workload'] = pod_target.value

        # Add a label that will help pod affinity pack pods
        # by namespace. There is also a namespaceSelector, we
        # could use.
        labels['ci-workload-namespace'] = namespace

        scheduler_name = None
        toleration_to_add = None
        if pod_target == PodTarget.BUILD_WORKLOAD:
            # This is a build job. Tolerate the build node taint and
            # add a node selector.
            toleration_to_add = {"key": "node-role.kubernetes.io/ci-build-worker", "operator": "Exists", "effect": "NoSchedule"}
            node_selector["ci-workload"] = "builds"
            scheduler_name = builds_scheduler
        elif pod_target == PodTarget.TESTS_WORKLOAD:
            # This is a test-like job. Tolerate the test node taint and
            # add a node selector.
            toleration_to_add = {"key": "node-role.kubernetes.io/ci-tests-worker", "operator": "Exists", "effect": "NoSchedule"}
            node_selector["ci-workload"] = "tests"
            scheduler_name = tests_scheduler

        # Check before adding in case idempotence is necessary.
        if toleration_to_add and toleration_to_add not in tolerations:
            tolerations.append(toleration_to_add)

        eprint(f'Pod in {namespace} has been selected for assignment: {node_selector}')

        patches = []

        if scheduler_name:
            patches.append(
                {"op": "add", "path": "/spec/schedulerName", "value": scheduler_name},
            )

        if allow_cpu_overcommit and pod_target == PodTarget.TESTS_WORKLOAD:
            # Make sure the test platform pod scaler doesn't undo our change.
            annotations['ci-workload-autoscaler.openshift.io/scale'] = 'true'

            # Even if we trick the scheduler, the kubelet will check the incoming
            # pod to see if requests are greater than capacity. So in order to
            # overcommit, it is necessary to reduce the request.
            pod_name = metadata.get('name', 'unknown')
            eprint(f'Reducing CPU requests in pod: {namespace}/{pod_name}')

            for container_type in ['initContainers', 'containers']:
                containers = spec.get(container_type, [])
                for idx, container in enumerate(containers):

                    resources = container.get('resources', None)
                    if resources is not None:
                        # Unclear why, but webhook does not receive obj.spec with resource requests
                        # and limits populated. Trying a dumb delete instead of trying to be smart
                        # checking whether they exist.

                        limits = resources.get('limits', None)
                        if limits is not None:
                            patches.extend([
                                {"op": "add", "path": f"/spec/{container_type}/{idx}/resources/limits/cpu", "value": "1m"},
                            ])
                            patches.extend([
                                {"op": "remove", "path": f"/spec/{container_type}/{idx}/resources/limits/cpu"},
                            ])

                        requests = resources.get('requests', None)
                        if requests is not None:
                            patches.extend([
                                {"op": "add", "path": f"/spec/{container_type}/{idx}/resources/requests/cpu", "value": "1m"},
                            ])

                        continue

        patches.extend([
            # https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/
            {"op": "add", "path": "/metadata/annotations", "value": annotations},
            {"op": "add", "path": "/metadata/labels", "value": labels},
            {"op": "add", "path": "/spec/tolerations", "value": tolerations},
            {"op": "add", "path": "/spec/nodeSelector", "value": node_selector},
            {"op": "add", "path": "/spec/affinity", "value": affinity}
        ])

        return admission_response_patch(
            request_uid,
            allowed=True,
            message="Adding attributes to partition ci workloads",
            json_patch=jsonpatch.JsonPatch(
                patches
            )
        )

    # Otherwise, we don't have an interest in this pod. Just allow it.
    return admission_response_patch(request_uid, allowed=True)


def admission_response_patch(request_uid, allowed=True, message=None, json_patch=None):
    response = {
        'uid': request_uid,
        'allowed': allowed
    }
    if message:
        response['status'] = {"message": message}

    if json_patch:
        base64_patch = base64.b64encode(json_patch.to_string().encode("utf-8")).decode("utf-8")
        response['patchType'] = "JSONPatch"
        response['patch'] = base64_patch

    # Response format: https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/
    return jsonify(
        {
            "apiVersion": "admission.k8s.io/v1",
            "kind": "AdmissionReview",
            "response": response
        }
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='ci-scheduler-webhook')
    parser.add_argument('--builds-scheduler', help='Name of the pod scheduler to use for builds', required=False,
                        default=None)
    parser.add_argument('--tests-scheduler', help='Name of the pod scheduler to use for test', required=False,
                        default=None)
    parser.add_argument("--allow-cpu-overcommit", default=False, action="store_true",
                        help="Permit the scheduler to overcommit CPU requests")
    args = vars(parser.parse_args())

    builds_scheduler = args['builds_scheduler']
    tests_scheduler = args['tests_scheduler']
    allow_cpu_overcommit = args['allow_cpu_overcommit']

    print(f'Using builds scheduler: {builds_scheduler}')
    print(f'Using tests scheduler: {tests_scheduler}')
    admission_controller.run(host='0.0.0.0', port=8443, ssl_context=('/etc/pki/tls/certs/admission/tls.crt', '/etc/pki/tls/certs/admission/tls.key'))
