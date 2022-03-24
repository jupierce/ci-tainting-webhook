# Make the cluster scheduler more aggressive
```shell
$ oc explain clusterautoscaler.spec.scaleDown
```
Set `unneededTime: 1m` in `$ oc edit clusterautoscaler --as system:admin` under 

# Reference: 
- https://cloud.redhat.com/blog/improving-the-resource-efficiency-for-openshift-clusters-via-trimaran-schedulers
- https://kubernetes.io/docs/reference/scheduling/config/
- https://medium.com/@juliorenner123/k8s-creating-a-kube-scheduler-plugin-8a826c486a1
- https://medium.com/paypal-tech/real-load-aware-scheduling-in-kubernetes-with-trimaran-a8efe14d51e2
- https://github.com/paypal/load-watcher

# For hp6a reserved memory for the kubelet
https://access.redhat.com/solutions/5688941

# Build load-watcher
```shell
$ git clone https://github.com/paypal/load-watcher.git
$ cd load-wacher
$ sudo docker build -t quay.io/openshift-cr/load-watcher:latest .
$ sudo docker push quay.io/openshift-cr/load-watcher:latest
```

# Build trimaran scheduler
```shell
$ git clone https://github.com/kubernetes-sigs/scheduler-plugins.git
$ git checkout release-1.22
$ export GOPATH=/home/jupierce/go
$ make
$ cp # Dockerfile and scheduler-config.yaml from this directory.
$ sudo docker login -u '...@redhat.com' quay.io
$ sudo docker build -t quay.io/openshift-cr/trimaran:v1.22 .
$ sudo docker push quay.io/openshift-cr/trimaran:v1.22
```

# Findings
The prometheus metrics plugin did not work successfully. It found memory utilization,
but not CPU. Disabling prometheus made the plugin default to normal kubernetes metrics.

After enabling the scheduler, I found that two nodes with nearly equal utilization
could toggle back and forth in the scoring, and basically stay equal. This is fine
with high utilization, but when both had low utilization, it kept a node alive 
unnecessarily. For this, I scaled down one of the machinesets manually. Once a node
is heavily utilized, new nodes coming online should score much lower. 

That said, it is probably worth considering update the NormalizeScore method in the
trimaran scheduler to favor a node by name if there are only slight differences 
between all nodes.