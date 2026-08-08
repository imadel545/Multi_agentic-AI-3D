FROM node:24-alpine@sha256:d32cdf619f63fe0471182d08996dd516c6275bb5fd31ae06e55a570bd9e1ad43 AS build

WORKDIR /build
COPY apps/frontend/package.json apps/frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY apps/frontend/ ./
RUN npm run build

FROM nginx:1.29-alpine@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de

COPY --from=build /build/dist /usr/share/nginx/html
COPY infra/docker/nginx.conf /etc/nginx/nginx.conf
COPY --chmod=755 infra/docker/frontend-healthcheck.sh /usr/local/bin/frontend-healthcheck

RUN mkdir -p \
        /tmp/nginx/client_temp \
        /tmp/nginx/proxy_temp \
        /tmp/nginx/fastcgi_temp \
        /tmp/nginx/uwsgi_temp \
        /tmp/nginx/scgi_temp \
    && chown -R 101:101 /tmp/nginx /usr/share/nginx/html

USER 101:101

EXPOSE 8080

ENTRYPOINT ["nginx", "-g", "daemon off;"]
