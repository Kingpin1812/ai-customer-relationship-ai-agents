FROM node:24.13-slim AS build
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /srv/frontend
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Standalone output is what lets the final image run without node_modules; see next.config.ts.
RUN BUILD_STANDALONE=1 npm run build

FROM node:24.13-slim
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
WORKDIR /srv/frontend
COPY --from=build --chown=node:node /srv/frontend/.next/standalone ./
COPY --from=build --chown=node:node /srv/frontend/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
