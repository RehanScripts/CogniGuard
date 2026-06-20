# Single-stage dev-server image (this is a demo, not a production build) -- matches
# the "one-shot docker compose up --build" framing used throughout this repo. Build
# context is the repo root (see docker-compose.yml) so behavior-sdk/ is reachable: it's
# a `file:../behavior-sdk` dependency that ships compiled dist/, not source, so it must
# be built before `npm install` resolves it.
FROM node:20-slim

WORKDIR /behavior-sdk
COPY behavior-sdk/package*.json ./
RUN npm install
COPY behavior-sdk/ ./
RUN npm run build

WORKDIR /app
COPY web-app/package*.json ./
RUN npm install
COPY web-app/ ./

EXPOSE 5173
CMD ["npm", "run", "dev"]
