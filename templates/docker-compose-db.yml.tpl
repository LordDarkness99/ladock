services:
  db___PROJECT__:
    image: mysql:8.0
    container_name: __PROJECT___db
    restart: unless-stopped
    command: --default-authentication-plugin=mysql_native_password
    environment:
      MYSQL_DATABASE: "__DB_NAME__"
      MYSQL_USER: "__DB_USER__"
      MYSQL_PASSWORD: "__DB_PASS__"
      MYSQL_ROOT_PASSWORD: "__DB_ROOT_PASS__"
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
      retries: 15

networks:
  __PROJECT___net:
    name: __PROJECT___net

volumes:
  __PROJECT___dbdata:
