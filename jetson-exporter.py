from prometheus_client import REGISTRY, start_http_server
from prometheus_client.core import GaugeMetricFamily, InfoMetricFamily
import time
import atexit
import argparse
import logging
from jtop import jtop, JtopException
import os
import threading
import re
from kubernetes import client, config


# Configurazione logging
logging.basicConfig(level=logging.INFO)
logging.info('Server started on port %s', 9401)

class PodNameCache:
    def __init__(self, refresh_interval=15):
        self.cache = {}
        self.lock = threading.Lock()
        self.refresh_interval = refresh_interval
        self._update_cache()

    def _update_cache(self):
        try:
            # Usa il contesto in-cluster; in caso di errore, usa il kubeconfig locale
            config.load_incluster_config()
        except Exception as e:
            logging.error("Errore nel load dell'in-cluster config: %s", e)
            config.load_kube_config()
        v1 = client.CoreV1Api()
        try:
            ret = v1.list_pod_for_all_namespaces(watch=False)
            with self.lock:
                for pod in ret.items:
                    self.cache[pod.metadata.uid] = pod.metadata.name
        except Exception as e:
            logging.error("Errore durante la lista dei pod: %s", e)
        # Pianifica l'aggiornamento successivo
        threading.Timer(self.refresh_interval, self._update_cache).start()

    def get_pod_name(self, uid):
        with self.lock:
            pod_name = self.cache.get(uid, "unknown")
            return pod_name
        
# Istanza globale della cache
pod_cache = PodNameCache(refresh_interval=15)

def get_pod_from_pid(pid):
    """
    Legge /proc/[pid]/cgroup per estrarre l'UID del pod e restituisce il nome del pod usando la cache.
    Se non trova informazioni, restituisce "unknown".
    """
    try:
        with open(f"/proc/{pid}/cgroup", "r") as f:
            lines = f.readlines()
            for line in lines:
                if "kubepods" in line:
                    # Cerca il pattern: una stringa che inizia con 'pod' seguita da caratteri e terminante con '.slice'
                    m = re.search(r'(pod[0-9a-fA-F\-_]+)\.slice', line)
                    if m:
                        pod_fragment = m.group(1)  # Es. "pod0721dadd_0b17_4ddb_9b81_310a9ba90dac"
                        uid_fragment = pod_fragment[3:]  # Rimuove il prefisso "pod"
                        pod_uid = uid_fragment.replace("_", "-")  # Converti in formato UID standard
                        pod_name = pod_cache.get_pod_name(pod_uid)
                        return pod_name
    except Exception as e:
        logging.debug("Errore nella lettura di /proc/%s/cgroup: %s", pid, e)
    return "unknown"

