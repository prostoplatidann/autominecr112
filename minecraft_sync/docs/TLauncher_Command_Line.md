# Инструкция по запуску TLauncher из командной строки

## Автоматический запуск с параметрами

TLauncher поддерживает следующие параметры командной строки:

```bash
TLauncher.exe -login <username> -start -version <версия>
```

### Примеры:

**Запуск Forge 1.21.1:**
```bash
"C:\Users\Pixel\AppData\Roaming\.minecraft\TLauncher.exe" -login Qtter -start -version forge-1.21.1
```

**Запуск Fabric 1.17.1:**
```bash
"C:\Users\Pixel\AppData\Roaming\.minecraft\TLauncher.exe" -login Qtter -start -version "Fabric 1.17.1"
```

**Запуск без имени пользователя (выбор в интерфейсе):**
```bash
"C:\Users\Pixel\AppData\Roaming\.minecraft\TLauncher.exe" -start -version forge-1.21.1
```

## Важные примечания

1. **Кавычки**: Если путь содержит пробелы, обязательно используйте кавычки
2. **Версия**: Должна точно совпадать с названием в списке версий TLauncher
3. **-login**: Опционально, можно не указывать для выбора вручную
4. **-start**: Автоматически запускает игру после выбора версии
5. **-version**: Выбирает указанную версию из списка

## Проверка доступных версий

Откройте TLauncher и посмотрите точные названия версий в выпадающем списке:
- `forge-1.21.1` - Forge для 1.21.1
- `Fabric 1.17.1` - Fabric для 1.17.1
- `OptiFine_1.20.4_HD_U_I6` - OptiFine и т.д.

## Решение проблем

### TLauncher не реагирует на параметры
1. Убедитесь, что используется последняя версия TLauncher
2. Попробуйте запустить от имени администратора
3. Проверьте, что TLauncher не запущен в фоновом режиме

### Неправильная версия
Используйте точное название версии как оно отображается в TLauncher:
```bash
# Для версий с пробелами используйте кавычки
-version "ForgeOptiFine 1.20.4"
```

### Автозапуск не работает
Удалите файл `.tlauncher/tlauncher.json` для сброса настроек:
```bash
del "%APPDATA%\.tlauncher\tlauncher.json"
```
