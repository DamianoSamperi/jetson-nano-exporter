from prometheus_client import REGISTRY, start_http_server
from prometheus_client.core import GaugeMetricFamily, InfoMetricFamily
import time
import atexit
import argparse
import logging
from jtop import jtop, JtopException
import os


# Configurazione logging
logging.basicConfig(level=logging.INFO)
logging.info('Server started on port %s', 9401)


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
        if not self._jetson or not self._jetson.ok():
            logging.warning("Lost connection to jtop, attempting to restart...")
            self.cleanup()
            self.restart_jtop()
            if not self._jetson or not self._jetson.ok():
                logging.error("Failed to restart jtop, skipping metric collection")
                return

        try:
            # Board info
            board_info = InfoMetricFamily('jetson_info_board', 'Board sys info', labels=['board_info'])
            board_info.add_metric(['info'], {
                'machine': self._jetson.board['platform'].get('Machine', 'Unknown'),
                'jetpack': self._jetson.board['hardware'].get('Jetpack', 'Unknown'),
                'l4t': self._jetson.board['hardware'].get('L4T', 'Unknown')
            })
            yield board_info

            # GPU Usage (percentuale) -- USATA dallo scheduler e da Locust
            gpu_usage_percentage_gauge = GaugeMetricFamily(
                "gpu_usage_percentage", "GPU Utilization Percentage from Jetson Stats",
                labels=["nvidia_gpu"],
            )
            for gpu_name in self._jetson.gpu.keys():
                load = self._jetson.gpu[gpu_name]["status"]["load"]
                gpu_usage_percentage_gauge.add_metric([gpu_name], value=load)
            yield gpu_usage_percentage_gauge

            # Power consumption (INA) -- per la sezione energia
            power_gauge = GaugeMetricFamily(
                "power_consumption", "Power consumption from Jetson Stats",
                labels=["rail"], unit="mW"
            )
            try:
                power_data = self._jetson.power
                tot = power_data.get("tot", {})
                if "power" in tot:
                    power_gauge.add_metric(["total"], value=tot["power"])
                for rail_name, rail_data in power_data.get("rail", {}).items():
                    if isinstance(rail_data, dict) and rail_data.get("online") and "power" in rail_data:
                        power_gauge.add_metric([rail_name], value=rail_data["power"])
            except Exception as e:
                logging.warning(f"Power data not available: {e}")
            yield power_gauge

            # CPU % (opzionale - tieni se ti serve come contorno)
            cpu_usage_percentage_gauge = GaugeMetricFamily(
                "cpu_usage_percentage", "CPU Usage Percentage from Jetson Stats", labels=["core"]
            )
            for core_number, core_data in enumerate(self._jetson.cpu.get('cpu', [])):
                idle = core_data.get("idle", 0); user = core_data.get("user", 0); system = core_data.get("system", 0)
                total = idle + user + system
                cpu_usage_percentage_gauge.add_metric([str(core_number)], value=(100 - idle/total*100) if total > 0 else 0)
            yield cpu_usage_percentage_gauge

            # RAM % (opzionale)
            ram_usage_percentage_gauge = GaugeMetricFamily(
                "ram_usage_percentage", "RAM Usage Percentage from Jetson Stats", labels=["statistic"]
            )
            tot_ram = self._jetson.memory["RAM"]["tot"]; used_ram = self._jetson.memory["RAM"]["used"]
            if tot_ram > 0:
                ram_usage_percentage_gauge.add_metric(["used"], value=used_ram/tot_ram*100)
            yield ram_usage_percentage_gauge

            # Temperature (opzionale)
            temperature_gauge = GaugeMetricFamily(
                "temperature", "Temperature from Jetson Stats", labels=["machine_part"], unit="C"
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
