#!/usr/bin/python3
# -*- coding: utf-8 -*-

# MIT License
#
# Copyright (c) 2021 Stefan von Cavallar
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import time
import atexit
import argparse
import logging
from prometheus_client import start_http_server
from prometheus_client.core import InfoMetricFamily, GaugeMetricFamily, REGISTRY
from jtop import jtop, JtopException

# Configurazione logging
logging.basicConfig(level=logging.INFO)
logging.info('Server started on port %s', 9401)

# Classe per raccogliere le metriche
class CustomCollector(object):
    def __init__(self):
        atexit.register(self.cleanup)
        self._jetson = jtop()
        try:
            self._jetson.start()
        except JtopException as e:
            logging.error("Error starting jtop: %s", e)
            raise

    def cleanup(self):
        print("Closing jetson-stats connection...")
        self._jetson.close()

    def collect(self):
        if self._jetson.ok():
            # Board info
            i = InfoMetricFamily('jetson_info_board', 'Board sys info', labels=['board_info'])
            i.add_metric(['info'], {
                'machine': self._jetson.board['platform']['Machine'], 
                'jetpack': self._jetson.board['hardware']['Jetpack'], 
                'l4t': self._jetson.board['hardware']['L4T']
            })
            yield i

            # Board hardware info
            i = InfoMetricFamily('jetson_info_hardware', 'Board hardware info', labels=['board_hw'])
            i.add_metric(['hardware'], {
                'model': self._jetson.board['hardware'].get('Model', 'unknown'),
                'part_number': self._jetson.board['hardware'].get('699-level Part Number', 'unknown'),
                'p_number': self._jetson.board['hardware'].get('P-Number', 'unknown'),
                'board_ids': self._jetson.board['hardware'].get('BoardIDs', 'unknown'),
                'module': self._jetson.board['hardware'].get('Module', 'unknown'),
                'soc': self._jetson.board['hardware'].get('SoC', 'unknown'),
                'cuda_arch_bin': self._jetson.board['hardware'].get('CUDA Arch BIN', 'unknown'),
                'codename': self._jetson.board['hardware'].get('Codename', 'unknown'),
                'serial_number': self._jetson.board['hardware'].get('Serial Number', 'unknown')
            })
            yield i

            # NV power mode
            i = InfoMetricFamily('jetson_nvpmode', 'NV power mode', labels=['nvpmode'])
            i.add_metric(['mode'], {'mode': self._jetson.nvpmodel.name})
            yield i

            # System uptime
            g = GaugeMetricFamily('jetson_uptime', 'System uptime', labels=['uptime'])
            days = self._jetson.uptime.days
            seconds = self._jetson.uptime.seconds
            hours = seconds // 3600
            minutes = (seconds // 60) % 60
            g.add_metric(['days'], days)
            g.add_metric(['hours'], hours)
            g.add_metric(['minutes'], minutes)
            yield g

            # CPU usage
            g = GaugeMetricFamily('jetson_usage_cpu', 'CPU % schedutil', labels=['cpu'])
            for cpu in self._jetson.cpu:
                g.add_metric([cpu], self._jetson.cpu[cpu]['val'])
            yield g

            # GPU usage
            g = GaugeMetricFamily('jetson_usage_gpu', 'GPU % schedutil', labels=['gpu'])
            g.add_metric(['val'], self._jetson.gpu['val'])
            yield g

            # RAM usage
            g = GaugeMetricFamily('jetson_usage_ram', 'Memory usage', labels=['ram'])
            g.add_metric(['shared'], self._jetson.ram['shared'])
            yield g

            # Disk usage
            g = GaugeMetricFamily('jetson_usage_disk', 'Disk space usage', labels=['disk'])
            g.add_metric(['used'], self._jetson.disk['used'])
            g.add_metric(['total'], self._jetson.disk['total'])
            g.add_metric(['available'], self._jetson.disk['available'])
            g.add_metric(['available_no_root'], self._jetson.disk['available_no_root'])
            yield g

            # Fan usage
            g = GaugeMetricFamily('jetson_usage_fan', 'Fan usage', labels=['fan'])
            g.add_metric(['speed'], self._jetson.fan['speed'])
            yield g

            # Power usage
            g = GaugeMetricFamily('jetson_usage_power', 'Power usage', labels=['power'])
            for component in self._jetson.power[1]:
                g.add_metric([component], self._jetson.power[1][component]['cur'])
            yield g

            # Sensor temperatures
            g = GaugeMetricFamily('jetson_temperatures', 'Sensor temperatures', labels=['temperature'])
            for temp_sensor in self._jetson.temperature:
                g.add_metric([temp_sensor], self._jetson.temperature[temp_sensor])
            yield g

# Funzione principale
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=9401, help='Metrics collector port number')

    args = parser.parse_args()

    # Avvia il server HTTP per esporre le metriche
    start_http_server(args.port)
    REGISTRY.register(CustomCollector())
    
    # Mantieni in esecuzione il programma per raccogliere metriche
    while True:
        time.sleep(1)

