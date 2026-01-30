import pynvml
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
                device_count = pynvml.nvmlDeviceGetCount()  # Получаем количество GPU
                temps = []
                for i in range(device_count):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)  # Получаем дескриптор GPU по индексу
                    temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)  # Получаем температуру
                    temps.append(temp)

                if temps:
                    new_temp = max(temps)
                    with self.lock:
                        self.current_max_temp = new_temp
                else:
                    # Не нашли ни одного GPU с валидной температурой
                    with self.lock:
                        self.current_max_temp = 100  # Аварийное значение
                    time.sleep(self.update_interval * 3)
                    continue

            except pynvml.NVMLError as e:
                # Ошибка NVML (например, GPU был отключен или драйвер сломался)
                print(f"Ошибка NVML при обновлении температуры: {e}")
                with self.lock:
                    self.current_max_temp = 100  # Аварийное значение
                time.sleep(self.update_interval * 3)
                continue
            except Exception as e:
                # Другие неожиданные ошибки
                print(f"Неожиданная ошибка при обновлении температуры: {e}")
                with self.lock:
                    self.current_max_temp = 100  # Аварийное значение
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
    try:
        pynvml.nvmlInit()  # Инициализируем NVML перед запуском монитора
    except pynvml.NVMLError as e:
        print(f"Не удалось инициализировать NVML: {e}")
        print("Убедитесь, что драйверы NVIDIA установлены и работают.")
        exit(1)  # Завершаем работу, если не можем получить доступ к GPU

    monitor = TemperatureMonitor()
    monitor.start()

    server = HTTPServer(('', 17006), TemperatureHandler)
    print("Сервер мониторинга температуры запущен на порту 17006")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановка...")
    finally:
        monitor.stop()
        server.server_close()
        pynvml.nvmlShutdown()
        print("Сервер остановлен")
