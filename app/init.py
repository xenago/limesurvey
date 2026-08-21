import copy
import logging
import logging.handlers
import os
import subprocess
import time

import statics

"""Prepare and launch the container
"""

log = logging.getLogger("init")
log.setLevel(logging.DEBUG)


def is_value_true(value: str):
    """Determine if the given value is true. Case and whitespace-insensitive.
    True values: 1, t, true, y, yes
    All other values are interpreted as False.
    """
    # Strips all whitespace by splitting the lowercased-string and rejoining it together
    return "".join(value.lower().split()) in ("1", "t", "true", "y", "yes")


def start_service(name: str):
    """Start a supervisor service
    :param name: The process/service name to start
    """
    print(f"Starting `{name}`...")
    process = subprocess.Popen(["supervisorctl", "start", name],
                                stdin=subprocess.PIPE,
                                universal_newlines=True)
    return_code = process.wait()
    # Validate if the service has actually started
    service_ready = False
    if name == "php":
        for x in range(statics.STARTUP_WAIT_SECONDS * 10):
            # Validate that the socket has been created
            if os.path.exists(statics.PHP_FPM_SOCKET):
                service_ready = True
                break
            time.sleep(0.1)
    elif name == "nginx":
        for x in range(statics.STARTUP_WAIT_SECONDS * 10):
            # Validate that the web server contains the expected string
            p = subprocess.run(["curl", "-kL", "http://127.0.0.1/"], capture_output=True, text=True)
            if "<!DOCTYPE html>" in p.stdout:
                service_ready = True
                break
            time.sleep(0.1)
    elif name == "rsyslog":
        for x in range(statics.STARTUP_WAIT_SECONDS * 10):
            # rsyslog creates the /dev/log socket once it is up
            if os.path.exists(statics.SYSLOG_SOCKET):
                service_ready = True
                break
            time.sleep(0.1)
    else:
        service_ready = True
    if not service_ready:
        print(f"Error: unable to start {name} in {statics.STARTUP_WAIT_SECONDS} seconds")
        short_circuit()
    if return_code != 0:
        print(f"Return code from {name} start: {return_code}")


def short_circuit():
    """Stop the container with an error code
    """
    try:
        # Send SIGKILL (9) to PID 1 (tini) so the container exits immediately with code 137
        # https://github.com/PyCQA/bandit/issues/333
        process = subprocess.Popen(["kill", "-9", "1"])  # nosec
        process.wait()
    except Exception as e:
        print(f"Fatal error on exit: {str(e)}")
    exit(1)


