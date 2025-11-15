import os
import json
import subprocess
import requests
from datetime import datetime
import psutil
import time
from pathlib import Path
import platform
import sys
import shutil
from dotenv import load_dotenv
import sqlite3
import gzip
import threading
from flask import Flask, render_template, jsonify
from config import CONFIG
from webService import *

# Cargar variables de entorno
load_dotenv()

class HardwareMonitor:
    def __init__(self):
        self.log_file = Path(CONFIG["log_file"])
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.running = True
        
        # Inicializar base de datos
        self.db_file = Path(CONFIG["db_file"])
        self.init_database()
    
    def init_database(self):
        """Crea la base de datos SQLite con todas las métricas"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT UNIQUE,
                
                cpu_percent REAL,
                cpu_freq REAL,
                cpu_count INTEGER,
                cpu_temp REAL,
                
                memory_percent REAL,
                memory_used_gb REAL,
                memory_total_gb REAL,
                memory_available_gb REAL,
                
                disk_percent REAL,
                disk_used_gb REAL,
                disk_total_gb REAL,
                disk_free_gb REAL,
                disk_read_count INTEGER,
                disk_write_count INTEGER,
                disk_read_bytes REAL,
                disk_write_bytes REAL,
                
                temp_cpu REAL,
                temp_gpu REAL,
                temp_ssd REAL,
                temp_hdd REAL,
                temperatures TEXT,
                
                network_bytes_sent REAL,
                network_bytes_recv REAL,
                network_packets_sent INTEGER,
                network_packets_recv INTEGER,
                
                processes_count INTEGER,
                threads_count INTEGER
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON metrics(timestamp)')
        conn.commit()
        conn.close()
    
    def get_disk_info(self):
        """Obtiene información detallada de discos"""
        try:
            disk_usage = psutil.disk_usage('/')
            disk_io = psutil.disk_io_counters()
            
            return {
                "percent": disk_usage.percent,
                "used_gb": disk_usage.used / (1024**3),
                "total_gb": disk_usage.total / (1024**3),
                "free_gb": disk_usage.free / (1024**3),
                "read_count": disk_io.read_count if disk_io else 0,
                "write_count": disk_io.write_count if disk_io else 0,
                "read_bytes": (disk_io.read_bytes / (1024**3)) if disk_io else 0,
                "write_bytes": (disk_io.write_bytes / (1024**3)) if disk_io else 0
            }
        except Exception as e:
            if CONFIG["debug"]:
                print(f"[ERROR] Disk info: {e}")
            return {}
    
    def get_all_temperatures(self):
        """Obtiene temperaturas de TODOS los componentes críticos"""
        temps = {
            "cpu": None,
            "gpu": None,
            "ssd": None,
            "hdd": None,
            "all": {}
        }
        
        try:
            temps_data = psutil.sensors_temperatures()
            
            if not temps_data:
                return temps
            
            # Mapeo de nombres comunes de sensores
            for sensor_name, sensor_list in temps_data.items():
                sensor_name_lower = sensor_name.lower()
                
                if sensor_list:
                    # Tomar la primera temperatura de cada sensor
                    current_temp = sensor_list[0].current
                    temps["all"][sensor_name] = current_temp
                    
                    # Clasificar por tipo
                    if any(x in sensor_name_lower for x in ["coretemp", "package", "cpu"]):
                        if temps["cpu"] is None:
                            temps["cpu"] = current_temp
                        else:
                            temps["cpu"] = max(temps["cpu"], current_temp)
                    
                    elif any(x in sensor_name_lower for x in ["nvidia", "amd", "radeon", "gpu"]):
                        if temps["gpu"] is None:
                            temps["gpu"] = current_temp
                        else:
                            temps["gpu"] = max(temps["gpu"], current_temp)
                    
                    elif any(x in sensor_name_lower for x in ["nvme", "ssd", "m.2"]):
                        if temps["ssd"] is None:
                            temps["ssd"] = current_temp
                        else:
                            temps["ssd"] = max(temps["ssd"], current_temp)
                    
                    elif any(x in sensor_name_lower for x in ["ata", "hdd", "sata"]):
                        if temps["hdd"] is None:
                            temps["hdd"] = current_temp
                        else:
                            temps["hdd"] = max(temps["hdd"], current_temp)
        
        except Exception as e:
            if CONFIG["debug"]:
                print(f"[ERROR] Temperature sensors: {e}")
        
        return temps
    
    def get_network_info(self):
        """Obtiene información de red"""
        try:
            net_io = psutil.net_io_counters()
            return {
                "bytes_sent": net_io.bytes_sent / (1024**3),
                "bytes_recv": net_io.bytes_recv / (1024**3),
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv
            }
        except Exception as e:
            if CONFIG["debug"]:
                print(f"[ERROR] Network info: {e}")
            return {}
    
    def get_process_info(self):
        """Obtiene información de procesos"""
        try:
            return {
                "processes": len(psutil.pids()),
                "threads": threading.active_count()
            }
        except Exception as e:
            if CONFIG["debug"]:
                print(f"[ERROR] Process info: {e}")
            return {}
    
    def get_hardware_metrics(self):
        """Obtiene métricas completas del hardware"""
        
        # CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_freq = psutil.cpu_freq().current if psutil.cpu_freq() else 0
        cpu_count = psutil.cpu_count()
        
        # Memoria
        mem = psutil.virtual_memory()
        
        # Temperaturas
        temps = self.get_all_temperatures()
        
        # Disco
        disk_info = self.get_disk_info()
        
        # Red
        net_info = self.get_network_info()
        
        # Procesos
        proc_info = self.get_process_info()
        
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "cpu": {
                "percent": cpu_percent,
                "freq": cpu_freq,
                "count": cpu_count,
                "temp": temps["cpu"]
            },
            "memory": {
                "percent": mem.percent,
                "used_gb": mem.used / (1024**3),
                "total_gb": mem.total / (1024**3),
                "available_gb": mem.available / (1024**3)
            },
            "disk": disk_info,
            "temperatures": temps,
            "network": net_info,
            "processes": proc_info
        }
        
        return metrics
    
    def write_metrics_to_db(self):
        """Guarda métricas completas en SQLite"""
        metrics = self.get_hardware_metrics()
        
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO metrics (
                    timestamp, cpu_percent, cpu_freq, cpu_count, cpu_temp,
                    memory_percent, memory_used_gb, memory_total_gb, memory_available_gb,
                    disk_percent, disk_used_gb, disk_total_gb, disk_free_gb,
                    disk_read_count, disk_write_count, disk_read_bytes, disk_write_bytes,
                    temp_cpu, temp_gpu, temp_ssd, temp_hdd, temperatures,
                    network_bytes_sent, network_bytes_recv, network_packets_sent, network_packets_recv,
                    processes_count, threads_count
                ) VALUES (?, ?, ?, ?, ?,
                          ?, ?, ?, ?,
                          ?, ?, ?, ?,
                          ?, ?, ?, ?,
                          ?, ?, ?, ?, ?,
                          ?, ?, ?, ?,
                          ?, ?)
            ''', (
                metrics["timestamp"],
                metrics["cpu"]["percent"],
                metrics["cpu"]["freq"],
                metrics["cpu"]["count"],
                metrics["cpu"]["temp"],
                metrics["memory"]["percent"],
                metrics["memory"]["used_gb"],
                metrics["memory"]["total_gb"],
                metrics["memory"]["available_gb"],
                metrics["disk"]["percent"],
                metrics["disk"]["used_gb"],
                metrics["disk"]["total_gb"],
                metrics["disk"]["free_gb"],
                metrics["disk"]["read_count"],
                metrics["disk"]["write_count"],
                metrics["disk"]["read_bytes"],
                metrics["disk"]["write_bytes"],
                metrics["temperatures"]["cpu"],
                metrics["temperatures"]["gpu"],
                metrics["temperatures"]["ssd"],
                metrics["temperatures"]["hdd"],
                json.dumps(metrics["temperatures"]["all"]),
                metrics["network"]["bytes_sent"],
                metrics["network"]["bytes_recv"],
                metrics["network"]["packets_sent"],
                metrics["network"]["packets_recv"],
                metrics["processes"]["processes"],
                metrics["processes"]["threads"]
            ))
            
            conn.commit()
            conn.close()
            
            if CONFIG["debug"]:
                print(f"[DB] Métrica guardada: {metrics['timestamp']}")
    
        except sqlite3.IntegrityError:
            if CONFIG["debug"]:
                print(f"[DB] Registro duplicado (mismo timestamp)")
    
        except Exception as e:
            if CONFIG["debug"]:
                print(f"[DB] Error guardando métricas: {e}")
    
    def write_metrics(self):
        """Escribe las métricas (DB + Comprimido)"""
        self.write_metrics_to_db()
        
        if CONFIG["log_compression"]:
            self.write_metrics_compressed()
    
    def write_metrics_compressed(self):
        """Escribe métricas en JSON comprimido"""
        metrics = self.get_hardware_metrics()
        json_data = json.dumps(metrics, ensure_ascii=False)
        
        log_gz = self.log_file.with_suffix('.jsonl.gz')
        
        try:
            with gzip.open(log_gz, 'at', encoding='utf-8') as f:
                f.write(json_data + '\n')
        except Exception as e:
            if CONFIG["debug"]:
                print(f"[ERROR] Compresión: {e}")

class GitUpdater:
    def __init__(self, repo):
        self.repo = repo
        self.current_version = self.get_local_version()
        self.system = platform.system()
        self.executable_name = self.get_executable_name()
        self.current_executable = self.get_current_executable_path()
        self.update_log = Path("logs/update_log.txt")
        self.update_log.parent.mkdir(parents=True, exist_ok=True)
        self.temp_update_file = f"{self.executable_name}.update"
        
        self.headers = {
            'User-Agent': 'hardwareMonitor-updater/1.0',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        if CONFIG["github_token"]:
            self.headers['Authorization'] = f'token {CONFIG["github_token"]}'
            self.debug_print(f"✓ Token de GitHub configurado (últimos 4 caracteres: ...{CONFIG['github_token'][-4:]})")
        else:
            self.debug_print("⚠️  Sin token: rate limit de 60 requests/hora")
        
        self.check_pending_update()
        
        self.debug_print(f"Sistema: {self.system}")
        self.debug_print(f"Versión local: {self.current_version}")
        self.debug_print(f"Ejecutable actual: {self.current_executable}")
        self.debug_print(f"Nombre esperado: {self.executable_name}")
    
    def check_pending_update(self):
        """Verifica si hay una actualización pendiente desde la ejecución anterior"""
        if os.path.exists(self.temp_update_file):
            self.debug_print(f"✓ Actualización pendiente encontrada: {self.temp_update_file}")
            try:
                backup_name = f"{self.executable_name}.backup"
                if os.path.exists(self.executable_name):
                    shutil.move(self.executable_name, backup_name)
                    self.debug_print(f"💾 Backup del ejecutable anterior: {backup_name}")
                
                shutil.move(self.temp_update_file, self.executable_name)
                
                if self.system in ["Linux", "Darwin"]:
                    os.chmod(self.executable_name, 0o755)
                
                self.debug_print(f"✅ Actualización aplicada exitosamente")
            except Exception as e:
                self.debug_print(f"❌ Error al aplicar actualización: {e}")
    
    def debug_print(self, msg):
        """Imprime mensaje de debug tanto en consola como en archivo"""
        if CONFIG["debug"]:
            print(f"[DEBUG] {msg}")
        with open(self.update_log, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    
    def test_connection(self):
        """Prueba la conexión a GitHub"""
        self.debug_print("Probando conexión a GitHub...")
        try:
            response = requests.get(
                "https://api.github.com",
                headers=self.headers,
                timeout=10
            )
            self.debug_print(f"✓ Conexión exitosa (código: {response.status_code})")
            return True
        except Exception as e:
            self.debug_print(f"✗ Error de conexión: {e}")
            return False
    
    def get_executable_name(self):
        """Determina el nombre del ejecutable según el SO"""
        if self.system == "Windows":
            return "hardwareMonitor-Windows.exe"
        elif self.system == "Darwin":
            return "hardwareMonitor-macOS"
        else:
            return "hardwareMonitor-Linux"
    
    def get_current_executable_path(self):
        """Obtiene el path del ejecutable actual"""
        if getattr(sys, 'frozen', False):
            return sys.executable
        return os.path.abspath(sys.argv[0])
    
    def get_local_version(self):
        """Obtiene la versión local del ejecutable"""
        try:
            with open("version.txt", "r") as f:
                version = f.read().strip()
                return version if version else "0.0.0"
        except:
            return "0.0.0"
    
    def get_latest_release(self):
        """Obtiene la última release de GitHub"""
        self.debug_print(f"Obteniendo última release de {self.repo}...")
        
        try:
            if not self.test_connection():
                self.debug_print("No hay conexión a Internet")
                return None
            
            url = f"https://api.github.com/repos/{self.repo}/releases/latest"
            self.debug_print(f"URL: {url}")
            
            response = requests.get(
                url,
                headers=self.headers,
                timeout=15
            )
            
            self.debug_print(f"Respuesta HTTP: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                version = data['tag_name'].lstrip('v')
                self.debug_print(f"✓ Última versión en GitHub: {version}")
                return version
            
            elif response.status_code == 404:
                self.debug_print("✗ No hay releases en GitHub")
                return None
            
            elif response.status_code == 403:
                self.debug_print(f"✗ Error 403 Forbidden")
                self.debug_print(f"Respuesta: {response.text}")
                return None
            
            else:
                self.debug_print(f"✗ Error HTTP: {response.status_code}")
                self.debug_print(f"Respuesta: {response.text}")
                return None
            
        except Exception as e:
            self.debug_print(f"✗ Error: {type(e).__name__}: {e}")
            return None
    
    def check_for_updates(self):
        """Verifica si hay actualizaciones disponibles"""
        self.debug_print("="*60)
        self.debug_print("INICIANDO VERIFICACIÓN DE ACTUALIZACIONES")
        self.debug_print("="*60)
        
        latest = self.get_latest_release()
        
        if latest is None:
            self.debug_print("✗ No se pudo obtener la versión remota")
            return False
        
        self.debug_print(f"Comparando: local={self.current_version} vs remota={latest}")
        
        if latest != self.current_version:
            self.debug_print(f"✓ Actualización disponible: {self.current_version} → {latest}")
            self.download_update(latest)
            return True
        else:
            self.debug_print(f"✓ Ya está en la última versión ({self.current_version})")
            return False
    
    def download_update(self, version):
        """Descarga la actualización"""
        try:
            url = f"https://github.com/{self.repo}/releases/download/v{version}/{self.executable_name}"
            self.debug_print(f"📥 Descargando desde: {url}")
            
            response = requests.get(
                url,
                headers=self.headers,
                timeout=CONFIG["update_timeout"],
                stream=True
            )
            self.debug_print(f"Respuesta: {response.status_code}")
            
            if response.status_code == 200:
                with open(self.temp_update_file, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                self.debug_print(f"✅ Descarga completada en: {self.temp_update_file}")
                self.debug_print(f"⚠️  La actualización se aplicará al reiniciar el programa")
                
                with open("version.txt", "w") as f:
                    f.write(version)
                
                self.current_version = version
                
            else:
                self.debug_print(f"❌ Error: código HTTP {response.status_code}")
                
        except Exception as e:
            self.debug_print(f"❌ Error al descargar: {type(e).__name__}: {e}")

def main():
    """Función principal"""
    monitor = HardwareMonitor()
    updater = GitUpdater(CONFIG["github_repo"])
    
    print("\n" + "="*60)
    print("🖥️  Hardware Monitor iniciado")
    print("="*60)
    print(f"Sistema: {updater.system}")
    print(f"Versión: {updater.current_version}")
    print(f"BD SQLite: {monitor.db_file}")
    if CONFIG["log_compression"]:
        print(f"JSON comprimido: {monitor.log_file.with_suffix('.jsonl.gz')}")
    print(f"🌐 Dashboard: http://{CONFIG['flask_host']}:{CONFIG['flask_port']}")
    print("="*60 + "\n")
    
    # Iniciar Flask en thread separado
    flask_thread = threading.Thread(
        target=run_flask_server,
        args=(CONFIG["db_file"],),
        daemon=True
    )
    flask_thread.start()
    print(f"✅ Servidor Flask iniciado en puerto {CONFIG['flask_port']}\n")
    
    last_update_check = 0
    
    try:
        while monitor.running:
            monitor.write_metrics()
            print(f"[METRIC] {datetime.now().strftime('%H:%M:%S')} - Métrica registrada")
            
            current_time = time.time()
            if current_time - last_update_check > CONFIG["check_updates_interval"]:
                print("\n[UPDATE] Verificando actualizaciones...")
                updater.check_for_updates()
                get_db_size_stats()
                print()
                last_update_check = current_time
            
            time.sleep(CONFIG["metrics_interval"])
    
    except KeyboardInterrupt:
        print("\n✓ Monitor detenido.")
        get_db_size_stats()
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()