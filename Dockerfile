# Standard library only, so the image is the interpreter and one file.
FROM python:3.12-slim AS base
RUN useradd --uid 65532 --no-create-home app
WORKDIR /srv
COPY app.py .
USER 65532
ENV PORT=8080 PYTHONUNBUFFERED=1
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).status == 200 else 1)"
CMD ["python3", "app.py"]
