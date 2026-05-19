# 🚀 Быстрый старт

## Установка за 5 минут

### Шаг 1: Установите зависимости
```bash
pip install -r requirements.txt
```

### Шаг 2: Настройте TLauncher
1. Убедитесь, что TLauncher установлен
2. Запустите TLauncher один раз вручную
3. Установите Forge 1.21.1 через список версий

### Шаг 3: Установите мод
1. Скопируйте `worldsync-1.21.1-1.0.jar` в `.minecraft/mods/`
2. Если папки `mods` нет — создайте её

### Шаг 4: Запустите программу
```bash
python src/main.py
```

### Шаг 5: Нажмите "Играть"! ✨

Программа автоматически:
- Запустит TLauncher
- Выберет Forge 1.21.1
- Нажмёт "Играть"
- Загрузит мир
- Откроет LAN (для хоста) / подключится (для клиента)

---

## Если что-то пошло не так

### TLauncher не найден?
Создайте файл `tlauncher_path.txt` с полным путём:
```
C:\Users\ВашеИмя\AppData\Roaming\.tlauncher\TLauncher.exe
```

### Автоматизация не работает?
Установите pyautogui:
```bash
pip install pyautogui
```

Или запустите TLauncher вручную перед нажатием "Играть".

### Ошибка "Radmin VPN adapter not found"?
1. Проверьте, что Radmin VPN запущен
2. Подключитесь к комнате
3. Убедитесь, что ваш IP начинается с `26.`

---

## Полная документация

- [docs/README.md](docs/README.md) — полное руководство
- [docs/AUTOMATION.md](docs/AUTOMATION.md) — настройка автоматизации
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — решение проблем
