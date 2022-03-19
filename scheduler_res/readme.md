# Make the cluster scheduler more aggressive
```shell
$ oc explain clusterautoscaler.spec.scaleDown
```
Set `unneededTime: 1m` in `$ oc edit clusterautoscaler --as system:admin` under 

# Reference: 
- https://medium.com/paypal-tech/real-load-aware-scheduling-in-kubernetes-with-trimaran-a8efe14d51e2
- https://github.com/paypal/load-watcher

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