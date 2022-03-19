Found hpc6a.48xlarge which is $2.88/h. It has 96 vCPU and 384G member and 100GB network.

Comparing this to a m5.4xlarge with 16 vCPU and 64G at 0.768/h.
    96 cpus / 16 cpus = 6   (i.e. 6 m5.4xlarges per hpc6a.48xlarge). 6 * 0.768/h = $4.608/h   (much more expensive than hcp6a)

c6.24xlarge is our only option in us-east-1. It is $3.672 / h. This is about 20% less.

hpc6a is not yet available in us-east-1. So trying c6a.24xlarge which is $3.672 / h.
Introduced this into build01, Mar 17 6:30pm eastern. There are presently 24 m5.4xlarges.

gp2 storage was used. 1500 G to provide sufficient iops for builds.
    1500 * 3 IOPs/GB = 4500 IOPS
    (3 IOPs/GB from https://aws.amazon.com/ebs/volume-types/)

For io2:
    $0.125/GB-month
    $0.065/provisioned IOPS-month up to 32,000 IOPS
    $0.046/provisioned IOPS-month from 32,001 to 64,000 IOPS

So, to handle the IOPS of 6 m5s per hpc6a, we need 6 * 4500 = 27000 IOPS. 
    27000 * 0.065 = $1755 / month.
The safe amount of space for hpc6a based on m5 provisioning would be 6*1500GB =  9000GB (9TB) = $1125 per month
9TB seems excessive, so let's go for 2TB = $250 per month

io1 has IOPS based on size, and storage/iops cost the same, so io2 is more flexible.  Has 50 IOPS per GB. 
Until https://bugzilla.redhat.com/show_bug.cgi?id=2065483 is fixed, using io1 for big systems. To get 27000 iops,
27000 / 50 = 540 . 

Considered gp3, but it maxes out at 16,000 IOPS. This might actually be fine because IOPS on actual drives seems to be 
peaking at about 14K/s at present. Review https://us-east-1.console.aws.amazon.com/ec2/v2/home?region=us-east-1#VolumeDetails:volumeId=vol-04bc48727b536b911 in the morning.

# Test workloads

For test ci workloads, I found that IOPS on c6a.48xlarges were hitting the upper bound of 3000 IOPS (burst speed
allowed by AWS for gp2 drives under 1TB). Changing this is io1 / 300G / 6000 iops.  


Forcing nodes to free up and move to c6a instances. First, edit all relevant m5.4xlarge machinesets
and set `ci-workload: none`.
```shell
$ for node in $(oc get machine -l machine.openshift.io/cluster-api-machine-role=worker,machine.openshift.io/instance-type=m5.4xlarge -o=name); do oc patch $node --type=json -p='[{"op": "replace", "path": "/spec/metadata/labels/ci-workload", "value":"none"}]' --as system:admin; done

$ for node in $(oc get nodes -l beta.kubernetes.io/instance-type=m5.4xlarge,ci-workload=builds -o=name); do oc label $node ci-workload=none --as system:admin --overwrite ; done
$ for node in $(oc get nodes -l beta.kubernetes.io/instance-type=m5.4xlarge,ci-workload=tests -o=name); do oc label $node ci-workload=none --as system:admin --overwrite ; done
```