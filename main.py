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

# Cargar variables de entorno
load_dotenv()

# Configuración
CONFIG = {
    "github_repo": "InnoDev69/hardwareMonitor",
    "log_file": "logs/hardware_metrics.txt",
    "check_updates_interval": 3600,
    "metrics_interval": 5,
    "update_timeout": 30,
    "debug": True,
    "github_token": os.getenv("GITHUB_TOKEN", "")
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
        self.current_executable = self.get_current_executable_path()
        self.update_log = Path("logs/update_log.txt")
        self.update_log.parent.mkdir(parents=True, exist_ok=True)
        self.temp_update_file = f"{self.executable_name}.update"  # ← AGREGAR
        
        # Headers CON TOKEN
        self.headers = {
            'User-Agent': 'hardwareMonitor-updater/1.0',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # Agregar token si existe
        if CONFIG["github_token"]:
            self.headers['Authorization'] = f'token {CONFIG["github_token"]}'
            self.debug_print(f"✓ Token de GitHub configurado (últimos 4 caracteres: ...{CONFIG['github_token'][-4:]})")
        else:
            self.debug_print("⚠️  Sin token: rate limit de 60 requests/hora")
        
        # Verificar si hay actualización pendiente
        self.check_pending_update()  # ← AGREGAR
        
        self.debug_print(f"Sistema: {self.system}")
        self.debug_print(f"Versión local: {self.current_version}")
        self.debug_print(f"Ejecutable actual: {self.current_executable}")
        self.debug_print(f"Nombre esperado: {self.executable_name}")
    
    def check_pending_update(self):  # ← NUEVA FUNCIÓN
        """Verifica si hay una actualización pendiente desde la ejecución anterior"""
        if os.path.exists(self.temp_update_file):
            self.debug_print(f"✓ Actualización pendiente encontrada: {self.temp_update_file}")
            try:
                # Hacer backup del actual
                backup_name = f"{self.executable_name}.backup"
                if os.path.exists(self.executable_name):
                    shutil.move(self.executable_name, backup_name)
                    self.debug_print(f"💾 Backup del ejecutable anterior: {backup_name}")
                
                # Reemplazar con la nueva versión
                shutil.move(self.temp_update_file, self.executable_name)
                
                # Hacer ejecutable en Linux/macOS
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
                # Descargar a archivo temporal
                with open(self.temp_update_file, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                self.debug_print(f"✅ Descarga completada en: {self.temp_update_file}")
                self.debug_print(f"⚠️  La actualización se aplicará al reiniciar el programa")
                
                # Actualizar version.txt para la próxima ejecución
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
    print(f"Guardando en: {monitor.log_file}")
    print(f"Log de updates: {updater.update_log}")
    print("="*60 + "\n")
    
    last_update_check = 0
    
    try:
        while monitor.running:
            monitor.write_metrics()
            print(f"[METRIC] {datetime.now().strftime('%H:%M:%S')} - Métrica registrada")
            
            current_time = time.time()
            if current_time - last_update_check > CONFIG["check_updates_interval"]:
                print("\n[UPDATE] Verificando actualizaciones...")
                updater.check_for_updates()
                print()
                last_update_check = current_time
            
            time.sleep(CONFIG["metrics_interval"])
    
    except KeyboardInterrupt:
        print("\n✓ Monitor detenido.")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()