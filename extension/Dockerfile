FROM node:20-alpine
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY tsconfig.json .vscodeignore ./
COPY src ./src/
RUN npx tsc
RUN npx vsce package --no-dependencies
CMD ["sh", "-c", "cp *.vsix /out/ 2>/dev/null || true; ls -la *.vsix"]
