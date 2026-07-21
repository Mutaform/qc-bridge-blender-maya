# QC Bridge Blender-Maya

`QC Bridge Maya-Blender by Mutaform` состоит из двух частей:

- Blender extension: `mutaform_bridge/`
- файлы для Maya: `maya/mutaform_bridge/`

Blender-часть устанавливается как обычный Blender Extension через ссылку на репозиторий. Maya-часть нужно скачать отдельным архивом и положить в папку scripts.

## Установка в Blender

Добавьте в Blender ссылку на extension repository:

```text
https://mutaform.github.io/qc-bridge-blender-maya/index.json
```

Затем синхронизируйте репозитории и установите:

```text
QC Bridge Maya-Blender by Mutaform
```

## Установка в Maya

Скачайте актуальный архив для Maya:

[mutaform_bridge_maya_v1.zip](https://mutaform.github.io/qc-bridge-blender-maya/mutaform_bridge_maya_v1.zip)

1. Закройте Maya.
2. Распакуйте архив `mutaform_bridge_maya_v1.zip`.
3. Внутри архива будет папка:

```text
mutaform_bridge
```

4. Эту папку нужно положить сюда:

```text
C:\Users\ИМЯ_ПОЛЬЗОВАТЕЛЯ\Documents\maya\2025\scripts\
```

В итоге должно получиться так:

```text
C:\Users\ИМЯ_ПОЛЬЗОВАТЕЛЯ\Documents\maya\2025\scripts\mutaform_bridge\
```

5. Запустите Maya.
6. Откройте Script Editor:

```text
Windows > General Editors > Script Editor
```

7. Перейдите на вкладку Python.
8. Вставьте туда код:

```python
import sys

path = r"C:\Users\ИМЯ_ПОЛЬЗОВАТЕЛЯ\Documents\maya\2025\scripts\mutaform_bridge"
if path not in sys.path:
    sys.path.append(path)

import install_shelf_button
install_shelf_button.install()
```

9. Замените `ИМЯ_ПОЛЬЗОВАТЕЛЯ` на имя пользователя Windows.

Например:

```python
import sys

path = r"C:\Users\denis\Documents\maya\2025\scripts\mutaform_bridge"
if path not in sys.path:
    sys.path.append(path)

import install_shelf_button
install_shelf_button.install()
```

10. Нажмите `Ctrl + Enter`.

После этого кнопка `QC Bridge` появится на shelf `Poly Modeling`. Это кнопка с логотипом Mutaform. При нажатии открывается окно аддона.

## Ссылки

Blender repository index:

[https://mutaform.github.io/qc-bridge-blender-maya/index.json](https://mutaform.github.io/qc-bridge-blender-maya/index.json)

Maya archive:

[https://mutaform.github.io/qc-bridge-blender-maya/mutaform_bridge_maya_v1.zip](https://mutaform.github.io/qc-bridge-blender-maya/mutaform_bridge_maya_v1.zip)

## Сборка Blender ZIP

Из корня репозитория:

```powershell
powershell -ExecutionPolicy Bypass -File tools/build_release.ps1
```

Готовый архив будет создан здесь:

```text
dist/mutaform_bridge_blender.zip
```

## Структура репозитория

```text
mutaform_bridge/       исходники Blender extension
maya/mutaform_bridge/  исходники Maya companion
downloads/             скачиваемый Maya archive
tools/                 скрипты сборки
```

## Лицензия

GPL-3.0-or-later, как указано в Blender Extension manifest.
