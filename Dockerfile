# syntax=docker/dockerfile:1
# The above directive must be the first line to enable newer Dockerfile syntax

########################################################################

# Stage 1: Base image prep
# - Debian 13 'Trixie' slim: long life, includes Python 3.13
# - Include TLS certs from equivalent Apache 'Trixie' image to enable HTTPS initially, as Debian does not contain certs
# - When updating base image, ensure the httpd image is kept in sync as well (until HTTPS is used by default by Debian)

FROM docker.io/debian:13-slim AS base
COPY --from=docker.io/httpd:trixie /etc/ssl /etc/ssl
COPY --from=docker.io/httpd:trixie /lib/ssl /lib/ssl
ARG DEBIAN_FRONTEND=noninteractive
RUN sed -i 's|http://|https://|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

########################################################################

# Stage 2: Download LimeSurvey
# - Fetch & extract package to /opt/limesurvey
# - Keep unzip out of the final image

FROM base AS limesurvey-src
# Find available releases:
# - https://community.limesurvey.org/downloads/
# - https://community.limesurvey.org/releases/
# - https://github.com/LimeSurvey/LimeSurvey/tags
# - https://newreleases.io/github/LimeSurvey/LimeSurvey
# Specify URL to LimeSurvey release zip file, see ls_version_detector.sh for update logic
ARG LIMESURVEY_URL=https://download.limesurvey.org/limesurvey7.1.0+260913.zip
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get install -y --no-install-recommends unzip && \
    curl -fsSLo /tmp/limesurvey.zip "$LIMESURVEY_URL" && \
    unzip -q -d /opt /tmp/limesurvey.zip && \
    rm /tmp/limesurvey.zip && \
    chmod -R u+rwX,g+rX-w,o-rwx /opt/limesurvey && \
    chmod -R u+rwX,g+rwX,o-rwx /opt/limesurvey/application/config && \
    chmod -R u+rwX,g+rwX,o-rwx /opt/limesurvey/tmp && \
    chmod -R u+rwX,g+rwX,o-rwx /opt/limesurvey/upload

########################################################################

# CI-only stage: changelog export
# - Scratch stage holding only the packaged LimeSurvey changelog, so the release workflow can
#   export it from the build
# - Not referenced by the runtime image

FROM scratch AS release-notes
COPY --from=limesurvey-src /opt/limesurvey/docs/release_notes.txt /release_notes.txt

########################################################################

# Stage 3: Runtime image

FROM base
# OCI image labels/annotations from the GitHub repo via docker/metadata-action in .github/workflows/build.yml
# Applied at build/push time as both per-arch labels+annotations and index annotations
# See https://github.com/opencontainers/image-spec/blob/main/annotations.md

# Set default timezone to UTC (can be overridden at runtime)
ENV TZ=Etc/UTC
# Use UTF-8 for Python IO streams
ENV PYTHONIOENCODING=UTF-8
# Do not buffer Python terminal output
ENV PYTHONUNBUFFERED=1
# Do not compile .pyc files, since the scripts run once per lifetime
ENV PYTHONDONTWRITEBYTECODE=1

