# scripts/validate_prompts.py  (minimal placeholder)
import sys, json, pathlib
def is_ascii(s): return all(ord(c) < 128 for c in s)
errors = 0
for path in pathlib.Path(sys.argv[1]).rglob("*.ndjson"):
    for ln, line in enumerate(path.read_text().splitlines(), 1):
        try:
            obj = json.loads(line)
        except Exception as e:
            print(f"{path}:{ln} invalid JSON: {e}")
            errors += 1
            continue
        if not is_ascii(json.dumps(obj)):
            print(f"{path}:{ln} contains non-ASCII characters")
            errors += 1
if errors:
    sys.exit("Prompt validation failed")
print("All prompts valid")
