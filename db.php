<?php

/*
 * Local development defaults keep the original project runnable, while real
 * credentials live outside source control in environment variables.
 */
$serverName = getenv('FARMEASY_DB_HOST') ?: '127.0.0.1';
$userName = getenv('FARMEASY_DB_USER') ?: 'root';
$password = getenv('FARMEASY_DB_PASSWORD') ?: '';
$dbName = getenv('FARMEASY_DB_NAME') ?: 'farmeasy';
$port = (int) (getenv('FARMEASY_DB_PORT') ?: 3306);

$conn = mysqli_connect($serverName, $userName, $password, $dbName, $port);
if (!$conn) {
    error_log('FarmEasy database connection failed: ' . mysqli_connect_error());
    http_response_code(500);
    exit('Database connection failed. Check the local configuration.');
}

mysqli_set_charset($conn, 'utf8mb4');
