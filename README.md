# QC Bridge Blender-Maya

`QC Bridge Maya-Blender by Mutaform` состоит из двух частей:

- Blender extension: `mutaform_bridge/`
- файлы для Maya: `maya/mutaform_bridge/`

Blender-часть устанавливается как обычный Blender Extension через ссылку на репозиторий. Maya-часть скачивается отдельным архивом и ставится перетаскиванием `install/install.py` во вьюпорт; дальше она обновляет себя сама.

## Установка в Blender

Добавьте в Blender ссылку на extension repository:

```text
https://mutaform.github.io/qc-bridge-blender-maya/index.json
```

Затем синхронизируйте репозитории и установите:

```text
QC Bridge Maya-Blender by Mutaform
```

После включения в шапке 3D Viewport, сразу после кнопок Proportional Editing,
появится иконка Maya. Нажатие открывает выпадающее меню моста: Import From
Maya, Export Selected, Export Selected Collection, Convert Scene и Settings.
В N-панели аддон больше не отображается.

## Установка в Maya

1. Скачайте [`mutaform_bridge_maya.zip`](https://mutaform.github.io/qc-bridge-blender-maya/mutaform_bridge_maya.zip)
2. Распакуйте **туда, где папка останется** — в папку инструментов, на сетевую шару,
   куда угодно постоянное
3. Перетащите `install/install.py` из распакованной папки во вьюпорт Maya

Всё. Установщик пропишет модуль Maya, добавит кнопку **QC Bridge** на полку
*Mutaform*, уберёт кнопку и копию старой версии 1.1.x из папки `scripts`, если
они есть, и откроет окно.

> **Распакованная папка и есть установка.** Ничего не копируется во внутренние
> каталоги Maya: файл модуля — это указатель на неё. Поэтому обновление сводится к
> замене одной папки. Обратная сторона: если папку удалить или перенести,
> инструмент отвалится — распакуйте заново и перетащите `install.py` ещё раз.

Удалить: `install.uninstall()`. Саму папку установщик не трогает.

## Обновления в Maya

В Maya нет репозитория аддонов, поэтому механизм свой — тот же, что в QC Bake for
Maya. Окно при каждом открытии спрашивает манифест на GitHub Pages, есть ли версия
новее, и если есть — сообщает об этом сверху. Само ничего не ставит.

По кнопке **Install** архив скачивается, сверяется с контрольной суммой из
манифеста, распаковывается, подменяет папку пакета и перезагружает его **без
перезапуска Maya**. Предыдущая версия хранится, пока новая не загрузится, — так
сломанный релиз откатывает себя сам.

Проверка идёт в фоновом потоке и молчит при неудаче, если вы её не запрашивали.
Отключить или запустить вручную: **Settings → Updates**.

Blender-половина обновляется штатно: Blender сам видит новую версию в
репозитории расширений.

## Ссылки

Blender repository index:

[https://mutaform.github.io/qc-bridge-blender-maya/index.json](https://mutaform.github.io/qc-bridge-blender-maya/index.json)

Maya archive:

[https://mutaform.github.io/qc-bridge-blender-maya/mutaform_bridge_maya.zip](https://mutaform.github.io/qc-bridge-blender-maya/mutaform_bridge_maya.zip)

Maya update manifest:

[https://mutaform.github.io/qc-bridge-blender-maya/version.json](https://mutaform.github.io/qc-bridge-blender-maya/version.json)

## Сборка

Из корня репозитория:

```powershell
powershell -ExecutionPolicy Bypass -File tools/build_release.ps1
```

Скрипт собирает оба архива и сверяет, что версия в `blender_manifest.toml`,
`mutaform_bridge/__init__.py` и `maya/mutaform_bridge/__init__.py` одна и та же.
Локально вывод создаётся рядом с репозиторием, в `Dev\`:

```text
Dev\dist\mutaform_bridge_blender-<версия>.zip
Dev\dist\mutaform_bridge_maya-<версия>.zip
Dev\pages\   оба архива под постоянными именами, version.json, index.html
```

Копии с версией в имени складываются в `Zip Addon\`, предыдущие версии уходят в
`Zip Addon\old\`. На CI вывод остаётся в корне чекаута, откуда workflow
публикует `pages/` в ветку `gh-pages`, добавив туда `index.json` репозитория
расширений Blender. Манифест обновлений Maya генерируется сборкой, а не пишется
руками: иначе он рано или поздно начнёт описывать не тот архив, что лежит рядом.

Апдейтер не импортирует Maya и тестируется где угодно, в том числе против
собранного архива и манифеста:

```bash
python tests/test_updater.py
```

`tests/test_install_maya.py` запускается внутри Maya: ставит собранный архив в
чистую папку, проверяет кнопку, модуль и окно, потом возвращает установку из
репозитория. Сцену не трогает. Способ запуска — в шапке файла.

## Структура репозитория

```text
mutaform_bridge/       исходники Blender extension
maya/mutaform_bridge/  пакет Maya companion
maya/install/          установщик Maya (перетащить во вьюпорт)
tests/                 тесты апдейтера и установки
tools/                 скрипт сборки
```

## Лицензия

GPL-3.0-or-later, как указано в Blender Extension manifest.
