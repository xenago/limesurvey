# LimeSurvey

Containerized build of Open Source [LimeSurvey CE](https://github.com/LimeSurvey/LimeSurvey), usable for a new deployment or to migrate an existing one. Not affiliated with [LimeSurvey](https://www.limesurvey.org/).

## Components

- LimeSurvey
- nginx
- PHP-FPM
- tini
- Supervisor
- Debian
- MariaDB (optional, runs in separate container)

### Containers

- LimeSurvey (HTTP) container on port 80, intended to be accessed by an external-facing reverse proxy server (image built in this repository)
- MariaDB (MySQL) container on internal port 3306 (using official image)

### Image

The image is published to `ghcr.io/xenago/limesurvey:latest` and is built for `amd64` and `arm64`.

[Supervisor](config/supervisor) is used as process manager; it starts [`init.py`](app/init.py), which performs startup tasks before running the web service.

## Deployment

Requires Docker Compose. These steps pull the prebuilt image and install a fresh database on first start.

1. Download or clone the repository:

       git clone https://github.com/xenago/limesurvey.git
       cd limesurvey

2. Copy the environment template and set the passwords:

       cp .env.example .env

   Set `MARIADB_PASSWORD` and `MARIADB_ROOT_PASSWORD`. To auto-install a fresh database, also set `LS_ADMIN_PASSWORD`. See [Configuration](#configuration).

3. Create the data directory and the two mounted config files. The image does not generate `config.php`; it must be prepared beforehand. They must exist as files before the first start, otherwise Docker creates them as directories:

       mkdir -p ./data/limesurvey
       cp examples/config.php ./data/limesurvey/config.php
       touch ./data/limesurvey/security.php

   The `upload` and database directories are created automatically as bind mounts. On start the container seeds an empty `upload` directory from the packaged defaults and sets ownership on the data it manages, so no manual `chown` is needed.

4. Edit `./data/limesurvey/config.php` to set the database name, user, and password to match the `MARIADB_*` entries in `.env`.

5. Start the stack. By default this pulls the prebuilt image from GHCR:

       docker compose up -d

   To build the image locally instead of pulling, add `--build`:

       docker compose up -d --build

   Browse to http://localhost once the containers report healthy. If the page doesn't load, monitor `docker compose logs -f` and check `docker compose ps` for container health.

When starting up, the container checks the database. If it is reachable but empty and `LS_ADMIN_PASSWORD` is set, the schema is prepared and the admin account is created.
If the database already has a schema, it runs the schema update instead. An unreachable database or a failed schema update/install will abort the container startup. Once everything is set up, clear `LS_ADMIN_PASSWORD` from .env and change the admin password in the web interface.

LimeSurvey writes data encryption keys into `security.php` on first use. If the keys are lost, encrypted responses and participant data cannot be recovered.

Implement a backup strategy for both the MariaDB database, and the LimeSurvey user data files.

## Configuration

The compose stack reads variables from `.env` (see [`.env.example`](.env.example)):

- `MARIADB_DATABASE`: database created on first start; must match `config.php`
- `MARIADB_USER`: application database user; must match `config.php`
- `MARIADB_PASSWORD`: application user password; must match `config.php`
- `MARIADB_ROOT_PASSWORD`: database root password
- `LS_ADMIN_USER`: initial admin username (default `admin`)
- `LS_ADMIN_PASSWORD`: initial admin password; leave blank to skip auto-install
- `LS_ADMIN_NAME`: initial admin display name
- `LS_ADMIN_EMAIL`: initial admin email address
- `LIMESURVEY_IMAGE`: optional, override the image reference, for example to pin a specific version tag
- `LS_DATA_DIR`: optional, absolute path for persistent data (default `./data` beside the compose file)
- `LS_PROXY_IP`: optional, trusted reverse-proxy IP or CIDR so the real client IP is recovered from `X-Forwarded-For` (default empty; see [Proxy](#proxy))
- `TZ`: optional, applied to PHP and logs (default `Etc/UTC`)

Application settings live in `config.php`, copied from [`examples/config.php`](examples/config.php).
That sample enables database-backed sessions, so sessions survive redeployment without a shared volume.
The `allowedHosts` trusted-host setting is also documented there.

By default the stack pulls the prebuilt image from `ghcr.io/xenago/limesurvey`. To refresh it later, run `docker compose pull` followed by `docker compose up -d`. To pin a tag, set `LIMESURVEY_IMAGE` in `.env` (for example `ghcr.io/xenago/limesurvey:7.0.11-260821`).

To build the image locally instead of pulling, run `docker compose up -d --build`; this is also how you deploy a custom LimeSurvey version (see [Updating LimeSurvey](#updating-limesurvey)). To make local builds the persistent default so Compose never pulls, set `LIMESURVEY_IMAGE=limesurvey:local` in `.env`.

To keep persistent data outside the compose folder, set `LS_DATA_DIR` to a different location, e.g. a sibling directory.

## Proxy

The container serves plain HTTP on port 80, so put a reverse proxy in front of it and enable HTTPS. The sample [`nginx-proxy.conf`](examples/nginx-proxy.conf) can be used as a starting point, though it will need to be customized depending on your setup.

When serving over HTTPS, set the session cookie to secure in `config.php` (`session` > `cookieParams` > `'secure' => true`). Add the public hostname to `allowedHosts`, retaining `localhost` and `127.0.0.1` for the container health check.

Set `LS_PROXY_IP` in `.env` to the reverse proxy's address or CIDR (e.g. an internal host `10.0.0.5` or segment `10.0.0.0/8`). The `X-Forwarded-For` header will be trusted and real client IPs will be visible instead of the proxy's address.

## Migrating an existing deployment

To use an existing LimeSurvey install, see the [migration section](docs/README.md#migrating-an-existing-deployment) in the docs.

## Reset the admin password

    docker compose exec -w /var/www/html/limesurvey limesurvey \
        php application/commands/console.php resetpassword <adminuser> '<newpassword>'

The account must already exist (default `admin`). `resetpassword` takes the password as a command-line argument, so it is briefly visible in the container process list while it runs. Ensure that the command is only run in a trusted single-user environment.

Note: If `console.php` is run with no arguments it will list the other commands (`install`, `updatedb`, `flushassets`, etc.).

## Updating LimeSurvey

Using the default prebuilt image, pull the newer release and redeploy:

    docker compose pull
    docker compose up -d

The published `latest` tag tracks the newest LimeSurvey release; pin a specific version with `LIMESURVEY_IMAGE` in `.env`.

To build a specific version locally instead:

1. Confirm no special upgrade steps are required for the jump:

   https://github.com/LimeSurvey/LimeSurvey/blob/master/docs/release_notes.txt

   https://www.limesurvey.org/manual/Upgrading_from_a_previous_version

2. Update `LIMESURVEY_URL` in the [`Dockerfile`](Dockerfile) to the target release zip:

   https://community.limesurvey.org/releases/

3. Rebuild the image and redeploy. On start the container runs the schema update (`updatedb`) against the existing database, which only moves the schema forward.

Back up the database and `security.php` before upgrading.

## Updating MariaDB

The MariaDB image is pinned in `docker-compose.yml`. When bumping it across a major version, the persistent data directory needs upgrading to match: set `MARIADB_AUTO_UPGRADE=1` in `.env`, or run `mariadb-upgrade` in the container. Upgrade one major version at a time, and back up the data directory first.
