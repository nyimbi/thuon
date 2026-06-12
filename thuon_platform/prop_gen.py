import csv
import re
from langchain_ollama.llms import OllamaLLM
from requests.models import encode_multipart_formdata


import re

def parse_thought(response: str) -> tuple[str, str]:
    """
    Parses text in the format:
    <think>
    Thinking Text
    </think>
    Answer Text

    Args:
        response: The input string containing the thought and answer.

    Returns:
        A tuple containing the thinking text and the answer text.
        Returns empty strings if the format is invalid.
    """
    try:
        thinking_match = re.search(r"<think>\s*(.*?)\s*</think>", response, re.DOTALL)
        if thinking_match:
            thinking_text = thinking_match.group(1).strip()
            answer_start = thinking_match.end()
            answer_text = response[answer_start:].strip()
            return thinking_text, answer_text
        else:
            return "", response.strip()  # Handle cases where <think> tag is missing.

    except Exception as e: # Catch any potential errors during parsing.
        print(f"Error parsing response: {e}") # Print the error for debugging
        return "", response  # Return responseempty strings on error.



# sect_no	head_level	title	key_aspect	Instruction	extra_instruction
llm_context = """
Some Context:
---
First International Africa Investment Bank (FIAB): New Sharia‑compliant investment bank headquartered in Rwanda focused in Africa. Targets unmet demand among Muslim and ethical customers via interest‑free finance—Murabaha, Mudaraba, Ijarah, Sukuk. Operates in Rwanda and East Africa; market potential of 61 M customers with bankable population growing from 7.4 M to 9.3 M. Financials: assets Rwf 40B (2025) → Rwf 406B (2030), break‑even in year one, profit margin 47%, cost‑to‑income 29%; revenue Rwf 2.9B → Rwf 30B; net income Rwf 164M → Rwf 13B.

Advanced digital platforms (AI, mobile, blockchain) drive operations. Rigorous risk management and strict regulatory compliance ensure stability; funding via international Sukuk, equity, deposits with target capital adequacy of 27%. Governance comprises a Board, Sharia Supervisory Committee, and oversight bodies. Competitive edge: first‑mover, exclusive full Sharia compliance; strategic partnerships and global financial expertise.

---
"""
post_prompt = """
Speak in complete sentences. Avoid using lists if possible. Use bold to highlight specific terminology, key ideas and concepts. Demonstrate a nuanced, detailed, expert level understanding of the task and objectives.
- Precise Terminology - If you know the exact term for something, use it. Avoid watered down or generic language. Scientific jargon is acceptable.
- Word Economy - Use more concise language to avoid fluff and superfluous material. Maintain a high insight-to-word ratio. Keep your responses full length.
- Write 5000 thoughtful words that cover every facet.
"""

model = OllamaLLM(model="dr1")

with open('/Users/nyimbiodero/src/pjs/work_docs/Projects/FIAB/sections.csv', newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        key_aspect = row['key_aspect']  # Adjust the key to match your CSV's column name
        inst = row["Instruction"]
        extra = row["extra_instruction"]
        head_level = row["head_level"]
        title = row["title"]
        sect_no = row["sect_no"]

        prompt = f"""
        {llm_context}
        Task: {inst}
        Be sure to cover {key_aspect}.
        {extra}
        --
        {post_prompt}
        """

        # print(prompt)
        # Generate a response using the model
        response = model.invoke(prompt)


        # Output the response
        print(f"{sect_no} - {title}")
        pre_a = ""
        if head_level == "Subsection":
            pre_a = "## "
        if head_level == "Subsubsection":
            pre_a = "### "
        thinking, answer = parse_thought(response)
        with open("/Users/nyimbiodero/src/pjs/work_docs/Projects/FIAB/prop_only.md", "a") as f:
            f.write(f"\n{pre_a} {sect_no} {title} \n\n")
            f.write(answer)

        with open("/Users/nyimbiodero/src/pjs/work_docs/Projects/FIAB/prop_n_thought.md", "a") as f:
            f.write(f"\n{pre_a} {sect_no} {title} \n\n")
            f.write(response)
