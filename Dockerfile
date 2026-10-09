# Standard library only, so the image is the interpreter and one file.
FROM python:3.12-alpine@sha256:1b668429b3511ab407d8e00648891631b0b1a4d7e15e3ca70f38ab5b91ad4ab4 AS runtime
WORKDIR /srv
COPY app.py .
USER 65532:65532
ARG APP_VERSION=development
ENV PORT=8080 PYTHONUNBUFFERED=1 APP_VERSION=$APP_VERSION
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).status == 200 else 1)"
CMD ["python3", "app.py"]

FROM runtime AS test
USER root
COPY tests ./tests
USER 65532:65532
CMD ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"]

FROM runtime AS release
