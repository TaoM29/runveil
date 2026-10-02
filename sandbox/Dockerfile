FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3
COPY runner.py /opt/runner.py
COPY fixtures /opt/fixtures
USER 65532:65532
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/python3", "-I", "-B", "/opt/runner.py"]
