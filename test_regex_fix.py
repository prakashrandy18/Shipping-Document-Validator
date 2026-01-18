
import re

text_problematic = "CTN NO  1 - 1704"
text_correct = "TOTAL: 1704"

patterns = [
    (r'TOTAL:\s*PACKED\s+IN:\s*([\d,]+)\s*CARTONS?', 1.0),
    (r'([\d,]+)\s+CARTON\s*\(\s*S\s*\)', 1.0),
    (r'GRAND\s+TOTAL\s+CARTON\s+Q[\'\"]?TY[:\s]*([\d,]+)', 1.0),
    (r'TYPES?\s+OF\s+PACKAGE[:\s]*([\d,]+)', 0.95),
    (r'\(CTN\)[:\s]*([\d,]+(?:\.\d+)?)', 0.95),
    # (r'CTN\s+NO[:\s]*([\d,]+)', 0.95), # Removed
    (r'TOTAL[:\s]+([\d,]+)\b', 0.85),  # Added
    (r'TOTAL[:\s]*([\d,]+)\s*(?:CTNS?|CARTONS?)', 0.9),
    (r'CTN[:\s]+([\d,]+(?:\.\d+)?)', 0.9),
    (r'CTNS[:\s]+([\d,]+(?:\.\d+)?)', 0.9),
    (r'([\d,]+)\s+CTNS?\b', 0.85),
    (r'NUMBER\s+OF\s+CARTONS?[:\s]*([\d,]+)', 0.85),
]

def test(text):
    print(f"Testing text: '{text}'")
    best_match = None
    best_conf = 0.0
    for pat, conf in patterns:
        m = re.search(pat, text)
        if m:
            val = m.group(1)
            print(f"  Match: '{pat}' -> {val} (conf={conf})")
            if conf > best_conf:
                best_conf = conf
                best_match = val
    print(f"  BEST: {best_match} with conf {best_conf}")

print("--- REGEX TEST ---")
test(text_problematic)
test(text_correct)
