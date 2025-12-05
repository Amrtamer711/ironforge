FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

COPY . .

RUN mkdir -p uploads data

ENV NODE_ENV=production

EXPOSE 3005

CMD ["node", "server.js"]
