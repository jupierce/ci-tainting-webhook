#!/bin/bash

nodes=$(oc get machines -n openshift-machine-api --no-headers -o=wide | grep ci- | awk '{print $7}')
for node in $nodes ; do
  oc get pods --all-namespaces -o wide --field-selector spec.nodeName=$node --no-headers | grep "ci-op"
done

echo "Unschedulable pods:"
oc get pods --all-namespaces -o=wide --field-selector=status.phase==Pending
