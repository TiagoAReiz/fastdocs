FROM node:20-alpine
RUN npm install -g azurite
EXPOSE 10000 10001 10002
CMD ["azurite", "--blobHost", "0.0.0.0", "--queueHost", "0.0.0.0", "--tableHost", "0.0.0.0", "--skipApiVersionCheck", "--location", "/data"]
