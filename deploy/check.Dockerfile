FROM node:24.21.0-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV NODE_OPTIONS=--max-old-space-size=1536
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
CMD ["sh", "-c", "npm test && mkdir -p /artifacts && npm pack --ignore-scripts --pack-destination /artifacts --json > /artifacts/pack.json && node scripts/check-package.mjs /artifacts/*.tgz && cd /artifacts && sha256sum *.tgz > SHA256SUMS"]
