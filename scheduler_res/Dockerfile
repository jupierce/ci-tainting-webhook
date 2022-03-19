FROM golang:1.5-alpine
ADD ./bin/kube-scheduler /bin/kube-scheduler
ADD ./scheduler-config.yaml /home/scheduler-config.yaml
RUN ["chmod", "+x", "/bin/kube-scheduler"]
CMD ["/bin/kube-scheduler"]
