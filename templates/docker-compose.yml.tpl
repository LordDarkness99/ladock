services:
  app___PROJECT__:
    build:
      context: .
      dockerfile: .docker/Dockerfile
      args:
        PHP_VERSION: __PHP_VERSION__
        COMPOSER_VERSION: __COMPOSER_VERSION__
    container_name: __PROJECT___app
    restart: unless-stopped
    working_dir: /var/www
    volumes:
      - .:/var/www
    networks:
      - __PROJECT___net
    depends_on:
      - db___PROJECT__

  web___PROJECT__:
    image: nginx:stable-alpine
    container_name: __PROJECT___nginx
    restart: unless-stopped
    ports:
      - "__HTTP_PORT__:80"
    volumes:
      - .:/var/www
      - ./.docker/nginx.conf:/etc/nginx/conf.d/default.conf:ro
    networks:
      - __PROJECT___net
    depends_on:
      - app___PROJECT__

  db___PROJECT__:
    image: mysql:8.0
    container_name: __PROJECT___db
    restart: unless-stopped
    command: --default-authentication-plugin=mysql_native_password
    environment:
      MYSQL_DATABASE: __DB_NAME__
      MYSQL_USER: __DB_USER__
      MYSQL_PASSWORD: __DB_PASS__
      MYSQL_ROOT_PASSWORD: __DB_ROOT_PASS__
    ports:
      - "__DB_PORT__:3306"
    volumes:
      - __PROJECT___dbdata:/var/lib/mysql
    networks:
      - __PROJECT___net
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-uroot", "-p__DB_ROOT_PASS__"]
      interval: 5s
      timeout: 5s
      retries: 10

networks:
  __PROJECT___net:
    driver: bridge

volumes:
  __PROJECT___dbdata: