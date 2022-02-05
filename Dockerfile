FROM registry.access.redhat.com/ubi7
RUN yum install -y rh-python36 rh-python36-python-pip python3-flask python3-jsonpatch

COPY ./requirements.txt /app/requirements.txt
WORKDIR /app
RUN /bin/bash -c "source scl_source enable rh-python36; pip install -r requirements.txt"
COPY *.py /app

ENTRYPOINT ["/bin/bash"]
CMD ["-c", "source scl_source enable rh-python36; python3 -V; python3 webhook.py"]