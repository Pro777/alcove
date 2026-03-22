# asl-gloss

English → ASL gloss pre-converter. Converts plain English text to a simplified
ASL (American Sign Language) gloss notation as a starting draft for human
interpreters. No external dependencies.

## Usage

```bash
# Convert a sentence
python tools/asl-gloss/gloss.py "The cat sat on the mat."

# Convert from a file (one sentence per line)
python tools/asl-gloss/gloss.py --file sentences.txt

# JSON output
python tools/asl-gloss/gloss.py --format json "Do you want coffee?"

# Keep articles (skip removal)
python tools/asl-gloss/gloss.py --keep-articles "The cat sat."
```

## Example output

```
EN:  The cat sat on the mat.
ASL: CAT SAT ON MAT

EN:  Do you want coffee?
ASL: YOU WANT COFFEE Y/N
     [Y/N question marker added]

EN:  She doesn't like it.
ASL: SHE LIKE NOT IT
```

## Transformations applied

| Rule | Example |
|---|---|
| Article removal | `the cat` → `CAT` |
| Copula reduction | `is happy` → `HAPPY` |
| Pronoun substitution | `I` → `ME`, `we` → `WE` |
| Negation expansion | `don't want` → `WANT NOT` |
| Y/N question marker | `Do you want?` → `YOU WANT Y/N` |
| Wh-question movement | `What do you want?` → `YOU WANT WHAT ?` |
| Temporal adverb fronting | `went yesterday` → `YESTERDAY WENT` |

## Plugin interface

```python
# The directory name uses a hyphen, so load with importlib:
import importlib.util, sys
spec = importlib.util.spec_from_file_location("gloss", "tools/asl-gloss/gloss.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["gloss"] = mod
spec.loader.exec_module(mod)
GlossConverter = mod.GlossConverter
SignLanguagePlugin = mod.SignLanguagePlugin

converter = GlossConverter()
result = converter.convert("She doesn't want coffee.")
print(result.gloss)   # SHE WANT NOT COFFEE
print(result.tokens)  # ['SHE', 'WANT', 'NOT', 'COFFEE']
print(result.notes)   # []

# Batch conversion
results = converter.convert_batch(["Hello.", "Goodbye."])
```

Implement `SignLanguagePlugin` protocol to extend or replace the converter in
the Alcove plugin system.

## Important note

ASL gloss output is a **draft pre-processing aid** for human interpreters,
not a production translation. Always review with a qualified ASL interpreter.

## Dependencies

No external dependencies — stdlib only.
