> Archived historical prompt. Not used by the WorkCrew runtime; see `README.md`.

**Filler Agent (Claude):**

## Steps

### 1. Read the Reference Format

Open the **"6) Engagement Projects"** sheet in `draft.xlsx` and note the naming format used for **Project ID*** and **Parent Program***.

Every entry in **"7) Practicum Courses"** must strictly follow the same format.

### 2. Read the Classification Standards

Open the **"Main Issue Area Codes"** tab in `draft.xlsx` and record all categories listed under **Standardized Format**. Use these categories for subsequent mapping.

### 3. Extract Information Folder by Folder

Process the 12 folders in the following order:

Brazil 2015 → India 2008 → India 2009 → … → India 2016
→ Inida 2017 → kenya 2020

For each folder:

* Read all documents contained in the folder, including PDF, DOCX, XLSX, PPT, and other relevant files.
* Extract any information that can be mapped to the columns in **"7) Practicum Courses"**.

### 4. Field Mapping Rules

| Column                       | Rule                                                                                                                                                                                                                        |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Main Issue Area(s)** | Match the information to one or more**Standardized Format** categories recorded in Step 2. If an exact match is not possible, select the closest category and note this in the source attribution.                    |
| **Project Tags**       | Select only from the following options: Financial Modeling · Impact Assessment · Marketing · Business Strategy/Revenue · Organizational Systems and Behavior · Investing/Endowment · Scaling · Technology Innovation |
| **All Other Columns**  | Fill in the fields based strictly on the documents in the relevant folder. Leave the field blank if the information cannot be determined.                                                                                   |

### 5. Source Attribution Required for Every Cell

Every populated field must include a brief source-based justification using the following format:

> `[filename] One-sentence specific justification`

Examples:

> `[India 2008/Project_Brief.pdf] The title page identifies the sector as Healthcare.`
> `[India 2012/syllabus.docx, p.2] The course description lists Financial Modeling as a core module.`

Do not use vague justifications such as "based on an overall assessment."

When multiple sources corroborate the same field, list only the 2–3 most important sources.

The source attribution information must also be organized as structured data, either in JSON format or in a separate sheet, using the following structure:

`{ "row_id + column_name": "source attribution text" }`

I will later use this structured source data to generate an interactive webpage where users can click to view the supporting sources.
