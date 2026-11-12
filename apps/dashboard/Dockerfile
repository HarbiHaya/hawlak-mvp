FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
COPY tsconfig.base.json ./tsconfig.base.json
COPY apps/dashboard/package.json ./apps/dashboard/package.json
COPY packages/contracts/package.json ./packages/contracts/package.json
RUN npm ci

COPY apps/dashboard ./apps/dashboard
COPY packages/contracts ./packages/contracts
COPY fixtures ./fixtures

ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build -w packages/contracts \
    && npm run build -w apps/dashboard

FROM nginx:1.29-alpine

COPY deploy/nginx-dashboard.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/dashboard/dist /usr/share/nginx/html

EXPOSE 80
