# jetson-exporter

 exporter for nvidia jetson with promehteus and grafana link , exporter is connected to the port 9401
 
## QuickStart
### kubernetes

```bash
kubectl apply  -f  ./deploy.yaml
```

## Prometheus

you can connect to prometheus in port 30090, i use the istallation of prometheus in this guide:
https://docs.nvidia.com/datacenter/cloud-native/gpu-telemetry/latest/kube-prometheus.html
but the additionalconfigscrape is this for my exporter:
    additionalScrapeConfigs: 
    - job_name: 'jetson-exporter'
      scrape_interval: 5s
      kubernetes_sd_configs:
        - namespaces:
            names:
              - monitoring
          role: pod
      metrics_path: /metrics
      scheme: http
      relabel_configs:
    # Seleziona solo i pod con etichetta app=jetson-exporter
      - action: keep
        source_labels:
          - __meta_kubernetes_pod_label_app
        regex: jetson-exporter
    # Imposta il target per il job per utilizzare la porta corretta (9401)
      - action: replace
        source_labels:
          - __meta_kubernetes_pod_name
        target_label: __param_target
        replacement: "9401"
         # Imposta il nome dell'istanza come indirizzo del pod
      - action: replace
        source_labels:
          - __meta_kubernetes_pod_ip
          - __param_target
        target_label: instance
        separator: ":"
            # Imposta l'indirizzo correttamente, includendo la porta 9401
      - action: replace
        source_labels:
          - __meta_kubernetes_pod_ip
        target_label: __address__
        replacement: "${1}:9401"


## Grafana

