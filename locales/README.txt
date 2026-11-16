Kiru languages
==============
Each .json file here is one language. Kiru lists them in Settings > Language.

  "name"      what the language is called in the list
  "strings"   "English text": "translation"   (copy the English exactly as Kiru shows it, without the final . : ... or bracket)
  "patterns"  the same, with {0} for a number and {t} for a track name, e.g. "Cut {0}": "Klipp {0}"

Anything a file does not have stays in English, so a file can be as small as you like.
To add a language: copy sv.json, rename it (for example it.json), change "name", translate the right-hand sides, restart Kiru.
To fix a translation: edit the file and restart Kiru.
