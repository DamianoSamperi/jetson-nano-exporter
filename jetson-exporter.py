from prometheus_client import REGISTRY, start_http_server
from prometheus_client.core import GaugeMetricFamily, InfoMetricFamily
import time
import atexit
import argparse
import logging
from jtop import jtop, JtopException

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logging.info('Server started on port %s', 9401)

# Classe per raccogliere le metriche
class CustomCollector(object):
    def __init__(self, update_period=1):
        atexit.register(self.cleanup)
        self._jetson = jtop()  # Inizializza l'oggetto jtop
        self._update_period = update_period
        try:
            self._jetson.start()  # Avvia il monitoraggio jtop
        except JtopException as e:
            logging.error("Error starting jtop: %s", e)
            raise

    def cleanup(self):
        print("Closing jetson-stats connection...")
        self._jetson.close()  # Chiude la connessione a jtop

    def collect(self):
        if self._jetson.ok():  # Verifica se la connessione è ok
            # Esempio di informazioni sulla board
            board_info = InfoMetricFamily(
                'jetson_info_board',
                'Board sys info',
                labels=['board_info']
            )
            board_info.add_metric(['info'], {
                'machine': self._jetson.board['platform']['Machine'],
                'jetpack': self._jetson.board['hardware']['Jetpack'],
                'l4t': self._jetson.board['hardware']['L4T']
            })
            yield board_info

            # Esempio di informazioni sul processore CPU
            cpu_gauge = GaugeMetricFamily(
                name="cpu_usage",
                documentation="CPU Usage from Jetson Stats",
                labels=["core", "statistic"],
                unit="Hz"
            )
            for core_number, core_data in enumerate(self._jetson.cpu['cpu']):
                cpu_gauge.add_metric([str(core_number), "freq"], value=core_data["freq"]["cur"])
                cpu_gauge.add_metric([str(core_number), "min_freq"], value=core_data["freq"]["min"])
                cpu_gauge.add_metric([str(core_number), "max_freq"], value=core_data["freq"]["max"])
                cpu_gauge.add_metric([str(core_number), "val"], value=core_data["idle"])
            yield cpu_gauge

            # Esempio di utilizzo della GPU
            gpu_gauge = GaugeMetricFamily(
                name="gpu_utilization_percentage",
                documentation="GPU Usage from Jetson Stats",
                labels=["statistic", "nvidia_gpu"],
                unit="Hz"
            )
            for gpu_name in self._jetson.gpu.keys():
                gpu_gauge.add_metric([gpu_name, "freq"], value=self._jetson.gpu[gpu_name]["freq"]["cur"])
                gpu_gauge.add_metric([gpu_name, "min_freq"], value=self._jetson.gpu[gpu_name]["freq"]["min"])
                gpu_gauge.add_metric([gpu_name, "max_freq"], value=self._jetson.gpu[gpu_name]["freq"]["max"])
            yield gpu_gauge

            # Esempio di utilizzo della RAM
            ram_gauge = GaugeMetricFamily(
                name="ram_usage",
                documentation="RAM Usage from Jetson Stats",
                labels=["statistic"],
                unit="kB"
            )
            ram_gauge.add_metric(["total"], value=self._jetson.jtop_stats["mem"]["RAM"]["tot"])
            ram_gauge.add_metric(["used"], value=self._jetson.jtop_stats["mem"]["RAM"]["used"])
            ram_gauge.add_metric(["buffers"], value=self._jetson.jtop_stats["mem"]["RAM"]["buffers"])
            ram_gauge.add_metric(["cached"], value=self._jetson.jtop_stats["mem"]["RAM"]["cached"])
            ram_gauge.add_metric(["lfb"], value=self._jetson.jtop_stats["mem"]["RAM"]["lfb"])
            ram_gauge.add_metric(["free"], value=self._jetson.jtop_stats["mem"]["RAM"]["free"])
            yield ram_gauge

            # Esempio di utilizzo dello Swap
            swap_gauge = GaugeMetricFamily(
                name="swap_usage",
                documentation="Swap Usage from Jetson Stats",
                labels=["statistic"],
                unit="kB"
            )
            swap_gauge.add_metric(["total"], value=self._jetson.jtop_stats["mem"]["SWAP"]["tot"])
            swap_gauge.add_metric(["used"], value=self._jetson.jtop_stats["mem"]["SWAP"]["used"])
            swap_gauge.add_metric(["cached"], value=self._jetson.jtop_stats["mem"]["SWAP"]["cached"])
            yield swap_gauge

            # Esempio di utilizzo del Disco
            disk_gauge = GaugeMetricFamily(
                name="disk_usage",
                documentation="Disk Usage from Jetson Stats",
                labels=["mountpoint", "statistic"],
                unit="GB"
            )
            for mountpoint, disk_info in self._jetson.disk.items():
                if mountpoint == "/":
                    disk_gauge.add_metric(["total"], value=disk_info["total"])
                    disk_gauge.add_metric(["used"], value=disk_info["used"])
                    disk_gauge.add_metric(["free"], value=disk_info["free"])
                    disk_gauge.add_metric(["percent"], value=disk_info["percent"])
            yield disk_gauge

            # Uptime
            uptime_gauge = GaugeMetricFamily(
                name="uptime",
                documentation="Uptime from Jetson Stats",
                labels=["statistic"],
                unit="s"
            )
            uptime_gauge.add_metric(["alive"], value=self._jetson.jtop_stats["upt"].total_seconds())
            yield uptime_gauge

            # Temperature
            temperature_gauge = GaugeMetricFamily(
                name="temperature",
                documentation="Temperature from Jetson Stats",
                labels=["statistic", "machine_part"],
                unit="C"
            )
            for part, temp in self._jetson.jtop_stats['tmp'].items():
                temperature_gauge.add_metric([part], value=temp["temp"])
            yield temperature_gauge

# Funzione principale
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=9401, help='Metrics collector port number')

    args = parser.parse_args()

    # Avvia il server HTTP per esporre le metriche
    start_http_server(args.port)
    REGISTRY.register(CustomCollector(update_period=1))
    
    # Mantieni in esecuzione il programma per raccogliere metriche
    while True:
        time.sleep(1)
