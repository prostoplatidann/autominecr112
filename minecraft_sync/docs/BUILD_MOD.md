# Инструкция по сборке Forge-мода WorldSync

## Требования для сборки
- **JDK 17** (обязательно Java 17)
- **Gradle 8.x** (рекомендуется использовать Gradle Wrapper)
- **Git** (опционально, для клонирования репозитория)

## Шаг 1: Подготовка окружения

### Установка JDK 17
1. Скачайте JDK 17 с [официального сайта](https://www.oracle.com/java/technologies/downloads/#java17)
2. Установите и добавьте в PATH
3. Проверьте: `java -version` (должно показать версию 17)

### Настройка переменных окружения
```bash
# Windows
set JAVA_HOME=C:\Program Files\Java\jdk-17
set PATH=%JAVA_HOME%\bin;%PATH%

# Linux/Mac
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk
export PATH=$JAVA_HOME/bin:$PATH
```

## Шаг 2: Создание проекта Forge MDK

### Вариант A: Через Forge Installer (рекомендуется)
1. Скачайте Forge MDK для 1.21.1 с [официального сайта](https://files.minecraftforge.net/)
2. Распакуйте архив в отдельную папку
3. Запустите `gradlew setup` для инициализации

### Вариант B: Ручная настройка
1. Создайте новую папку для проекта
2. Скопируйте файлы из этого руководства:
   - `build.gradle` в корень проекта
   - `mods.toml` в `src/main/resources/META-INF/`
   - `WorldSyncMod.java` в `src/main/java/com/worldsync/mod/`

## Шаг 3: Структура проекта

Правильная структура должна выглядеть так:
```
worldsync-mod/
├── build.gradle
├── gradlew
├── gradlew.bat
├── settings.gradle
├── src/
│   └── main/
│       ├── java/
│       │   └── com/
│       │       └── worldsync/
│       │           └── mod/
│       │               └── WorldSyncMod.java
│       └── resources/
│           └── META-INF/
│               └── mods.toml
└── run/ (создаётся после сборки)
```

## Шаг 4: Сборка мода

### Windows
```batch
cd worldsync-mod
gradlew.bat build
```

### Linux/Mac
```bash
cd worldsync-mod
chmod +x gradlew
./gradlew build
```

## Шаг 5: Поиск собранного файла

После успешной сборки JAR-файл будет находиться:
```
build/libs/worldsync-1.21.1-1.0.jar
```

## Шаг 6: Установка мода

1. Найдите папку `.minecraft`:
   - Windows: `%APPDATA%\.minecraft`
   - Linux: `~/.minecraft`
   - Mac: `~/Library/Application Support/minecraft`

2. Скопируйте JAR-файл в папку `mods`:
   ```
   .minecraft/mods/worldsync-1.21.1-1.0.jar
   ```

3. Если папки `mods` нет, создайте её

## Решение проблем

### Ошибка: "Unsupported class file major version"
- Убедитесь, что используется JDK 17, а не более старая версия
- Проверьте: `java -version`

### Ошибка: "Could not find toolchain"
- Установите JDK 17 правильно
- Укажите путь в `gradle.properties`:
  ```
  org.gradle.java.home=C:\\Program Files\\Java\\jdk-17
  ```

### Ошибка: "Forge dependencies not found"
- Проверьте интернет-соединение
- Попробуйте очистить кэш Gradle: `gradlew --refresh-dependencies`

### Мод не загружается в Minecraft
- Проверьте версию Forge (должна быть 1.21.1)
- Посмотрите логи в `.minecraft/logs/latest.log`
- Убедитесь, что мод совместим с вашей версией Forge

## Быстрая сборка (для опытных)

Если у вас уже настроен Forge MDK 1.21.1:

```bash
# Копирование файлов мода
cp WorldSyncMod.java src/main/java/com/worldsync/mod/
cp mods.toml src/main/resources/META-INF/

# Сборка
./gradlew clean build

# Копирование в Minecraft (Windows)
copy build\libs\worldsync-1.21.1-1.0.jar %APPDATA%\.minecraft\mods\
```

## Проверка работы

1. Запустите Minecraft с Forge 1.21.1
2. В главном меню нажмите "Mods"
3. Найдите в списке "WorldSync Mod"
4. Если мод отображается - установка успешна

## Дополнительные ресурсы

- [Документация Forge](https://mcforge.readthedocs.io/)
- [Forge Discord](https://discord.gg/Uvedt9m)
- [Minecraft Modding Wiki](https://mcforge.readthedocs.io/en/latest/)