class CustomCollector(object):
    def __init__(self, update_period=1):
        atexit.register(self.cleanup)
        self._update_period = update_period
        self._jetson = None
        self._start_jetson()

    def _start_jetson(self):
        """Avvia jtop con gestione degli errori."""
        try:
            self._jetson = jtop()
            self._jetson.start()
            logging.info("jtop started successfully")
        except JtopException as e:
            logging.error("Error starting jtop: %s", e)
            self._jetson = None
    def restart_jtop():
        try:
            subprocess.run(["systemctl", "restart", "jtop.service"], check=True)
            logging.info("jtop restarted successfully!")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to restart jtop: {e}")

    def cleanup(self):
        if self._jetson:
            logging.info("Closing jetson-stats connection...")
            self._jetson.close()

    def collect(self):
        """Raccoglie le metriche di sistema."""
        if not self._jetson or not self._jetson.ok():
            logging.warning("Lost connection to jtop, attempting to restart...")
            self.cleanup()
            self.restart_jtop()
            if not self._jetson or not self._jetson.ok():
                logging.error("Failed to restart jtop, skipping metric collection")
                return  

        try:
            # Board info
            board_info = InfoMetricFamily(
                'jetson_info_board', 'Board sys info', labels=['board_info']
            )
            board_info.add_metric(['info'], {
                'machine': self._jetson.board['platform'].get('Machine', 'Unknown'),
                'jetpack': self._jetson.board['hardware'].get('Jetpack', 'Unknown'),
                'l4t': self._jetson.board['hardware'].get('L4T', 'Unknown')
            })
            yield board_info

            # CPU Usage (absolute)
            cpu_gauge = GaugeMetricFamily(
                "cpu_usage", "CPU Usage from Jetson Stats",
                labels=["core", "statistic"], unit="Hz"
            )
            #for core_number, core_data in enumerate(self._jetson.cpu.get('cpu', [])):
            #    cpu_gauge.add_metric([str(core_number), "freq"], value=core_data["freq"]["cur"])
            #    cpu_gauge.add_metric([str(core_number), "min_freq"], value=core_data["freq"]["min"])
            #    cpu_gauge.add_metric([str(core_number), "max_freq"], value=core_data["freq"]["max"])
            #    cpu_gauge.add_metric([str(core_number), "val"], value=core_data["idle"])
            #yield cpu_gauge
            for core_number, core_data in enumerate(self._jetson.cpu.get('cpu', [])):
                freq_data = core_data.get("freq", {})
                idle = core_data.get("idle", 0)
                if freq_data:
                    cpu_gauge.add_metric([str(core_number), "freq"], value=freq_data.get("cur", 0))
                    cpu_gauge.add_metric([str(core_number), "min_freq"], value=freq_data.get("min", 0))
                    cpu_gauge.add_metric([str(core_number), "max_freq"], value=freq_data.get("max", 0))
                cpu_gauge.add_metric([str(core_number), "val"], value=idle)
            yield cpu_gauge
            # CPU Usage (percentuale)
            cpu_usage_percentage_gauge = GaugeMetricFamily(
                "cpu_usage_percentage", "CPU Usage Percentage from Jetson Stats",
                labels=["core"],
            )
            #for core_number, core_data in enumerate(self._jetson.cpu.get('cpu', [])):
            #    idle_time = core_data["idle"]
            #    total_time = core_data["idle"] + core_data["user"] + core_data["system"]
            #    cpu_usage_percentage = 100 - (idle_time / total_time * 100)
            #    cpu_usage_percentage_gauge.add_metric([str(core_number)], value=cpu_usage_percentage)
            #yield cpu_usage_percentage_gauge
            for core_number, core_data in enumerate(self._jetson.cpu.get('cpu', [])):
                idle_time = core_data.get("idle", 0)
                user_time = core_data.get("user", 0)
                system_time = core_data.get("system", 0)
                total_time = idle_time + user_time + system_time
                if total_time > 0:
                    cpu_usage_percentage = 100 - (idle_time / total_time * 100)
                else:
                    cpu_usage_percentage = 0
                cpu_usage_percentage_gauge.add_metric([str(core_number)], value=cpu_usage_percentage)
            yield cpu_usage_percentage_gauge

            # GPU Usage
            gpu_gauge = GaugeMetricFamily(
                "gpu_utilization", "GPU Usage from Jetson Stats",
                labels=["statistic", "nvidia_gpu"], unit="Hz"
            )
            #for gpu_name in self._jetson.gpu.keys():
            #    gpu_gauge.add_metric([gpu_name, "freq"], value=self._jetson.gpu[gpu_name]["freq"]["cur"])
            #    gpu_gauge.add_metric([gpu_name, "min_freq"], value=self._jetson.gpu[gpu_name]["freq"]["min"])
            #    gpu_gauge.add_metric([gpu_name, "max_freq"], value=self._jetson.gpu[gpu_name]["freq"]["max"])
            #yield gpu_gauge
            for gpu_name, gpu_data in self._jetson.gpu.items():
                freq_data = gpu_data.get("freq", {})
                if freq_data:
                    gpu_gauge.add_metric([gpu_name, "freq"], value=freq_data.get("cur", 0))
                    gpu_gauge.add_metric([gpu_name, "min_freq"], value=freq_data.get("min", 0))
                    gpu_gauge.add_metric([gpu_name, "max_freq"], value=freq_data.get("max", 0))
                else:
                    logging.warning(f"'freq' data missing for GPU {gpu_name}")
            yield gpu_gauge
            # GPU Usage (percentuale)
            gpu_usage_percentage_gauge = GaugeMetricFamily(
                "gpu_usage_percentage", "GPU Utilization Percentage from Jetson Stats",
                labels=["nvidia_gpu"],
            )
            for gpu_name in self._jetson.gpu.keys():
                gpu_usage_percentage = self._jetson.gpu[gpu_name]["status"]["load"]
                gpu_usage_percentage_gauge.add_metric([gpu_name], value=gpu_usage_percentage)            
            yield gpu_usage_percentage_gauge

            # Uso GPU aggregato per pod
            gpu_pod_usage_gauge = GaugeMetricFamily(
                name="gpu_pod_usage",
                documentation="Estimated GPU computation usage per pod aggregated from GPU processes",
                labels=["pod"]
            )

            # Memoria GPU utilizzata per pod
            gpu_pod_memory_usage_gauge = GaugeMetricFamily(
                name="gpu_pod_memory_usage",
                documentation="GPU memory usage per pod in MB",
                labels=["pod"]
            )

            pod_gpu_usage = {}
            pod_gpu_memory_usage = {}
            total_gpu_mem_used = sum(proc[8] for proc in self._jetson.processes if proc[8] > 0)

            if total_gpu_mem_used > 0:
                for proc in self._jetson.processes:
                    pid = str(proc[0])
                    gpu_mem_used = proc[8]  # Memoria GPU usata dal processo
                    pod = get_pod_from_pid(pid)

                    if pod == "unknown":
                        continue

                    total_gpu_usage = next(
                        (self._jetson.gpu[gpu]["status"]["load"] for gpu in self._jetson.gpu.keys()),
                        0
                    )

                    # Calcolo uso GPU per pod
                    process_gpu_usage = (gpu_mem_used / total_gpu_mem_used) * total_gpu_usage
                    pod_gpu_usage[pod] = pod_gpu_usage.get(pod, 0) + process_gpu_usage

                    # Memoria GPU totale utilizzata dal pod
                    pod_gpu_memory_usage[pod] = pod_gpu_memory_usage.get(pod, 0) + gpu_mem_used

                    logging.debug(f"Pod: {pod}, GPU Memory Used: {gpu_mem_used} MB")

            # Aggiunta delle metriche alla raccolta
            for pod, usage in pod_gpu_usage.items():
                gpu_pod_usage_gauge.add_metric([pod], value=usage)

            for pod, mem_usage in pod_gpu_memory_usage.items():
                gpu_pod_memory_usage_gauge.add_metric([pod], value=mem_usage)

            # Restituisce entrambe le metriche
            yield gpu_pod_usage_gauge
            yield gpu_pod_memory_usage_gauge

            # RAM Usage
            ram_gauge = GaugeMetricFamily(
                "ram_usage", "RAM Usage from Jetson Stats",
                labels=["statistic"], unit="kB"
            )
            for key in ["tot", "used", "buffers", "cached", "lfb", "free"]:
                ram_gauge.add_metric([key], value=self._jetson.memory["RAM"].get(key, 0))
            yield ram_gauge

            # RAM Usage (percentuale)
            ram_usage_percentage_gauge = GaugeMetricFamily(
                "ram_usage_percentage", "RAM Usage Percentage from Jetson Stats",
                labels=["statistic"]
            )
            total_ram = self._jetson.memory["RAM"]["tot"]
            used_ram = self._jetson.memory["RAM"]["used"]
            if total_ram > 0:
                ram_usage_percentage = (used_ram / total_ram) * 100
                ram_usage_percentage_gauge.add_metric(["used"], value=ram_usage_percentage)
            yield ram_usage_percentage_gauge

            # Swap Usage
            swap_gauge = GaugeMetricFamily(
                "swap_usage", "Swap Usage from Jetson Stats",
                labels=["statistic"], unit="kB"
            )
            for key in ["tot", "used", "cached"]:
                swap_gauge.add_metric([key], value=self._jetson.memory["SWAP"].get(key, 0))
            yield swap_gauge


            # Disk Usage
            #disk_gauge = GaugeMetricFamily(
            #    "disk_usage", "Disk Usage from Jetson Stats",
            #    labels=["statistic"], unit="GB"
            #)
            # Aggiungi solo le chiavi numeriche (ignora 'unit' che è una stringa)
            #for key in ["total", "used", "available", "available_no_root"]:
            #    value = self._jetson.disk.get(key)
            #    if value is not None:
            #        disk_gauge.add_metric([key], value=value)

            #yield disk_gauge


            # Uptime
            uptime_gauge = GaugeMetricFamily(
                "uptime", "Uptime from Jetson Stats",
                labels=["statistic"], unit="s"
            )
            uptime_gauge.add_metric(["alive"], value=self._jetson.uptime.total_seconds())
            yield uptime_gauge

            # Temperature
            temperature_gauge = GaugeMetricFamily(
                "temperature", "Temperature from Jetson Stats",
                labels=["machine_part"], unit="C"
            )
            for part, temp in self._jetson.temperature.items():
                temperature_gauge.add_metric([part], value=temp["temp"])
            yield temperature_gauge

        except Exception as e:
            logging.error("Error while collecting metrics: %s", e)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=9401, help='Metrics collector port number')
    args = parser.parse_args()

    start_http_server(args.port)
    REGISTRY.register(CustomCollector(update_period=1))

    while True:
        time.sleep(1)
