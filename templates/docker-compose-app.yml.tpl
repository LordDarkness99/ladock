services:
  app___PROJECT__:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        PHP_VERSION: "__PHP_VERSION__"
        COMPOSER_VERSION: "__COMPOSER_VERSION__"
    container_name: __PROJECT___app
    restart: unless-stopped
    mem_limit: __MEMORY_LIMIT__
    working_dir: /var/www
    ports:
      - "__HTTP_PORT__:80"
    volumes:
      - ./src:/var/www
      - ./apache-vhost.conf:/etc/apache2/sites-available/000-default.conf:ro
    env_file:
      - ./src/.env
    environment:
      APP_ENV: "local"
    networks:
      - ladock_net

networks:
  ladock_net:
    name: ladock_net
    external: true
