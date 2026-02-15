import fitz
import json

doc = fitz.open("Title.pdf")
book_content = []

for page_num, page in enumerate(doc):
    blocks = page.get_text("dict")["blocks"]
    page_data = {"page": page_num + 1, "elements": []}

    for block in blocks:
        if "lines" in block:
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    if not text: continue

                    element = {
                        "text": text,
                        "size": span["size"],
                        "type": "header" if span["size"] > 15 else "paragraph",
                        "font": span["font"]
                    }
                    page_data["elements"].append(element)

    book_content.append(page_data)

print(json.dumps(book_content, indent=2, ensure_ascii=False))