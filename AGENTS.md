## Language Islands Varvara - Project Rules

### Translation Source Rule

When creating a theme for any target language such as Spanish, French, German, Italian, or Japanese, the content must be derived from the English source:

`themes/theme-XX__topic/level-basic/theme.json`

Specifically:
1. Read the English `theme.json` to get the list of entries with `en` and `ru` fields.
2. Translate the `en` text into the target language.
3. Keep the `ru` text unchanged so that it matches the English theme exactly.
4. Preserve the same number of entries, the same names such as Yulia, Zhenya, Ilya, and Felix, and the same narrative structure.
5. Do not invent new characters, new phrases, or change the meaning of entries.

The English themes are the canonical source. All non-English themes are translations of the corresponding English theme.

### Theme Structure

- English themes: `themes/theme-XX__topic/level-basic/theme.json` use the `en` field for target text.
- Non-English themes: `themes/<language>/theme-XX__slug/level-basic/theme.json` use the `text` field for target text and include a root `language` field.

### Encoding Integrity Rule

All Russian text and all user-readable text outputs must remain readable in UTF-8.

Rules:
1. Before rebuilding any theme, verify that `theme.json` is readable as UTF-8 and that `ru` fields contain real Cyrillic text, not placeholders such as `???` or replacement characters such as `�`.
2. If Russian text is damaged, do not continue the build until it is repaired.
3. After generation, verify that user-readable text files such as `.txt`, `.srt`, and JSON sources open correctly as UTF-8 and preserve Cyrillic text.
4. Do not silently accept outputs where Russian text has turned into question marks, replacement symbols, or mojibake.
5. If encoding damage is detected, treat it as a build error, fix the source text first, and only then regenerate PDF, subtitles, video, and archives.

### Subtitle Timing Rule

When building subtitles and burned-in video, phrase timing must prioritize the real start of spoken sentences.

Rules:
1. If speech chunk detection yields the same number of chunks as theme entries, treat those chunk starts as the primary timing anchors.
2. In that case, subtitle timing should be aligned to the beginning of each spoken phrase, not only distributed proportionally by text length.
3. For long `level-hard` sentences, do not let smoothing or proportional timing push the on-screen text noticeably behind the voice.
4. Use proportional timing only as a fallback when reliable phrase-start anchors cannot be detected from the audio.

### Advanced Level Rule

When creating `level-advanced` for an English theme, the corresponding English `level-basic` theme remains the source of truth.

Rules:
1. `level-advanced` must preserve the same theme, the same personal facts, the same names, and the same overall narrative as `level-basic`.
2. `level-advanced` must not invent new characters, new events, or new factual claims that are absent from `level-basic`.
3. The difference from `level-basic` must be meaningful, not cosmetic. It is not enough to only join two short sentences into one longer sentence.
4. `level-advanced` should sound more natural and connected by using:
   - linking words such as `because`, `but`, `so`, `usually`, and `sometimes`
   - slightly richer personal explanation
   - short cause-and-effect phrasing
   - small reflective phrases such as `I think`, `it helps me`, and `I enjoy`
5. `level-advanced` may use more advanced grammar selectively and naturally, including:
   - `Present Continuous`
   - `Present Perfect`
   - comparison language
   These forms should only be used where they sound natural for a schoolgirl aged about 10-11.
6. `level-advanced` must still remain below `level-hard`. It should feel like a stronger and more connected personal monologue, not a formal essay and not an adult-style text.
7. The number of entries should normally stay in the `20-30` range, but the final PDF must still fit on one A4 page.

Practical interpretation:
- `basic` = short direct facts, mostly one idea per sentence
- `advanced` = the same facts expressed in a more connected, more natural, more descriptive way
- `hard` = a denser and more independent monologue with substantially richer structure

### Full Build Pipeline

When creating a new theme, the agent must complete the entire pipeline from start to finish and produce all final output files: PDF, MP3, MP4, SRT, and ZIP. Do not stop after creating `theme.json`.

#### Step 1 - Create `theme.json`

Translate or adapt from the canonical source and create the target theme file.

#### Step 2 - Generate PDFs and text inputs

```powershell
python scripts/build_island.py <theme.json>
```

This produces the bilingual PDF, active recall PDF, and NaturalReaders text inputs.

#### Step 3 - Generate MP3

Use NaturalReaders as the primary TTS engine.

Fallback to `edge-tts` is allowed only when the user has not explicitly required NaturalReaders.

```powershell
edge-tts --voice <voice> --rate=-5% -f "<naturalreaders_input.txt>" --write-media "<output_mp3>"
```

Voice selection:
- Spanish: `es-ES-ElviraNeural` for `edge-tts` / `Arabella (Spain)` for NaturalReaders Plus Voice
- French: `fr-FR-DeniseNeural`
- German: `de-DE-KatjaNeural`
- Italian: `it-IT-ElsaNeural`

Important:
- If the user has explicitly requested NaturalReaders, do not silently switch to fallback TTS.
- In that case, if NaturalReaders is unavailable in the current environment, stop and report it honestly instead of substituting another engine.

#### Step 4 - Build repeat MP3

```powershell
python scripts/build_repeat_mp3.py <once.mp3> <repeat.mp3> <phrase_count>
```

`<phrase_count>` is the number of entries in the theme.

#### Step 5 - Final build

```powershell
python scripts/build_island.py <theme.json>
```

This re-runs the build with MP3 files in place and produces the final video, subtitles, and ZIP archive.

### Expected Output Files

| File pattern | Description |
|---|---|
| `__03__bilingual_study.pdf` | Bilingual PDF (target + Russian) |
| `__04__shadowing_<lang>.mp3` | Once audio |
| `__04a__shadowing_<lang>__naturalreaders_input.txt` | Text input for TTS |
| `__05__active_recall.pdf` | Active recall PDF |
| `__06__shadowing_<lang>_repeat.mp3` | Repeat audio (5x each phrase) |
| `__13__shadowing_ru.srt` | Russian subtitles |
| `__14__shadowing_video_<lang>.mp4` | Video with subtitles |

### File Naming

- Files use language codes such as `_es`, `_en`, `_fr`, and so on.
- Output goes to `output/<Language>/N. Topic Name/level-basic/` or the corresponding level folder.
