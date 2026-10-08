FROM python:3.12-slim
WORKDIR /app
COPY core.py provider.py server.py dashboard.html config.json ./
RUN useradd --create-home app && mkdir /app/data && chown -R app:app /app
USER app
ENV BIND_HOST=0.0.0.0 DATA_DIR=/app/data
EXPOSE 8080
CMD ["python", "server.py"]
