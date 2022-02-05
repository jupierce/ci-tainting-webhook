#!/usr/bin/env python

from flask import Flask, request, jsonify
import base64
import random
import jsonpatch
import sys

CI_OPERATOR_NAMESPACE_PREFIX = 'ci-op-'
BUILD_LABEL_NAME = 'openshift.io/build.name'

VERSION = '0.3'

# Python modeled on https://medium.com/analytics-vidhya/how-to-write-validating-and-mutating-admission-controller-webhooks-in-python-for-kubernetes-1e27862cb798
admission_controller = Flask(__name__)


@admission_controller.route('/ping', methods=['GET'])
def pods_webhook_ping():
    return jsonify(
        ['ok', VERSION]
    )


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


@admission_controller.route('/mutate/pods', methods=['POST'])
def pods_webhook_mutate():
    request_info = request.get_json()['request']

    request_uid = request_info['uid']
    metadata = request_info["object"]["metadata"]
    namespace = request_info["namespace"]
    spec = request_info["object"]['spec']

    if namespace.startswith(CI_OPERATOR_NAMESPACE_PREFIX):
        labels = metadata.get('labels', {})
        tolerations = spec.get('tolerations', [])
        node_selector = spec.get('nodeSelector', {})

        if BUILD_LABEL_NAME in labels:
            # This is a build job. Tolerate the build node taint and
            # add a node selector.
            tolerations.append(
                {"key": "node-role.kubernetes.io/ci-build-worker", "operator": "Exists", "effect": "NoSchedule"}
            )
            node_selector["ci-workload"] = "builds"
        else:
            # This is a test-like job. Tolerate the test node taint and
            # add a node selector.
            tolerations.append(
                {"key": "node-role.kubernetes.io/ci-tests-worker", "operator": "Exists", "effect": "NoSchedule"}
            )
            node_selector["ci-workload"] = "tests"

        eprint(f'Pod in {namespace} has been selected for assignment: {node_selector}')

        return admission_response_patch(
            request_uid,
            allowed=True,
            message="Adding nodeSelector for ci-workload",
            json_patch=jsonpatch.JsonPatch(
                [
                    # https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/
                    {"op": "add", "path": "/spec/tolerations", "value": tolerations},
                    {"op": "add", "path": "/spec/nodeSelector", "value": node_selector}
                ]
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
    admission_controller.run(host='0.0.0.0', port=8443, ssl_context=('/etc/pki/tls/certs/admission/tls.crt', '/etc/pki/tls/certs/admission/tls.key'))
