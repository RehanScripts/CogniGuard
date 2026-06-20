# Single-stage dev-server image -- no behavior-sdk dependency (this app never
# captures telemetry), so unlike web-app/Dockerfile this needs no cross-package build
# step and can use the plain repo-relative service directory as its build context.
FROM node:20-slim

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .

EXPOSE 5174
CMD ["npm", "run", "dev"]
