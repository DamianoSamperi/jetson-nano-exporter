FROM python:3.6-slim
# Imposta la directory di lavoro
WORKDIR /app
# Copia il tuo script Python nel contenitore
COPY jetson_exporter.py /app/jetson_exporter.py

RUN apk update \
    && apk --no-cache add bash \
    && pip install jetson-stats prometheus-client \
    && rm -rf /var/cache/apk/*
# Espone la porta su cui il server HTTP sarà in ascolto
EXPOSE 9401

# Esegui lo script Python all'avvio del contenitore
CMD ["python", "jetson_exporter.py", "--port", "9401"]
