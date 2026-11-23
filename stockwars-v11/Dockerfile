FROM node:20-slim AS web
WORKDIR /w
COPY webapp/package.json .
RUN npm install
COPY webapp .
RUN npm run build

FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=web /w/dist /srv/webapp/dist
CMD ["python", "-m", "app.run"]