ARG DEBIAN_FRONTEND=noninteractive
ARG DEBCONF_NOWARNINGS="yes"
# Install base packages, then PHP (PPA/PHP/extensions), and then clear out apt cruft
# Debian developer Sury publishes this PPA because the OS only includes a single specific version normally
# See https://deb.sury.org/
# See docs: https://www.limesurvey.org/manual/Installation_-_LimeSurvey_CE#Make_sure_you_can_use_LimeSurvey_on_your_website
# Note: `common`, `opcache`,`readline`, and `sodium` are automatically installed with these dependencies
# Tracked dependencies:
# - ca-certificates     (Cert bundle, required for HTTPS use with APT; installed in base)
# - cron                (Scheduled tasks, used to clean up sessions if in file mode)
# - curl                (HTTP client, for downloads during container build and by health checks/init; installed in base)
# - locales             (Internationalization/timezones)
# - nginx               (HTTP server, used to host LimeSurvey files)
# - python3             (System-provided Python used by init)
# - rsyslog             (Log management with syslog)
# - supervisor          (Service manager)
# - tini                (Init/PID 1)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    cron \
    locales \
    nginx \
    python3 \
    rsyslog \
    supervisor \
    tini && \
    curl -fsSLo /tmp/debsuryorg-archive-keyring.deb https://packages.sury.org/debsuryorg-archive-keyring.deb && \
    dpkg -i /tmp/debsuryorg-archive-keyring.deb && \
    rm /tmp/debsuryorg-archive-keyring.deb && \
    echo "deb [signed-by=/usr/share/keyrings/deb.sury.org-php.gpg] https://packages.sury.org/php/ $(. /etc/os-release && echo $VERSION_CODENAME) main" \
      > /etc/apt/sources.list.d/php.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    php8.4 \
    php8.4-bz2 \
    php8.4-cli \
    php8.4-curl \
    php8.4-fpm \
    php8.4-gd \
    php8.4-imap \
    php8.4-ldap \
    php8.4-mbstring \
    php8.4-mysql \
    php8.4-soap \
    php8.4-tidy \
    php8.4-xml \
    php8.4-zip && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/* /var/tmp/* /tmp/*

# Install PHP configs
COPY config/php/php.ini /etc/php/8.4/fpm/php.ini
COPY config/php/php-fpm.conf  /etc/php/8.4/fpm/php-fpm.conf
COPY config/php/www.conf /etc/php/8.4/fpm/pool.d/www.conf
# Prepare folder for PHP-FPM socket
RUN mkdir -p /var/run/php

# Create directories, import container-specific code
COPY app/ /app
RUN chmod +x /app/startup.sh

# Import supervisord configs
COPY config/supervisor/supervisord.conf /etc/supervisor/supervisord.conf
COPY config/supervisor/conf.d/* /etc/supervisor/conf.d/

# Import rsyslog configs
COPY config/rsyslog/rsyslog.conf /etc/rsyslog.conf
COPY config/rsyslog/rsyslog.d/* /etc/rsyslog.d/

# Import and install crontab
COPY config/cron/root_crontab /tmp/root_crontab
RUN crontab -u root /tmp/root_crontab && \
    rm /tmp/root_crontab

# Clean up nginx default files
RUN rm /etc/nginx/nginx.conf && \
    rm -rf /etc/nginx/sites-available && \
    rm /etc/nginx/sites-enabled/default && \
    rm -rf /var/www/html/*
# Import nginx configs
COPY config/nginx/nginx.conf /etc/nginx/nginx.conf
COPY config/nginx/limesurvey.conf /etc/nginx/sites-enabled/limesurvey.conf

# Retrieve LimeSurvey application files from prior stage
# Then assign the user permissions, and change file modes -Recursively:
# - user: read, write and eXecute,
# - group: read and eXecute, but not -write
# - other: none
# - X makes directories executable, but not files, unless already searchable/executable
# https://www.limesurvey.org/manual/Installation_security_hints#Linux_file_permissions
# The limesurvey/application/config directory requires Read & Write for saving the application configuration settings
# The limesurvey/tmp directory and its sub-directories are used for imports/uploads and should be set to Read & Write for your web server
# The upload directory and all its sub-directories must also have set Read & Write permissions in order to enable pictures and media files upload
# File permissions/mode are set in a previous stage and carry over here
# Ownership is applied via --chown to avoid additional layers blowing up the image size
# Note: On admin login, LimeSurvey warns it cannot create application/config/allowed_hosts.php even though it has permission here
COPY --from=limesurvey-src --chown=nobody:www-data /opt/limesurvey /var/www/html/limesurvey

# Stash the default upload tree so init.py can seed an empty upload volume on a fresh install;
# a bind mount over /var/www/html/limesurvey/upload would otherwise shadow the packaged contents
RUN cp -a /var/www/html/limesurvey/upload /opt/limesurvey-skel-upload

# Basic web server health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsSL http://127.0.0.1/ | grep -q LimeSurvey || exit 1

# Handle signals and run startup script
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/app/startup.sh"]

# Define port 80 (for use by nginx)
EXPOSE 80
