# How to Teach the AI (The Rulebook)

The file `rules.csv` allows you to manually override the AI's extraction logic for specific vendors or document types.

## How it works
1. When a new file is uploaded, the system checks if the **filename** contains a `Keyword` defined in `rules.csv`.
2. If it finds a match, it forces the AI to follow the specific `Action` for that file.

---

## Editing `rules.csv`

You can open this file in **Excel** or any Text Editor. It must have these 4 columns:

### Columns Explained

1. **Keyword**
   - The text to look for in the FILENAME.
   - Example: `Karooni` (matches "Karooni_Packing_List.pdf")
   - Example: `Garments` (matches "Invoice_Garments_123.pdf")

2. **Field**
   - Which data field are you fixing?
   - Options: `cartons`, `gross_weight`, `cbm`

3. **Action**
   - What should the AI do?
   - `IGNORE_COLUMN`: Tells the AI **NOT** to read from a specific column header.
   - `PICK_COLUMN`: Tells the AI **ONLY** to read from a specific column header.

4. **Value**
   - The exact text of the column header in the PDF table.
   - Example: `Total Garments Quantity` (to ignore it)
   - Example: `CTN QTY` (to pick it)

---

## Examples

#### Scenario 1: AI picks "Total Garments Quantity" instead of Cartons.
Add this row to tell AI to ignore that column:
| Keyword | Field | Action | Value |
| :--- | :--- | :--- | :--- |
| Garments | cartons | IGNORE_COLUMN | Total Garments Quantity |

#### Scenario 2: AI cannot find Cartons, but the column is named "PKG QTY".
Add this row to tell AI to look specifically for "PKG QTY":
| Keyword | Field | Action | Value |
| :--- | :--- | :--- | :--- |
| VendorXYZ | cartons | PICK_COLUMN | PKG QTY |

---

## Tips
*   **Keywords are Case-Insensitive:** `Karooni` will match `karooni` or `KAROONI`.
*   **Restart Required?** No. The system reads the CSV file every time a new batch runs. Just save the file and run your batch again!
