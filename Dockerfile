# ADR-0001's Tertiary distribution tier: a prebuilt image, one per release, at
# ghcr.io/vespassassina/edgar. Installs the PyPI release rather than copying the
# working tree, so the image is exactly what `pip install edgar-harness` gives
# anyone else.
FROM python:3.12-slim
ARG VERSION=""
RUN pip install --no-cache-dir "edgar-harness${VERSION:+==$VERSION}"
WORKDIR /work
ENTRYPOINT ["edgar"]
