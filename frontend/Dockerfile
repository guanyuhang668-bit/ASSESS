FROM node:20-alpine

WORKDIR /app

# 装依赖（利用缓存）
COPY package.json ./
RUN npm install --silent

# 源码
COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
