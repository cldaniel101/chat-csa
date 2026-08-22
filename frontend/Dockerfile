FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
ARG VITE_INGESTER_URL=http://localhost:8001
ARG VITE_CONSUMER_URL=http://localhost:8002
ENV VITE_INGESTER_URL=$VITE_INGESTER_URL
ENV VITE_CONSUMER_URL=$VITE_CONSUMER_URL
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
