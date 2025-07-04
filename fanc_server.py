import subprocess
import threading
import time
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

class TemperatureMonitor:
    def __init__(self):
        self.current_max_temp = 0
        self.lock = threading.Lock()
        self.update_interval = 3  # между обновлениями
        self.running = True

    def get_temperature(self):
        """Получаем текущую максимальную температуру"""
        with self.lock:
            return self.current_max_temp

    def update_temperature(self):
        """Обновление показателей температуры в фоновом режиме"""
        while self.running:
            try:
                result = subprocess.run(
                    ['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader'],
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                    timeout=2
                )
                if result.returncode == 0:
                    temps = [int(t.strip()) for t in result.stdout.splitlines() if t.strip().isdigit()]
                    if temps:
                        new_temp = max(temps)
                        with self.lock:
                            self.current_max_temp = new_temp
                    else:
                        # Нет валидных температур - устанавливаем аварийное значение
                        with self.lock:
                            self.current_max_temp = 100
                        time.sleep(self.update_interval * 3)
                        continue
                else:
                    # Ошибка выполнения команды - устанавливаем аварийное значение
                    with self.lock:
                        self.current_max_temp = 100
                    time.sleep(self.update_interval * 3)
                    continue
            except Exception:
                # Исключение при выполнении - устанавливаем аварийное значение
                with self.lock:
                    self.current_max_temp = 100
                time.sleep(self.update_interval * 2)
                continue
            
            time.sleep(self.update_interval)

    def start(self):
        """Запуск фонового потока"""
        self.thread = threading.Thread(target=self.update_temperature, daemon=True)
        self.thread.start()

    def stop(self):
        """Остановка фонового потока"""
        self.running = False
        self.thread.join(timeout=1)

class TemperatureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(str(monitor.get_temperature()).encode())
        else:
            self.send_error(404)
            
    def log_message(self, format, *args):
        """Отключаем стандартное логирование запросов"""
        return

if __name__ == '__main__':
    monitor = TemperatureMonitor()
    monitor.start()
    
    server = HTTPServer(('', 17006), TemperatureHandler)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        monitor.stop()
        server.server_close()