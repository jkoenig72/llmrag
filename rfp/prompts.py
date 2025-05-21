import logging
from config import get_config
from langchain.prompts import PromptTemplate

# Get configuration
config = get_config()
logger = logging.getLogger(__name__)

class PromptManager:
    """
    Manager for prompt templates used in the RFP processing system.
    
    This class provides access to the various prompt templates used
    for summarization, question answering, and refinement.
    """
    
    # Prompt for summarizing long text
    SUMMARY_PROMPT = PromptTemplate.from_template(
        template="""
You are an experienced technical writer specialized in summarizing technical documentation.
Your task is to summarize the following document text into a concise and professional paragraph:
- Ensure key technical and business points are retained
- The summary should be targeted toward an audience of engineers and technical managers
- Keep the summary under {{ MAX_WORDS_BEFORE_SUMMARY }} words
---

Original Text:
{{ text }}

Summary:
""",
        template_format="jinja2"
    )

    # Prompt for answering RFP questions
    QUESTION_PROMPT = PromptTemplate.from_template(
        template="""
You are a Senior Solution Engineer at Salesforce, with deep expertise in Salesforce products{% if product_focus and product_focus != "None" %}, particularly in {{ product_focus }}{% endif %}.

CRITICAL INSTRUCTIONS:
1. Your ENTIRE response must be ONLY a valid JSON object - nothing else
2. The "answer" field MUST contain NORMAL PLAIN TEXT ONLY - NO JSON STRUCTURES, NO LISTS, NO OBJECTS
3. NEVER put JSON, code blocks, or structured data inside the "answer" field
4. The "references" field must be an array of relevant Salesforce URLs from the context
5. Be OPTIMISTIC about compliance ratings - if it can be achieved with configuration or low-code tools, mark it as FC

❗️STEP 1: EVALUATE RELEVANCE - VERY IMPORTANT
Carefully determine if the question is directly relevant to Salesforce{% if product_focus and product_focus != "None" %} or {{ product_focus }}{% endif %}.
A question is NOT RELEVANT if:
- It asks about non-Salesforce topics (e.g., weather, history, colors, personal opinions)
- It doesn't relate to any business or technical function Salesforce provides
- It's about general topics unrelated to CRM, sales, service, or marketing platforms

If NOT relevant, you MUST return EXACTLY:
{
  "compliance": "NA",
  "answer": "This question is not applicable to Salesforce{% if product_focus and product_focus != "None" %} or {{ product_focus }}{% endif %} and should be marked as out of scope.",
  "references": []
}

✅ If relevant, continue to STEP 2.

❗️STEP 2: DETERMINE COMPLIANCE LEVEL
- FC (Fully Compliant): Supported via standard features, configuration, or low-code tools. This includes anything achievable through the UI, Flow Builder, Process Builder, or minimal configuration. If it can be done without extensive coding, consider it FC.
- PC (Partially Compliant): Requires significant custom development such as complex Apex coding, extensive LWC development, or complex external system integrations.
- NC (Not Compliant): Not possible in Salesforce even with customization
- NA (Not Applicable): Out of scope for Salesforce products

❗️STEP 3: FORMAT YOUR RESPONSE
Return ONLY this JSON structure:
{
  "compliance": "FC|PC|NC|NA",
  "answer": "Write ONLY a clear, professional explanation in 5-10 sentences. NEVER include JSON here!",
  "references": ["URL1", "URL2"]
}

EXAMPLES OF IRRELEVANT QUESTIONS THAT SHOULD BE MARKED NA:
1. "Is red a better color than green?" - This is about color preferences, not Salesforce.
2. "What will the weather be tomorrow?" - This is about weather forecasting, not Salesforce.
3. "What do you think about Alexander the Great?" - This is about historical figures, not Salesforce.
4. "Which diet is best for weight loss?" - This is about nutrition, not Salesforce.

EXAMPLES OF RELEVANT QUESTIONS:
1. "Do you support Email to Case functionality?" - This is about Salesforce Service Cloud features.
2. "How does Order Management work in your solution?" - This is about Salesforce functionality.

Context:
{{ context_str }}

Question:
{{ question }}

Response (JSON only):
""",
        template_format="jinja2"
    )

    # Prompt for refining answers with additional context
    REFINE_PROMPT = PromptTemplate.from_template(
        template="""
You are refining an RFI response about Salesforce{% if product_focus and product_focus != "None" %}, particularly regarding {{ product_focus }}{% endif %}.

CRITICAL INSTRUCTIONS:
1. Return ONLY a valid JSON object with the EXACT same structure as the existing answer
2. The "answer" field must contain ONLY plain text - NO JSON, NO code blocks
3. Your task is to ENHANCE the existing answer with new information, not replace it entirely 

Carefully analyze the new context and update ONLY if the new information:
1. Contradicts your previous answer with more accurate information
2. Provides more specific details about Salesforce capabilities
3. Changes the compliance level based on new evidence
4. Adds relevant references not previously included

Compliance levels:
- FC: Available through standard features, configuration, or low-code tools
- PC: Requires significant custom development
- NC: Not possible even with customization
- NA: Out of scope

Return ONLY this JSON structure:
{
  "compliance": "FC|PC|NC|NA",
  "answer": "Refined explanation in plain text only (5-10 sentences)",
  "references": ["URL1", "URL2"]
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
    
    @classmethod
    def get_summary_prompt(cls):
        """Get the summary prompt template."""
        logger.debug("Retrieving summary prompt template")
        return cls.SUMMARY_PROMPT
    
    @classmethod
    def get_question_prompt(cls):
        """Get the question prompt template."""
        logger.debug("Retrieving question prompt template")
        return cls.QUESTION_PROMPT
    
    @classmethod
    def get_refine_prompt(cls):
        """Get the refinement prompt template."""
        logger.debug("Retrieving refinement prompt template")
        return cls.REFINE_PROMPT
    
    @classmethod
    def format_summary_prompt(cls, text: str) -> str:
        """
        Format the summary prompt with the provided text.
        
        Args:
            text: Text to summarize
            
        Returns:
            Formatted prompt
        """
        logger.debug("Formatting summary prompt with text length: %d", len(text))
        return cls.SUMMARY_PROMPT.format(text=text, MAX_WORDS_BEFORE_SUMMARY=config.max_words_before_summary)
    
    @classmethod
    def format_question_prompt(cls, context_str: str, question: str, product_focus: str = None) -> str:
        """
        Format the question prompt with the provided context and question.
        
        Args:
            context_str: Context for the question
            question: Question to answer
            product_focus: Optional product focus
            
        Returns:
            Formatted prompt
        """
        logger.debug("Formatting question prompt with context length: %d, question: %s, product_focus: %s", 
                    len(context_str), question, product_focus)
        return cls.QUESTION_PROMPT.format(
            context_str=context_str,
            question=question,
            product_focus=product_focus
        )
    
    @classmethod
    def format_refine_prompt(cls, question: str, existing_answer: str, context_str: str, product_focus: str = None) -> str:
        """
        Format the refinement prompt with the provided information.
        
        Args:
            question: Original question
            existing_answer: Existing answer to refine
            context_str: New context for refinement
            product_focus: Optional product focus
            
        Returns:
            Formatted prompt
        """
        logger.debug("Formatting refinement prompt with question: %s, context length: %d, product_focus: %s",
                    question, len(context_str), product_focus)
        return cls.REFINE_PROMPT.format(
            question=question,
            existing_answer=existing_answer,
            context_str=context_str,
            product_focus=product_focus
        )