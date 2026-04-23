# Minimal RFC 3161 TSA stub for local dev. Returns HTTP 200 on any path so
# Story 1.13's TSA client scaffolding can hit a reachable endpoint without
# the real FreeTSA service. Story 1.13 replaces this with a real RFC 3161
# client + fallback chain.
FROM nginx:1.27-alpine

COPY default.conf /etc/nginx/conf.d/default.conf
