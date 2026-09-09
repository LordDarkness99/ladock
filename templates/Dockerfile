FROM php:8.4-fpm

# System deps + PHP extensions yang dibutuhkan Laravel
RUN apt-get update && apt-get install -y \
        git curl zip unzip \
        libpng-dev libonig-dev libxml2-dev libzip-dev \
        libicu-dev \ 
        libpq-dev \
        default-mysql-client \
    && docker-php-ext-install pdo_mysql mbstring exif pcntl bcmath gd zip intl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Composer
COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

WORKDIR /var/www

COPY . /var/www

# --- FIX 3: Berikan izin yang benar untuk semua folder yang diperlukan ---
RUN mkdir -p storage bootstrap/cache \
    && chown -R www-data:www-data storage bootstrap/cache \
    && chown -R www-data:www-data public \
    && chmod -R 755 storage bootstrap/cache public

EXPOSE 9000
CMD ["php-fpm"]