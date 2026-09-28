# ============================================================
# Apache Gateway Dockerfile — Microservice Reverse Proxy
# Image ringan berbasis httpd:2.4-alpine (~50MB)
# ============================================================
FROM httpd:2.4-alpine

# Copy konfigurasi utama httpd yang mengaktifkan extra includes
COPY httpd.conf /usr/local/apache2/conf/httpd.conf

# Buat folder htdocs (untuk dashboard HTML)
RUN mkdir -p /usr/local/apache2/htdocs

EXPOSE 80
