from flask import Flask, render_template, jsonify
import sqlite3
from pathlib import Path
import json
from dotenv import load_dotenv
from config import CONFIG

class DashboardServer:
    def __init__(self, db_file):
        self.db_file = db_file
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        self.setup_routes()
    
    def get_db_connection(self):
        """Crea una conexión a la BD"""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        return conn
    
    def setup_routes(self):
        """Configura las rutas de Flask"""
        
        @self.app.route('/')
        def index():
            return render_template('dashboard.html')
        
        @self.app.route('/api/latest')
        def api_latest():
            """Últimas 100 métricas para gráficos"""
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT timestamp, cpu_percent, memory_percent, disk_percent,
                       COALESCE(temp_cpu, 0) as temp_cpu, 
                       COALESCE(temp_gpu, 0) as temp_gpu, 
                       COALESCE(temp_ssd, 0) as temp_ssd, 
                       COALESCE(temp_hdd, 0) as temp_hdd,
                       network_bytes_sent, network_bytes_recv, processes_count
                FROM metrics 
                ORDER BY timestamp DESC 
                LIMIT 100
            ''')
            
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                return jsonify([])
            
            data = [dict(row) for row in reversed(rows)]
            return jsonify(data)
        
        @self.app.route('/api/stats')
        def api_stats():
            """Estadísticas generales"""
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_registros,
                    AVG(cpu_percent) as cpu_promedio,
                    MAX(cpu_percent) as cpu_maximo,
                    AVG(memory_percent) as ram_promedio,
                    MAX(memory_percent) as ram_maximo,
                    AVG(disk_percent) as disk_promedio,
                    MAX(disk_percent) as disk_maximo,
                    AVG(temp_cpu) as temp_cpu_avg,
                    MAX(temp_cpu) as temp_cpu_max,
                    AVG(temp_gpu) as temp_gpu_avg,
                    AVG(temp_ssd) as temp_ssd_avg,
                    AVG(temp_hdd) as temp_hdd_avg,
                    MIN(timestamp) as desde
                FROM metrics
            ''')
            
            row = cursor.fetchone()
            conn.close()
            
            return jsonify(dict(row))
        
        @self.app.route('/api/db-size')
        def api_db_size():
            """Tamaño de la BD"""
            db_path = Path(self.db_file)
            if db_path.exists():
                size_mb = db_path.stat().st_size / (1024**2)
                
                conn = self.get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM metrics")
                rows = cursor.fetchone()[0]
                conn.close()
                
                bytes_per_row = (size_mb * 1024 * 1024) / rows if rows > 0 else 0
                
                return jsonify({
                    "size_mb": round(size_mb, 2),
                    "registros": rows,
                    "bytes_per_row": round(bytes_per_row, 1)
                })
            return jsonify({"error": "BD no encontrada"}), 404
        
        @self.app.route('/api/temperatures')
        def api_temperatures():
            """Temperaturas completas del último registro"""
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT timestamp, temp_cpu, temp_gpu, temp_ssd, temp_hdd, temperatures
                FROM metrics ORDER BY timestamp DESC LIMIT 1
            ''')
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return jsonify({"error": "No hay datos"}), 404
            
            temps = {
                "timestamp": row['timestamp'],
                "cpu": row['temp_cpu'],
                "gpu": row['temp_gpu'],
                "ssd": row['temp_ssd'],
                "hdd": row['temp_hdd'],
                "all_sensors": json.loads(row['temperatures']) if row['temperatures'] else {}
            }
            
            return jsonify(temps)
    
    def run(self, host, port, debug):
        """Inicia el servidor Flask"""
        self.app.run(host=host, port=port, debug=debug, use_reloader=False)

def run_flask_server(db_file):
    """Ejecuta Flask en un thread separado"""
    dashboard = DashboardServer(db_file)
    dashboard.run(
        host=CONFIG["flask_host"],
        port=CONFIG["flask_port"],
        debug=CONFIG["flask_debug"]
    )

def get_db_size_stats():
    """Muestra estadísticas de tamaño de la base de datos"""
    db_file = Path(CONFIG["db_file"])
    if db_file.exists():
        size_mb = db_file.stat().st_size / (1024**2)
        
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM metrics")
        rows = cursor.fetchone()[0]
        conn.close()
        
        bytes_per_row = (size_mb * 1024 * 1024) / rows if rows > 0 else 0
        
        print(f"\n📊 Estadísticas de BD:")
        print(f"   Tamaño: {size_mb:.2f} MB")
        print(f"   Registros: {rows:,}")
        print(f"   Bytes/registro: {bytes_per_row:.1f}")
        print(f"   Proyección/mes: {(size_mb/24):.2f} MB (si corre 24h)\n")