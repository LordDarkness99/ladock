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
  && sed -i 's|http://security.debian.org|http://archive.debian.org|g' /etc/apt/sources.list \
  || true) \
 && (apt-get update -o Acquire::Check-Valid-Until=false || (sed -i 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' /etc/apt/sources.list && apt-get update -o Acquire::Check-Valid-Until=false)) \
 && apt-get install -y --no-install-recommends --fix-missing \
      -o Acquire::http::Timeout=60 \
      -o Acquire::Retries=5 \
      git curl zip unzip \
      libpng-dev libonig-dev libxml2-dev libzip-dev \
      libicu-dev \
 && docker-php-ext-install pdo_mysql mbstring exif pcntl bcmath gd zip intl \
 && a2enmod rewrite \
 && echo "ServerName localhost" >> /etc/apache2/apache2.conf \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy Composer dari stage composer
COPY --from=composer /usr/bin/composer /usr/bin/composer

WORKDIR /var/www

# Salin source code dari src/ ke dalam container
COPY src/ /var/www/

RUN mkdir -p storage bootstrap/cache public \
    && chown -R www-data:www-data storage bootstrap/cache public 2>/dev/null || true \
    && chmod -R 775 storage bootstrap/cache public 2>/dev/null || true

EXPOSE 80
CMD ["apache2-foreground"]