def run_or_fail(cmd, description):
    """Run a command, stopping the container via short_circuit() if it exits non-zero."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error(f"{description} failed (rc={result.returncode}): {result.stderr.strip()}")
        short_circuit()
    return result


def configure_logging():
    """Attach the log handler
    """
    if log.handlers:
        return
    try:
        # rsyslog reads /dev/log and splits messages to stdout/stderr by severity
        handler = logging.handlers.SysLogHandler(
            facility=logging.handlers.SysLogHandler.LOG_LOCAL0, address="/dev/log")
        handler.setFormatter(logging.Formatter(statics.LOG_FORMAT))
    except Exception:
        # fall back to console if rsyslog is unavailable
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(statics.LOG_FORMAT_TIME))
    log.addHandler(handler)


def run():
    """Prepare and start services
    """
    # Load config/ENV vars and apply options
    print("Initializing container...")
    print("Checking configuration...")
    # Check every environment variable against the defaults
    #   - if any matching keys have different values, highlight them
    #   - if any keys are not present in the defaults, highlight them
    #   - censor output if it is a password or token
    env = copy.deepcopy(statics.DEFAULT_ENV)
    for variable, value in sorted(os.environ.items()):        
        # Found expected variable
        if variable in statics.DEFAULT_ENV:
            if value != statics.DEFAULT_ENV[variable]:
                if "KEY" not in variable and "PASSWORD" not in variable and "TOKEN" not in variable:
                    print(f"Overriding default: {variable}={value}")
                else:
                    print(f"Overriding default: {variable}=***")
                env[variable] = value
        elif variable in statics.IGNORED_ENV:
            # Known benign container/shell variable; ignore without warning
            continue
        else:
            if "KEY" not in variable and "PASSWORD" not in variable and "TOKEN" not in variable:
                print(f"Warning: Unknown variable `{variable}={value}`")
            else:
                print(f"Warning: Unknown variable `{variable}=***`")

    # Apply runtime config overrides
    if "LS_PROXY_IP" in env and len(env["LS_PROXY_IP"].strip()) > 0:
        ls_nginx_file = statics.NGINX_SITE_CONF
        ls_proxy_ip = env["LS_PROXY_IP"].strip()
        print(f"Applying `LS_PROXY_IP={ls_proxy_ip}` in `{ls_nginx_file}`")
        with open(ls_nginx_file, 'r') as f:
            file_contents = f.read()
        find_text = "# https://nginx.org/en/docs/http/ngx_http_realip_module.html"
        replace_text = f"set_real_ip_from {ls_proxy_ip};\n    real_ip_header X-Forwarded-For;\n    real_ip_recursive on;"
        file_contents = file_contents.replace(find_text, replace_text)
        with open(ls_nginx_file, 'w') as f:
            f.write(file_contents)
    if "TZ" in env and len(env["TZ"].strip()) > 0:
        ls_php_file = statics.PHP_FPM_INI
        ls_tz = env["TZ"].strip()
        print(f"Applying `TZ={ls_tz}` in `{ls_php_file}`")
        with open(ls_php_file, 'r') as f:
            file_contents = f.read()
        find_text = ";date.timezone ="
        replace_text = f"date.timezone = {ls_tz}"
        file_contents = file_contents.replace(find_text, replace_text)
        with open(ls_php_file, 'w') as f:
            f.write(file_contents)

    # Start the log service first
    if is_value_true(env["LS_SERVICE_RSYSLOG"]):
        start_service("rsyslog")
    configure_logging()

    # Prepare persistent data that may arrive as fresh (empty) bind mounts. Fresh bind mounts are
    # created root-owned, and an empty upload volume shadows the packaged defaults.
    ls_config = statics.LIMESURVEY_CONFIG_DIR
    upload_dir = statics.LIMESURVEY_UPLOAD_DIR
    upload_skel = statics.LIMESURVEY_UPLOAD_SKEL
    if os.path.isdir(upload_skel) and os.path.isdir(upload_dir) and not os.listdir(upload_dir):
        log.info("Seeding upload directory from image defaults...")
        run_or_fail(["cp", "-a", upload_skel + "/.", upload_dir], "Seeding the upload directory")
    # config.php is only read at runtime: group-readable for the web user, never world-readable
    if os.path.exists(ls_config + "/config.php"):
        run_or_fail(["chown", "nobody:www-data", ls_config + "/config.php"], "Setting ownership on config.php")
        run_or_fail(["chmod", "u=rw,g=r,o=", ls_config + "/config.php"], "Setting permissions on config.php")
    # upload (survey files) and security.php (generated encryption keys) must be writable by www-data
    for path in (upload_dir, ls_config + "/security.php"):
        if os.path.exists(path):
            run_or_fail(["chown", "nobody:www-data", path], f"Setting ownership on {path}")
            run_or_fail(["chmod", "u+rwX,g+rwX,o-rwx", path], f"Setting permissions on {path}")

    # Verify database and apply schema before starting the web server.
    # These steps run via the PHP CLI and need neither php-fpm nor nginx.
    # A failure calls short_circuit() to stop the container.
    # Decide install vs update by checking for an existing schema, rather than inferring it from a
    # failed update. The check exits 0 if a core table exists, 1 if the database is reachable but
    # has no schema, or 2 if it cannot be reached.
    log.info("Checking database installation state...")
    check = subprocess.run(["php", "-r", statics.DB_SCHEMA_CHECK_PHP], capture_output=True, cwd=statics.LIMESURVEY_DIR, text=True)
    if check.returncode == 0:
        # Existing installation: bring the schema up to date
        log.info("Running database schema update...")
        p = subprocess.run(["php", "-d", "memory_limit=-1", "application/commands/console.php", "updatedb"], capture_output=True, cwd=statics.LIMESURVEY_DIR, text=True)
        log.info(f"Ran database schema update: returncode={p.returncode}, stdout={p.stdout}, stderr={p.stderr}")
        if p.returncode != 0:
            log.error("Database schema update failed.")
            short_circuit()
    elif check.returncode == 1 and env["LS_ADMIN_PASSWORD"].strip():
        # Reachable but empty, with admin credentials supplied: install the schema and initial admin
        log.info("Database reachable but empty; creating schema and initial admin account...")
        p = subprocess.run(["php", "-d", "memory_limit=-1", "application/commands/console.php", "install", env["LS_ADMIN_USER"], env["LS_ADMIN_PASSWORD"], env["LS_ADMIN_NAME"], env["LS_ADMIN_EMAIL"]], capture_output=True, cwd=statics.LIMESURVEY_DIR, text=True)
        # Log fields individually: the CompletedProcess repr would include the admin password in its args
        log.info(f"Ran install: returncode={p.returncode}, stdout={p.stdout}, stderr={p.stderr}")
        if p.returncode != 0:
            log.error("Database install failed.")
            short_circuit()
    elif check.returncode == 1:
        log.info("Database is empty and LS_ADMIN_PASSWORD is not set; skipping auto-install")
    else:
        # rc == 2 (unreachable) or any unexpected code: never serve against an unknown database
        log.error(f"Could not reach or determine the database state (rc={check.returncode}): {check.stderr.strip()}")
        short_circuit()

    # Clear cached assets so stale files from a previous version are not served after an upgrade.
    # A flush failure is only cosmetic (stale assets), so warn but do not block startup.
    log.info("Flushing asset cache...")
    p = subprocess.run(["php", "application/commands/console.php", "flushassets"], capture_output=True, cwd=statics.LIMESURVEY_DIR, text=True)
    if p.returncode == 0:
        log.info(f"Flushed asset cache: stdout={p.stdout}, stderr={p.stderr}")
    else:
        log.warning(f"Asset cache flush failed; continuing startup: returncode={p.returncode}, stdout={p.stdout}, stderr={p.stderr}")

    # Start the remaining services
    log.info("Starting the web server and remaining services...")
    for service in statics.SERVICES_ORDER:
        # Check if the service is enabled in env
        if service != "rsyslog" and is_value_true(env[f"LS_SERVICE_{service.upper()}"]):
            start_service(service)

    log.info("Init complete.")


# Run the script if executed standalone
if __name__ == "__main__":
    run()
