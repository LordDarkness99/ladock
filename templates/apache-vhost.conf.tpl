<VirtualHost *:80>
    ServerName localhost
    DocumentRoot __DOCUMENT_ROOT__

    <Directory __DOCUMENT_ROOT__>
        Options Indexes FollowSymLinks
        AllowOverride All
        Require all granted
    </Directory>

    ErrorLog ${APACHE_LOG_DIR}/__PROJECT___error.log
    CustomLog ${APACHE_LOG_DIR}/__PROJECT___access.log combined
</VirtualHost>
