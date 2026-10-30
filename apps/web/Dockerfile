FROM node:22-slim
WORKDIR /srv
COPY package*.json ./
RUN npm ci
COPY . .
ARG REDEEM_API_URL=http://api:8000
ENV REDEEM_API_URL=$REDEEM_API_URL
RUN npx next build
EXPOSE 3000
CMD ["npx", "next", "start", "-p", "3000"]
