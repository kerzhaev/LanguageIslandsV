# Language Islands Pipeline

Локальный пайплайн для сборки персональных "языковых островов".

В репозитории хранятся:
- скрипты сборки
- структура тем
- шаблоны уровней
- правила генерации PDF, TXT, SRT, MP3-ожиданий и видео

В репозиторий не входят:
- результаты генерации из `output/`
- временные файлы
- браузерный профиль
- скачанные артефакты `mp3/mp4/pdf/srt/zip`

## Структура

- `scripts/build_island.py` — основная сборка одной темы
- `scripts/build_all.py` — пакетная сборка
- `scripts/naturalreaders_download.mjs` — автоматизация NaturalReaders
- `themes/` — темы и уровни
- `output/` — результаты сборки, не версионируются

## Формат темы

Обычный вариант:

- `themes/theme-XX__topic/theme.json`

Многоуровневый вариант:

- `themes/theme-XX__topic/level-basic/theme.json`
- `themes/theme-XX__topic/level-advanced/theme.json`
- `themes/theme-XX__topic/level-hard/theme.json`

## Что собирается из темы

- `03__bilingual_study.pdf`
- `05__active_recall.pdf`
- `04a__shadowing_en__naturalreaders_input.txt`
- `06a__shadowing_en_repeat__naturalreaders_input.txt`
- `13__shadowing_ru.srt`
- `14__shadowing_video_en.mp4`
- `.zip` с готовыми файлами

Если `mp3` еще нет, пайплайн готовит PDF и TXT и ждет аудио с ожидаемыми именами.

## Быстрый старт

```powershell
cd F:\Projects\LanguageIslandsVarvara
python -m pip install -r requirements.txt
python .\scripts\build_island.py .\themes\theme-01__about-me-my-family-and-school\theme.json
```

Для пакетной сборки:

```powershell
python .\scripts\build_all.py
```

## NaturalReaders

Обычный сценарий:

1. Пайплайн создает два TXT-файла для темы.
2. Текст отправляется в NaturalReaders.
3. Сервис отдает:
   `__04__shadowing_en.mp3`
4. Сервис отдает:
   `__06__shadowing_en_repeat.mp3`
5. После появления `mp3` повторный запуск сборки создает `ru.srt`, `mp4` и архив.

## Печать

Текущая верстка настроена так, чтобы:

- одна тема помещалась не более чем на один лист A4
- тема старалась заполнять лист максимально полно

Сводные файлы:

- `output/all-themes-bilingual-study.pdf`
- `output/all-themes-active-recall.pdf`
- `output/all-themes-print.pdf`

## Git и сохранность пайплайна

Этот проект уже инициализирован как git-репозиторий.

Текущий снимок пайплайна:

- ветка: `main`
- первый базовый коммит: `Initial language islands pipeline snapshot`

## Как перенести на GitHub

1. Создайте пустой репозиторий на GitHub.
2. Выполните в этом проекте:

```powershell
git remote add origin <URL_ВАШЕГО_РЕПОЗИТОРИЯ>
git push -u origin main
```

Если репозиторий на GitHub уже не пустой, сначала лучше посмотреть его состояние, а не пушить вслепую.

## Как объединить с пайплайном с другого компьютера

Лучший безопасный вариант — не копировать файлы поверх вручную, а заводить отдельную ветку.

Рекомендуемый порядок:

1. Этот восстановленный пайплайн остается в `main`.
2. Версию с другого компьютера добавьте в отдельную ветку, например:
   `other-computer-pipeline`
3. После этого сравнивайте ветки:
   - `scripts/`
   - `README.md`
   - структуру `themes/`
4. Берите лучшие решения из обеих веток и вносите их в новую рабочую ветку, например:
   `merge-best-of-both`

Полезные команды:

```powershell
git checkout -b other-computer-pipeline
```

Когда версия со второго компьютера окажется в этой ветке:

```powershell
git diff main..other-computer-pipeline -- scripts
git diff main..other-computer-pipeline -- README.md
git diff main..other-computer-pipeline -- themes
```

Для аккуратного объединения:

```powershell
git checkout -b merge-best-of-both main
```

И дальше уже переносить лучшие изменения осознанно, а не автоматически целиком.
