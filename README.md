# Language Islands Pipeline

Локальный пайплайн для сборки "языкового острова" без доступа к основному компьютеру.

Что собирается из одной темы:

- `03__bilingual_study.pdf`
- `05__active_recall.pdf`
- `04a__shadowing_en__naturalreaders_input.txt`
- `06a__shadowing_en_repeat__naturalreaders_input.txt`
- `13__shadowing_en.srt`
- `14__shadowing_video_en.mp4`
- `.zip` с готовыми артефактами

## Быстрый старт

```powershell
cd F:\Projects\LanguageIslandsVarvara
python -m pip install -r requirements.txt
python .\scripts\build_island.py .\themes\theme-01__about-me-my-family-and-school\theme.json
```

Для сборки всех тем сразу:

```powershell
python .\scripts\build_all.py
```

После первого запуска в папке `output\1. Обо мне\` появятся:

- два PDF
- два TXT для вставки в NaturalReaders
- ожидаемые имена для MP3
- SRT для субтитров

## Ручной шаг с NaturalReaders

1. Откройте `04a__shadowing_en__naturalreaders_input.txt`.
2. Вставьте текст в NaturalReaders и скачайте аудио как:
   `theme-01__about-me-my-family-and-school__04__shadowing_en.mp3`
3. Откройте `06a__shadowing_en_repeat__naturalreaders_input.txt`.
4. Вставьте текст в NaturalReaders и скачайте аудио как:
   `theme-01__about-me-my-family-and-school__06__shadowing_en_repeat.mp3`
5. Сохраните оба MP3 в ту же папку `output\1. Обо мне\`.

## Сборка видео после появления MP3

Повторно запустите ту же команду:

```powershell
python .\scripts\build_island.py .\themes\theme-01__about-me-my-family-and-school\theme.json
```

Если файл `04__shadowing_en.mp3` найден, скрипт автоматически:

- пересчитает `13__shadowing_en.srt`
- соберет `14__shadowing_video_en.mp4`
- обновит `.zip`

## Формат исходной темы

См. пример:

- [theme.json](F:\Projects\LanguageIslandsVarvara\themes\theme-01__about-me-my-family-and-school\theme.json)
- [template theme.json](F:\Projects\LanguageIslandsVarvara\themes\_template\theme.json)

Каждая запись содержит английскую фразу и русский смысл. Из одного файла строятся все артефакты.

Для индивидуальных тем можно хранить уровни отдельно внутри одной темы:

- `theme-XX__topic\level-basic\theme.json`
- `theme-XX__topic\level-advanced\theme.json`
- `theme-XX__topic\level-hard\theme.json`

Если в `theme.json` указан `"level": "basic"` или другой уровень, выходные файлы будут складываться в соответствующую подпапку внутри `output`.
