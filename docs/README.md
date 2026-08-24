# Documentation

Development and release info, with incoming migration steps for an existing LimeSurvey deployment.

## Development and releases

Automated updates land on the `dev` branch and collect there.
A release is published by merging `dev` into `main` and pushing a version tag,
so that a push to `main` never cuts a new release alone.

### Workflows

- `update-limesurvey.yml` runs weekly (Monday 06:00 UTC). It creates `dev` from the default
  branch if missing, detects the newest LimeSurvey release with `ls_version_detector.sh`, and
  opens a pull request bumping `LIMESURVEY_URL` in the Dockerfile against `dev`. Set `LS_MAJOR`
  in that workflow to track a single major line instead of the latest release overall.
- Dependabot runs 30 minutes afterwards, and opens Docker and GitHub Actions updates against `dev`.
- `build.yml` builds the image natively for `linux/amd64` and `linux/arm64` and smoke-tests the
  stack
- PRs into `dev` and manual runs validate the build and smoke test only
- A semver tag pushed to `main` builds, tests, pushes, and publishes a release

### Initial repository setup

- Enable `Allow GitHub Actions to create and approve pull requests` under
  `Settings > Actions > General > Workflow permissions` so the update workflow can open PRs.
- Enable Dependabot alerts and security updates under `Settings > Advanced security`.
- Enable `Private vulnerability reporting` under `Settings > Advanced Security` for the [SECURITY.md](SECURITY.md) process.

### Cutting a release

1. Prepare a stable commit on `dev`
2. Merge from `dev` to `main`
3. Tag the release commit with the LimeSurvey version and push the tag:

       git tag 7.0.11+260821
       git push origin 7.0.11+260821

`build.yml` publishes the version with `+` rewritten to `-` (for example `6.17.16-260814`,
since Docker tags cannot contain `+`) and a commit-sha tag. It also updates `latest`, but only
when the pushed tag is the highest version, so tagging an older release later never rolls
`latest` backwards. The tag must point at a commit on `main`, or the workflow refuses to publish.
A GitHub Release is created for the tag with the image pull commands and the packaged LimeSurvey changelog.

The image in this repo publishes to `ghcr.io/xenago/limesurvey` using the built-in `GITHUB_TOKEN`.
The visibility can be set after the first tagged publish creates the package.

## Migrating an existing deployment

If already running LimeSurvey, it can be migrated to this stack.
That was the original purpose of this repository internally, before being cleaned up for publishing: to migrate a standalone deployment previously updated by [ls_updater](https://github.com/xenago/ls_updater).
Two parts can be migrated: the application/files (`config.php`, `security.php`, along with the `upload` directory), and the database (optional).

If the LimeSurvey container is intended to be run with an existing external database, only the file state needs to be migrated.
See [Keeping an external database](#keeping-an-external-database) below for details.

Notes before starting migration:

- Back up the database and LimeSurvey deployment as a whole.
- The image must be running the same or newer LimeSurvey version than the current install. On
  first start it runs the schema upgrade (`updatedb`), which only moves forward.
- The existing `security.php` must be preserved. It holds the data-encryption keys, and losing them
  makes encrypted responses and participant data unrecoverable.

Paths below assume the default data directory `./data` (see `LS_DATA_DIR` in the README); adjust if it is set elsewhere.
For an [ls_updater](https://github.com/xenago/ls_updater)-managed source, the files are a standard LimeSurvey layout
under the configured `install_path`, and the database credentials are in `~/.my.cnf`.

### 1. Copy the file state

Needed in every case:

    mkdir -p ./data/limesurvey
    cp -a <install_path>/upload                          ./data/limesurvey/upload
    cp    <install_path>/application/config/config.php   ./data/limesurvey/config.php
    cp    <install_path>/application/config/security.php ./data/limesurvey/security.php

The container will automatically set ownership on these at startup as-needed.

### 2. Point config.php at the database

In `./data/limesurvey/config.php`:

- Set the `db` `connectionString` host: `host=limesurvey-mariadb` for the bundled MariaDB, or the
  existing server's hostname to keep an external database.
- Set the username and password to match that database (the `MARIADB_USER`/`MARIADB_PASSWORD` from
  `.env` when using the bundled MariaDB).
- Leave the table prefix unchanged.

Leave `LS_ADMIN_PASSWORD` blank in `.env` so the container does not auto-install over the existing
data.

### 3. Move the database (skip when keeping an external database)

Stop the old site so no new responses arrive, then export the database:

    mysqldump --single-transaction --routines --triggers <dbname> > limesurvey.sql

Bring up only the bundled MariaDB (it creates an empty database and user from the `MARIADB_*`
variables), then load the dump into it:

    docker compose up -d limesurvey-mariadb
    docker compose exec -T limesurvey-mariadb \
        mariadb -u<user> -p<password> <dbname> < limesurvey.sql

### 4. Start the stack

    docker compose up -d
    docker compose logs -f

On startup the LimeSurvey container will detect the existing schema and run `updatedb` to bring it up to the image's version.
The logs show the schema update; after that, log in and confirm the site works.

### Keeping an external database

To continue using the current database server, only steps 1 and 2 apply.
In step 2, set the `config.php` host to the existing database server and keep its credentials.
Remove or comment out the `limesurvey-mariadb` service and the `depends_on` block from `docker-compose.yml`, and skip step 3.
The container still runs `updatedb` against the external database on start;
that database must be reachable from the container and its user permitted to connect from the container network.
