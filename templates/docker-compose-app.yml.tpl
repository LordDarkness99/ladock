services:
  app___PROJECT__:
    build:
      context: .
      dockerfile: .docker/Dockerfile
      args:
        PHP_VERSION: "__PHP_VERSION__"
        COMPOSER_VERSION: "__COMPOSER_VERSION__"
    container_name: __PROJECT___app
    restart: unless-stopped
    working_dir: /var/www
    ports:
      - "__HTTP_PORT__:80"
    volumes:
      - .:/var/www
      - ./.docker/apache-vhost.conf:/etc/apache2/sites-available/000-default.conf:ro
    environment:
      APP_ENV: "local"
      DB_CONNECTION: "mysql"
      DB_HOST: "ladock_mysql"
      DB_PORT: "3306"
      DB_DATABASE: "__DB_NAME__"
      DB_USERNAME: "__DB_USER__"
      DB_PASSWORD: "__DB_PASS__"
    networks:
      - ladock_net

networks:
  ladock_net:
    name: ladock_net
    external: true
