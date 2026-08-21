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
# Reads the DB connection from config.php and exits 0 if a core table exists,
# 1 if the database is reachable but has no schema, or 2 if it cannot be reached.
DB_SCHEMA_CHECK_PHP = r'''
$c = require "''' + LIMESURVEY_CONFIG_DIR + r'''/config.php";
$db = $c["components"]["db"];
try {
    $pdo = new PDO($db["connectionString"], $db["username"], $db["password"]);
    $prefix = isset($db["tablePrefix"]) ? $db["tablePrefix"] : "";
    $stmt = $pdo->prepare("SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = ?");
    $stmt->execute([$prefix . "settings_global"]);
    exit($stmt->fetch() ? 0 : 1);
} catch (Throwable $e) {
    fwrite(STDERR, $e->getMessage() . "\n");
    exit(2);
}
'''
