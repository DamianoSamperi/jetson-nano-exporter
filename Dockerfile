FROM arm64v8/python:3.6-slim
# Imposta la directory di lavoro
WORKDIR /app
# Copia il tuo script Python nel contenitore
COPY jetson-exporter.py /app/jetson_exporter.py

RUN apt-get update \
    && apt-get install -y bash \
    && pip install jetson-stats prometheus-client \
    && rm -rf /var/lib/apt/lists/*  # Pulisce i dati di apt-get per ridurre l'immagine

# Espone la porta su cui il server HTTP sarà in ascolto
EXPOSE 9401

# Esegui lo script Python all'avvio del contenitore
CMD ["python", "jetson_exporter.py", "--port", "9401"]
