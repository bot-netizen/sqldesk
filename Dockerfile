# The frontend is JavaScript: the same files whichever platform the image is
# for, so it is built on the machine's own platform and never under emulation.
# Built for arm64 on an amd64 machine it took 30 minutes instead of 4.
FROM --platform=$BUILDPLATFORM node:24-bookworm AS frontend-builder

RUN npm install --global pnpm@10.30.3

# Controls whether to build the frontend assets
ARG skip_frontend_build

ENV CYPRESS_INSTALL_BINARY=0
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=1

RUN useradd -m -d /frontend sqldesk
USER sqldesk

WORKDIR /frontend
COPY --chown=sqldesk package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc /frontend/
COPY --chown=sqldesk viz-lib /frontend/viz-lib
COPY --chown=sqldesk scripts /frontend/scripts

# Controls whether to instrument code for coverage information
ARG code_coverage
ENV BABEL_ENV=${code_coverage:+test}

# Use BuildKit cache mount for pnpm store to speed rebuilds
RUN --mount=type=cache,id=pnpm-store,target=/frontend/.cache/pnpm,uid=1001,gid=1001 \
  pnpm config set store-dir /frontend/.cache/pnpm && \
  if [ "x$skip_frontend_build" = "x" ] ; then pnpm install --frozen-lockfile; fi

COPY --chown=sqldesk client /frontend/client
COPY --chown=sqldesk webpack.config.js /frontend/

# Use the same cache mount for the build step
RUN --mount=type=cache,id=pnpm-store,target=/frontend/.cache/pnpm,uid=1001,gid=1001 <<EOF
  if [ "x$skip_frontend_build" = "x" ]; then
    pnpm run build
  else
    mkdir -p /frontend/client/dist
    touch /frontend/client/dist/multi_org.html
    touch /frontend/client/dist/index.html
  fi
EOF

# The Python dependencies are built here and copied into the runtime image
# below, so that nothing needed to *build* them ships to production.
#
# A compiler is needed because several data source drivers have no wheel for
# every platform -- mysqlclient, python-ldap, pymssql, sasl -- and are built
# from source during `uv sync`. Shipping that toolchain afterwards cost about
# 300 MB: gcc alone is 102 MB, the development headers another chunk, and
# `lto-dump`, `ld.gold`, perl and git sit in /usr/bin being 40 MB of nothing
# anybody runs. None of it can be removed in a later layer -- a layer only
# ever adds -- so the split has to be a separate stage.
FROM python:3.13-slim-bookworm AS python-builder

RUN apt-get update && \
  apt-get install -y --no-install-recommends \
  pkg-config \
  build-essential \
  libffi-dev \
  git-core \
  # Kerberos, needed for MS SQL Python driver to compile on arm64
  libkrb5-dev \
  # Postgres client
  libpq-dev \
  # ODBC support:
  g++ unixodbc-dev \
  # Additional packages required for data sources:
  libssl-dev \
  default-libmysqlclient-dev \
  freetds-dev \
  libsasl2-dev && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv (pinned) from the official distroless image for a reproducible
# build. It stays in this stage: 50 MB of build tool that the runtime image
# used to carry for nothing.
COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /usr/local/bin/uv

# Install into the system environment rather than a project-local virtualenv,
# so console scripts (gunicorn, supervisord, rq, ...) are on PATH -- and so
# that /usr/local copies across to the runtime stage whole.
ENV UV_PROJECT_ENVIRONMENT=/usr/local
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./

ARG TARGETPLATFORM
ARG UV_OPTIONS="--frozen --no-install-project --no-default-groups"
# for LDAP authentication, install with the `ldap3` group
# disabled by default due to GPL license conflict
ARG install_groups="main,all_ds,dev"
# Translate the comma-separated install_groups list into uv flags. "main"
# refers to the project's base dependencies (always installed); every other
# entry maps to a uv dependency group.
#
# One uv cache per platform. The amd64 and arm64 images build side by side, and
# with one shared cache one build waited on the other's lock on gssapi -- a
# source build, slow under emulation -- for longer than uv waits (300 s), and
# failed. Wheels built for one platform are no use to the other anyway.
RUN --mount=type=cache,target=/root/.cache/uv,id=uv-${TARGETPLATFORM} <<EOF
  group_flags=""
  for group in $(echo "$install_groups" | tr ',' ' '); do
    if [ "$group" != "main" ]; then
      group_flags="$group_flags --group $group"
    fi
  done
  uv sync $UV_OPTIONS $group_flags
  # uv itself, last: the runtime stage copies this whole directory, so a
  # build tool left in it ships to production -- which is how 50 MB of uv
  # ended up in every image. `COPY --from` reads the stage's final state, so
  # deleting it here means it is never in a runtime layer at all.
  #
  # pip goes with it. The runtime base image has its own, in a layer nothing
  # can remove, and there is no reason to ship a second.
  rm -f /usr/local/bin/uv
  rm -rf /usr/local/lib/python3.13/site-packages/pip \
         /usr/local/lib/python3.13/site-packages/pip-*.dist-info \
         /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.13
