#!/bin/sh
set -eu
: "${CCK_SERVER_NAME:?Set CCK_SERVER_NAME}"
: "${CCK_PUBLIC_ORIGIN:?Set CCK_PUBLIC_ORIGIN}"
case "$CCK_SERVER_NAME" in ''|*[!A-Za-z0-9.-]*) echo "Invalid server name" >&2; exit 1;; esac
case "$CCK_PUBLIC_ORIGIN" in
  "https://$CCK_SERVER_NAME") ;;
  "https://$CCK_SERVER_NAME":*)
    port="${CCK_PUBLIC_ORIGIN##*:}"
    case "$port" in ''|*[!0-9]*) echo "Invalid HTTPS origin" >&2; exit 1;; esac
    [ "$port" -ge 1 ] && [ "$port" -le 65535 ] || exit 1;;
  *) echo "HTTPS origin must match server name" >&2; exit 1;;
esac
export CCK_API_UPSTREAM="${CCK_API_UPSTREAM:-api:8000}"
export CCK_RESOLVER="${CCK_RESOLVER:-127.0.0.11}"
export CCK_TLS_CERTIFICATE="${CCK_TLS_CERTIFICATE:-/run/secrets/tls_certificate}"
export CCK_TLS_KEY="${CCK_TLS_KEY:-/run/secrets/tls_private_key}"
export CCK_STATIC_ROOT="${CCK_STATIC_ROOT:-/usr/share/nginx/html}"
export CCK_HEADERS_FILE="${CCK_HEADERS_FILE:-/etc/cck/security-headers.conf}"
export CCK_MIME_TYPES_FILE="${CCK_MIME_TYPES_FILE:-/etc/nginx/mime.types}"
export CCK_HTTP_LISTEN="${CCK_HTTP_LISTEN:-8080}"
export CCK_HTTPS_LISTEN="${CCK_HTTPS_LISTEN:-8443}"
envsubst '${CCK_SERVER_NAME} ${CCK_PUBLIC_ORIGIN} ${CCK_API_UPSTREAM} ${CCK_RESOLVER} ${CCK_TLS_CERTIFICATE} ${CCK_TLS_KEY} ${CCK_STATIC_ROOT} ${CCK_HEADERS_FILE} ${CCK_MIME_TYPES_FILE} ${CCK_HTTP_LISTEN} ${CCK_HTTPS_LISTEN}' \
  < "${CCK_TEMPLATE:-/etc/cck/nginx.conf.template}" > /tmp/cck-nginx.conf
exec nginx -c /tmp/cck-nginx.conf -g 'daemon off;'
