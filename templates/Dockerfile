# ============================================================
# LaDock — Universal PHP + Apache Application Image
# ============================================================
ARG PHP_VERSION=8.2
ARG COMPOSER_VERSION=2

# Stage untuk Composer (pilih versi)
FROM composer:${COMPOSER_VERSION} AS composer

# Stage utama PHP + Apache
FROM php:${PHP_VERSION}-apache

# System deps + PHP extensions + mod_rewrite
RUN (sed -i 's|http://deb.debian.org/debian-security|http://archive.debian.org/debian-security|g' /etc/apt/sources.list \
  && sed -i 's|http://security.debian.org|http://archive.debian.org/debian-security|g' /etc/apt/sources.list \
  && sed -i 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' /etc/apt/sources.list \
  && sed -i '/-updates/d' /etc/apt/sources.list \
  || true) \
 && (apt-get update -o Acquire::Check-Valid-Until=false || true) \
 && (apt-get install -y --no-install-recommends --allow-unauthenticated \
      -o Acquire::http::Timeout=60 \
      -o Acquire::Retries=5 \
      git curl zip unzip \
      libpng-dev libxml2-dev libzip-dev libicu-dev libmcrypt-dev || true) \
 && (apt-get install -y --no-install-recommends --allow-unauthenticated libonig-dev || true) \
 && (docker-php-ext-install pdo_mysql mysqli mbstring exif pcntl bcmath gd zip intl || \
     docker-php-ext-install pdo_mysql mysqli mbstring gd zip || \
     docker-php-ext-install pdo_mysql mysqli || true) \
 && (docker-php-ext-install mcrypt || (pecl install mcrypt && docker-php-ext-enable mcrypt) || true) \
 && a2enmod rewrite headers \
 && echo "ServerName localhost" >> /etc/apache2/apache2.conf \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN docker-php-ext-install mysqli

# Copy Composer dari stage composer
COPY --from=composer /usr/bin/composer /usr/bin/composer

WORKDIR /var/www

EXPOSE 80
CMD ["apache2-foreground"]