EOF


FROM python:3.13-slim-bookworm

EXPOSE 5000

RUN useradd --create-home sqldesk

# The *runtime* libraries only: the shared objects the drivers built above
# link against, with no headers, no compiler and no source control.
#
# `curl` and `pwgen` are gone with them. Nothing in the image calls either:
# the health checks are pg_isready, redis-cli and an HTTP GET the kubelet
# makes, and `make env` runs pwgen on the developer's own machine.
RUN apt-get update && \
  apt-get install -y --no-install-recommends \
  ca-certificates \
  # Postgres
  libpq5 \
  # MySQL and MariaDB
  libmariadb3 \
  # SQL Server and Sybase, through FreeTDS
  libsybdb5 \
  # Kerberos, for the SASL mechanisms the Hive and Impala runners use
  libkrb5-3 libgssapi-krb5-2 libsasl2-2 libsasl2-modules-gssapi-mit \
  # ODBC drivers are loaded by this
  unixodbc \
  # SAML
  xmlsec1 \
  libffi8 && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*


ARG TARGETPLATFORM
ARG databricks_odbc_driver_url=https://databricks-bi-artifacts.s3.us-east-2.amazonaws.com/simbaspark-drivers/odbc/2.6.26/SimbaSparkODBC-2.6.26.1045-Debian-64bit.zip
# curl, gnupg and unzip are installed and removed inside this one layer: they
# exist to fetch two drivers and would otherwise ship for ever.
RUN <<EOF
  if [ "$TARGETPLATFORM" = "linux/amd64" ]; then
    apt-get update
    apt-get install -y --no-install-recommends curl gnupg unzip
    curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg
    curl https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list
    apt-get update
    ACCEPT_EULA=Y apt-get install  -y --no-install-recommends msodbcsql18
    curl "$databricks_odbc_driver_url" --location --output /tmp/simba_odbc.zip
    chmod 600 /tmp/simba_odbc.zip
    unzip /tmp/simba_odbc.zip -d /tmp/simba
    dpkg -i /tmp/simba/*.deb
    printf "[Simba]\nDriver = /opt/simba/spark/lib/64/libsparkodbc_sb64.so" >> /etc/odbcinst.ini
    rm /tmp/simba_odbc.zip
    rm -rf /tmp/simba
    apt-get purge -y curl gnupg unzip
    apt-get autoremove -y
    apt-get clean
    rm -rf /var/lib/apt/lists/*
  fi
EOF

WORKDIR /app

# Everything the builder installed: site-packages and the console scripts.
COPY --from=python-builder /usr/local /usr/local

COPY --chown=sqldesk . /app
# Belt and braces over .dockerignore, which excludes these too. A stale .pyc
# is loaded in preference to its own source whenever the mtime it recorded
# still matches, so one that slips in does not announce itself: the code that
# runs is not the code in the image, and nothing says so. One line here means
# the image cannot carry bytecode it did not compile itself.
RUN find /app -name '__pycache__' -type d -prune -exec rm -rf {} + && find /app -name '*.py[co]' -delete
COPY --from=frontend-builder --chown=sqldesk /frontend/client/dist /app/client/dist
RUN chown sqldesk /app

# Created here, owned by the user the container runs as, because
# compose.prod.yaml mounts a named volume over it. Docker seeds a volume's
# ownership from the directory already in the image; with no such directory it
# creates the mount point owned by root, and this container is not root -- so
# saving an upload fails with EACCES. The directory has to exist in the image
# even though nothing in the image puts anything in it.
RUN mkdir -p /app/uploads && chown sqldesk:sqldesk /app/uploads

USER sqldesk

ENTRYPOINT ["/app/bin/docker-entrypoint"]
CMD ["server"]
