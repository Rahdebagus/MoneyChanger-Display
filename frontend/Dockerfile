# Frontend: build the SPA, serve it with nginx.

FROM node:22-alpine AS build
WORKDIR /app

# The API base URL is baked in at build time by Vite, so it is a build arg.
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY package.json package-lock.json ./
# npm ci, not npm install: a clean install must match the lockfile exactly.
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
