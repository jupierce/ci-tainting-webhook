#!/bin/sh

sudo docker build -t quay.io/jupierce/ci-tainting-webhook:latest .
sudo docker push quay.io/jupierce/ci-tainting-webhook:latest