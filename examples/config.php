<?php if (!defined('BASEPATH')) exit('No direct script access allowed');

/*
 * Sample LimeSurvey configuration based on upstream config-sample-mysql.php
 * 
 * Copy it to the data directory (e.g. ./data/limesurvey/config.php)
 * and fill in the database credentials.
 * 
 * The database name, user, and password must match the MARIADB_* variables
 * in .env (see .env.example and docker-compose.yml).
 */

return array(
    'components' => array(
        'db' => array(
            // Supported database drivers are mysql, pgsql, mssql, sqlite, and oci
            // Only the mysql driver is installed in the container, since MariaDB is used
            'connectionString' => 'mysql:host=limesurvey-mariadb;port=3306;dbname=limesurvey_db;',
            'emulatePrepare' => true,
            'username' => 'limesurvey',
            'password' => 'CHANGEME',
            'charset' => 'utf8mb4',
            'tablePrefix' => 'lime_',
        ),

        // Database-backed sessions survive container redeployments and don't need a shared volume.
        // The sessions table is created automatically on first use.
        // Pruning is controlled by gCProbability below, and file session GC is disabled by default.
        // When run directly, don't use the DB sessions
        'session' => (PHP_SAPI === 'cli') ? array() : array(
            'class' => 'application.core.web.DbHttpSession',
            'connectionID' => 'db',
            'sessionTableName' => '{{sessions}}',
            'gCProbability' => 1,  // Prunes expired sessions about 1 percent of the time
            'cookieParams' => array(
                'httponly' => true,
                // Enable secure cookies once behind an HTTPS proxy
                //'secure' => true,
                'secure' => false,
            ),
        ),

        // LimeSurvey 7's new question editor requires the "path" URL format
        'urlManager' => array(
            'urlFormat' => 'path',
            'rules' => array(
                // You can add your own rules here
            ),
            'showScriptName' => false,
        ),
    ),

    'config' => array(
        // Trusted host protection:
        // Add any public hostnames to the list once the site is proxied
        // Ensure the loopback entries are included, otherwise the localhost startup/health checks are blocked
        // 'allowedHosts' => array('surveys.example.com', 'localhost', '127.0.0.1'),
        'debug' => 0,
        'debugsql' => 0,
        // Disable buggy 'https not enabled' alert
        //'ssl_disable_alert' => true,
        // Don't check upstream for updates in the UI
        //'updatable' => false,
    ),
);
