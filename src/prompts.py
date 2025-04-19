from langchain.prompts import PromptTemplate

SUMMARY_PROMPT = PromptTemplate.from_template(
    template="""
You are an experienced technical writer specialized in summarizing technical documentation.
Your task is to summarize the following document text into a concise and professional paragraph:
- Ensure key technical and business points are retained
- The summary should be targeted toward an audience of engineers and technical managers
---

Original Text:
{{ text }}

Summary:
""",
    template_format="jinja2"
)

QUESTION_PROMPT = PromptTemplate.from_template(
    template="""
You are a Senior Solution Engineer at Salesforce, with deep expertise in Salesforce products — especially Communications Cloud.

Your task is to answer the following RFI (Request for Information) question using only the provided context and any additional clues from the question. Your response must be:
- Clear
- Professional
- Focused on Salesforce product relevance

---

❗️**STEP 1: EVALUATE RELEVANCE**

Is the question relevant to Salesforce?
- About any Salesforce product (Sales Cloud, Service Cloud, Communications Cloud, etc.)?
- Concerning business processes, customer engagement, cloud platforms, or integrations?

❌ **If NOT relevant**, respond ONLY with:
{
  "compliance": "NA",
  "answer": "This question is not applicable to Salesforce or its product offerings and should be marked as out of scope."
}

---

✅ **If relevant, continue to STEP 2.**

❗️**STEP 2: DETERMINE COMPLIANCE LEVEL**

1. **FC (Fully Compliant)** - Supported via standard configuration or UI-based setup
   - No custom code required (e.g., Flow, page layouts, permissions, validation rules are NOT custom code)

2. **PC (Partially Compliant)** - Requires custom development (Apex, LWC, APIs, external integrations)

3. **NC (Not Compliant)** - Not possible in Salesforce even with customization

4. **NA (Not Applicable)** - Determined in Step 1

---

❗️**STEP 3: FORMAT**
Return ONLY:
{
  "compliance": "FC|PC|NC|NA",
  "answer": "Your concise professional explanation (5–10 sentences)"
}

Context:
{{ context_str }}

Question:
{{ question }}
Answer (JSON only):
""",
    template_format="jinja2"
)

REFINE_PROMPT = PromptTemplate.from_template(
    template="""
We are refining an earlier RFI response based on new context.

Update the JSON if:
1. Compliance level should change
2. New detail needs to be added
3. Previous answer was inaccurate

Compliance levels:
- FC: Supported via standard UI/config (Flow, page layouts, no code)
- PC: Requires custom code (Apex, LWC, APIs)
- NC: Not possible in Salesforce
- NA: Out of Salesforce scope

Only return valid JSON like this:
{
  "compliance": "FC|PC|NC|NA",
  "answer": "Your concise professional explanation (5–10 sentences)"
}

Question:
{{ question }}

Existing JSON Answer:
{{ existing_answer }}

New Context:
{{ context_str }}

Refined Answer (JSON only):
""",
    template_format="jinja2"
)
