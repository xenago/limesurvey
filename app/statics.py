"""Static values
"""

# Store the default/expected environment variables
DEFAULT_ENV = {
    # ========
    # Runtime environment configuration options
    "LS_SERVICE_CRON": "1",  # Run Cron
    "LS_SERVICE_NGINX": "1",  # Run LimeSurvey
    "LS_SERVICE_PHP": "1",  # Run PHP-FPM (FastCGI)
    "LS_SERVICE_RSYSLOG": "1",  # Run rsyslog
    "LS_PROXY_IP": "",  # Set proxy IP address (or range like `192.168.0.0/16`) - if empty, no proxy is assumed
    "LS_ADMIN_USER": "admin",  # Initial admin username, used only when auto-installing an empty database
    "LS_ADMIN_PASSWORD": "",  # Initial admin password; if empty, database auto-install is skipped
    "LS_ADMIN_NAME": "Administrator",  # Initial admin display name (auto-install only)
    "LS_ADMIN_EMAIL": "admin@example.com",  # Initial admin email address (auto-install only)
    # ========
    # Values baked-in at build time or expected in the environment, indicated by: *Preset*
    # These should typically not be changed
    "HOME": "/root",  # *Preset* User homedir is root for the service manager
    "HOSTNAME": "limesurvey",  # *Preset* Default hostname
    "LC_CTYPE": "C.UTF-8",  # *Preset* Expected default locale for ctype/multibyte functions
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",  # *Preset* Default system PATH
    "PWD": "/",  # *Preset*
    "PYTHONIOENCODING": "UTF-8",  # *Preset* Python IO encoding to UTF-8 (in Dockerfile)
    "PYTHONUNBUFFERED": "1",  # *Preset* Python stdout/stderr routing (in Dockerfile)
    "PYTHONDONTWRITEBYTECODE": "1",  # *Preset* Skip writing .pyc bytecode cache (in Dockerfile)
    "SUPERVISOR_ENABLED": "1",  # *Preset* Set by Supervisor in the environment
    "SUPERVISOR_SERVER_URL": "unix:///dev/shm/supervisor.sock",  # *Preset* Supervisor server URL (in supervisord.conf)
    "SUPERVISOR_PROCESS_NAME": "init",  # *Preset* Name of init script service process (in init_service.conf)
    "SUPERVISOR_GROUP_NAME": "init",  # *Preset* Name of init script service group (in init_service.conf)
    "TZ": "Etc/UTC",  # *Preset* Timezone (in Dockerfile)
}

# Environment variables that may appear and can be ignored
IGNORED_ENV = {
    "LIMESURVEY_IMAGE",
    "LS_DATA_DIR",
    "MARIADB_DATABASE",
    "MARIADB_USER",
    "MARIADB_PASSWORD",
    "MARIADB_ROOT_PASSWORD",
    "SHLVL",     # shell nesting level, set by the startup shell
    "_",         # last command executed, set by the shell
    "OLDPWD",    # previous working directory, set by the shell
    "TERM",      # terminal type, set when a TTY is attached
    "LANG",      # locale
    "LANGUAGE",  # locale
    "LC_ALL",    # locale
    "container",  # set by some container runtimes
}

# Define Python-based log format
LOG_FORMAT = "[%(process)s] %(filename)s:%(lineno)d [%(levelname)s]: %(message)s"
LOG_FORMAT_TIME = "%(asctime)s [%(process)s] %(filename)s:%(lineno)d [%(levelname)s]: %(message)s"

# List in startup order (shutdown occurs in reverse order)
SERVICES_ORDER = [
    "rsyslog",
    "php",
    "nginx",
    "cron"
]

# Used as a delay timeout in the init
STARTUP_WAIT_SECONDS = 10

# LimeSurvey application paths (baked into the image)
LIMESURVEY_DIR = "/var/www/html/limesurvey"
LIMESURVEY_CONFIG_DIR = LIMESURVEY_DIR + "/application/config"
LIMESURVEY_UPLOAD_DIR = LIMESURVEY_DIR + "/upload"
# Pristine copy of the default upload tree, used to seed an empty upload volume (see Dockerfile)
LIMESURVEY_UPLOAD_SKEL = "/opt/limesurvey-skel-upload"

# Service config files edited at runtime from environment variables
NGINX_SITE_CONF = "/etc/nginx/sites-enabled/limesurvey.conf"
PHP_FPM_INI = "/etc/php/8.3/fpm/php.ini"
# PHP-FPM socket (defined in config/php/www.conf); init waits for it to appear
PHP_FPM_SOCKET = "/var/run/php/php-fpm.sock"
# Syslog socket created by rsyslog when it comes up; init waits for it to appear
SYSLOG_SOCKET = "/dev/log"

# PHP used to detect whether the database already holds a LimeSurvey schema.
# BASEPATH must be defined before the require: every LimeSurvey config.php starts with
# `if (!defined('BASEPATH')) exit('No direct script access allowed');`, and that exit() prints to
# stdout and returns status 0, which would otherwise look like "schema present" to this check.
# Reads DB connection in config.php:
# - exits 0 if settings_global has a DBVersion row whose value is a positive integer
#   (mirrors UpdateDBCommand's own `if (!intval($currentDbVersion))` check, since a present-but-
#   falsy value would otherwise pass a naive existence check yet still be rejected by updatedb)
# - exits 1 if the database is reachable but the table is missing or DBVersion is absent/falsy
# - exits 2 if it cannot be reached
# Every exit path logs an "LS_DB_CHECK:" line to stderr, so the reason for the exit code shows up
# in the container logs and the caller can tell a real result from a script that never ran.
DB_SCHEMA_CHECK_PHP = r'''
define("BASEPATH", "''' + LIMESURVEY_DIR + r'''");
$c = require "''' + LIMESURVEY_CONFIG_DIR + r'''/config.php";
if (!is_array($c) || !isset($c["components"]["db"]["connectionString"])) {
    fwrite(STDERR, "LS_DB_CHECK: config.php did not return a database configuration\n");
    exit(2);
}
$db = $c["components"]["db"];
try {
    $pdo = new PDO($db["connectionString"], $db["username"], $db["password"]);
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $prefix = isset($db["tablePrefix"]) ? $db["tablePrefix"] : "";
    $stmt = $pdo->prepare("SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = ?");
    $stmt->execute([$prefix . "settings_global"]);
    if (!$stmt->fetch()) {
        fwrite(STDERR, "LS_DB_CHECK: settings_global table not found\n");
        exit(1);
    }
    $stmt = $pdo->prepare("SELECT stg_value FROM `" . $prefix . "settings_global` WHERE stg_name = ?");
    $stmt->execute(["DBVersion"]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    $dbVersion = $row ? intval($row["stg_value"]) : 0;
    fwrite(STDERR, "LS_DB_CHECK: settings_global exists; DBVersion row " . ($row ? "= '" . $row["stg_value"] . "'" : "not found") . "\n");
    exit($dbVersion > 0 ? 0 : 1);
} catch (Throwable $e) {
    fwrite(STDERR, "LS_DB_CHECK: " . $e->getMessage() . "\n");
    exit(2);
}
'''
