#!/bin/bash

oc create configmap -o=yaml --dry-run=client  trimaran-scheduler-config --from-file scheduler-config.yaml | oc -n kube-system --as system:admin apply -f -
oc create configmap -o=yaml --dry-run=client  trimaran-scheduler-config-next --from-file scheduler-config-next.yaml | oc -n kube-system --as system:admin apply -f -