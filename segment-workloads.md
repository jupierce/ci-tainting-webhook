To accomplish the creation of machinepools on OSD clusters:

You can download the `ocm` client binary from https://console.redhat.com/openshift/downloads . 

To use `ocm`, you must log in to https://console.redhat.com . Then visit: https://console.redhat.com/openshift/token
to find the `login` invocation to use to interact with your account on the command line.

Annotating non-replicated as evictable
```shell
$ for ns in $(oc get projects -o=name | grep openshift- | cut -d / -f 2); do oc -n $ns --as system:admin annotate pods --all cluster-autoscaler.kubernetes.io/safe-to-evict=true ; done     

$ for ns in openshift-console openshift-marketplace openshift-monitoring rh-corp-logging ocp openshift-splunk-forwarder-operator openshift-route-monitor-operator openshift-velero openshift-osd-metrics openshift-cloud-ingress-operator openshift-rbac-permissions openshift-network-diagnostics cert-manager openshift-user-workload-monitoring; do oc -n $ns --as system:admin annotate pods --all cluster-autoscaler.kubernetes.io/safe-to-evict=true ; done
```

Adding quota request to allow us to establish these machinepools: https://gitlab.cee.redhat.com/service/ocm-resources/-/merge_requests/2084 . 


There was an initial attempt and creating the required machinepools using the OSD API:
https://api.openshift.com/#/default/post_api_clusters_mgmt_v1_clusters__cluster_id__machine_pools (see below).
However, this API did not have the ability to change the boot volume of the nodes (required for
IOPS during OpenShift Builds). This approach was therefore abandoned in favor of establishing the
machinesets directly.
```shell
$ MACHINE_TYPE=m5.4xlarge   # For AWS
##XOR
$ MACHINE_TYPE=custom-16-65536   # For GCP

$ ./ocm login ...
# Find the cluster id for the cluster to interact with
$ ./ocm list cluster | grep build03
# Set the value into an environment variable for convenience. 
$ CID=1nq........................7o5l4
# Create build workers machine pool
$ ./ocm create machinepool -c $CID --enable-autoscaling --instance-type $MACHINE_TYPE --min-replicas 1 --max-replicas 50 --labels 'ci-workload=builds' --taints 'node-role.kubernetes.io/ci-build-worker=ci-build-worker:NoSchedule' ci-build-workers
# Create test workers machine pool
$ ./ocm create machinepool -c $CID --enable-autoscaling --instance-type $MACHINE_TYPE --min-replicas 1 --max-replicas 50 --labels 'ci-workload=tests' --taints 'node-role.kubernetes.io/ci-tests-worker=ci-tests-worker:NoSchedule' ci-tests-workers
```




Redeploying the webhook with updated code:
```shell
$ oc --as system:admin delete -n ci $(oc get pods -n ci -o=name | grep tainting)
```

Viewing logs for deployment
```shell
$ oc -n ci logs -f deploy/ci-tainting-consumer-admission
```


