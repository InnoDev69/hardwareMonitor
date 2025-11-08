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

# Configuración
CONFIG = {
    "github_repo": "InnoDev69/hardwareMonitor",
    "log_file": "logs/hardware_metrics.txt",
    "check_updates_interval": 3600,  # Cada hora (en segundos)
    "metrics_interval": 5,  # Cada 5 segundos
    "update_timeout": 15  # Timeout más largo para descargas
}

class HardwareMonitor:
    def __init__(self):
        self.log_file = Path(CONFIG["log_file"])
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.running = True
        
    def get_hardware_metrics(self):
        """Obtiene métricas esenciales del hardware"""
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "cpu": {
                "percent": psutil.cpu_percent(interval=1),
                "count": psutil.cpu_count(),
                "freq": psutil.cpu_freq().current if psutil.cpu_freq() else 0
            },
            "memory": {
                "percent": psutil.virtual_memory().percent,
                "used_gb": psutil.virtual_memory().used / (1024**3),
                "total_gb": psutil.virtual_memory().total / (1024**3)
            },
            "disk": {
                "percent": psutil.disk_usage('/').percent,
                "used_gb": psutil.disk_usage('/').used / (1024**3),
                "total_gb": psutil.disk_usage('/').total / (1024**3)
            },
            "temperature": self.get_temperature()
        }
        return metrics
    
    def get_temperature(self):
        """Obtiene temperatura si está disponible"""
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    if entries:
                        return {name: entries[0].current}
            return {}
        except:
            return {}
    
    def write_metrics(self):
        """Escribe las métricas en el archivo txt"""
        metrics = self.get_hardware_metrics()
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"Timestamp: {metrics['timestamp']}\n")
            f.write(f"CPU: {metrics['cpu']['percent']}% | {metrics['cpu']['freq']:.0f} MHz\n")
            f.write(f"RAM: {metrics['memory']['percent']}% ({metrics['memory']['used_gb']:.2f}GB / {metrics['memory']['total_gb']:.2f}GB)\n")
            f.write(f"DISK: {metrics['disk']['percent']}% ({metrics['disk']['used_gb']:.2f}GB / {metrics['disk']['total_gb']:.2f}GB)\n")
            if metrics['temperature']:
                f.write(f"Temperatura: {metrics['temperature']}\n")

class GitUpdater:
    def __init__(self, repo):
        self.repo = repo
        self.current_version = self.get_local_version()
        self.system = platform.system()
        self.executable_name = self.get_executable_name()
    
    def get_executable_name(self):
        """Determina el nombre del ejecutable según el SO"""
        if self.system == "Windows":
            return "hardwareMonitor.exe"
        elif self.system == "Darwin":  # macOS
            return "hardwareMonitor"
        else:  # Linux
            return "hardwareMonitor"
    
    def get_local_version(self):
        """Obtiene la versión local del ejecutable"""
        try:
            with open("version.txt", "r") as f:
                return f.read().strip()
        except:
            return "0.0.0"
    
    def get_latest_release(self):
        """Obtiene la última release de GitHub"""
        try:
            url = f"https://api.github.com/repos/{self.repo}/releases/latest"
            response = requests.get(url, timeout=15)  # Aumentado a 15 segundos
            if response.status_code == 200:
                data = response.json()
                return data['tag_name'].lstrip('v')
            return None
        except requests.exceptions.Timeout:
            print("Timeout al conectar a GitHub API. Reintentando en la próxima verificación...")
            return None
        except requests.exceptions.ConnectionError:
            print("Error de conexión a GitHub. Verifica tu conexión a Internet.")
            return None
        except Exception as e:
            print(f"Error al verificar updates: {e}")
            return None
    
    def check_for_updates(self):
        """Verifica si hay actualizaciones disponibles"""
        latest = self.get_latest_release()
        if latest and latest != self.current_version:
            print(f"Actualización disponible: {self.current_version} -> {latest}")
            self.download_update(latest)
            return True
        return False
    
    def download_update(self, version):
        """Descarga la actualización"""
        try:
            url = f"https://github.com/{self.repo}/releases/download/v{version}/{self.executable_name}"
            print(f"Descargando actualización desde {url}...")
            response = requests.get(url, timeout=CONFIG["update_timeout"])
            if response.status_code == 200:
                backup_name = f"{self.executable_name}.backup"
                
                # Hacer backup del ejecutable actual
                if os.path.exists(self.executable_name):
                    os.rename(self.executable_name, backup_name)
                
                # Guardar nueva versión
                with open(self.executable_name, "wb") as f:
                    f.write(response.content)
                
                # Hacer ejecutable en Linux/macOS
                if self.system in ["Linux", "Darwin"]:
                    os.chmod(self.executable_name, 0o755)
                
                print("Descarga completada. Reinicia el programa para aplicar la actualización.")
                with open("version.txt", "w") as f:
                    f.write(version)
                self.current_version = version
            else:
                print(f"Error al descargar: código HTTP {response.status_code}")
        except Exception as e:
            print(f"Error al descargar: {e}")

def main():
    """Función principal"""
    monitor = HardwareMonitor()
    updater = GitUpdater(CONFIG["github_repo"])
    
    print("Hardware Monitor iniciado...")
    print(f"Sistema: {updater.system}")
    print(f"Versión actual: {updater.current_version}")
    print(f"Guardando métricas en: {monitor.log_file}")
    
    last_update_check = 0
    
    try:
        while monitor.running:
            # Escribir métricas
            monitor.write_metrics()
            print(f"Métrica registrada - {datetime.now().strftime('%H:%M:%S')}")
            
            # Verificar actualizaciones
            current_time = time.time()
            if current_time - last_update_check > CONFIG["check_updates_interval"]:
                print("Verificando actualizaciones...")
                updater.check_for_updates()
                last_update_check = current_time
            
            time.sleep(CONFIG["metrics_interval"])
    
    except KeyboardInterrupt:
        print("\nMonitor detenido.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()