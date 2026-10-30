import os
import json
import pandas as pd
import traceback 
from dotenv import load_dotenv
from langchain_core.exceptions import ModelAPIError
from langchain_openai import ChatOpenAI

#imporing necessary packages packages from langchain
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_community.callbacks.manager import get_openai_callback
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
import PyPDF2


# Load environment variables from the .env file
load_dotenv() 

# Access the environment variables just like you would with os.environ
KEY = os.getenv("OPENAI_KEY")


llm=ChatOpenAI(openai_api_key=KEY, model="gpt-4o", temperature=0.5, max_tokens=2000, request_timeout=120)

template="""
Text:{text}
You are an expert MCQ maker. Given the above text, it is your job to \
create a quiz  of {number} multiple choice questions for {subject} students in {tone} tone. 
Make sure the questions are not repeated and check all the questions to be conforming the text as well.
Make sure to format your response like  RESPONSE_JSON below  and use it as a guide. \
Ensure to make {number} MCQs
### RESPONSE_JSON
{response_json}

"""

quiz_generation_prompt = PromptTemplate(
    input_variables=[
        "text",
        "number",
        "subject",
        "tone",
        "response_json"
    ],
    template=template
)



quiz_chain = quiz_generation_prompt | llm | StrOutputParser()

template="""
You are an expert english grammarian and writer. Given a Multiple Choice Quiz for {subject} students.\
You need to evaluate the complexity of teh question and give a complete analysis of the quiz if the students
will be able to unserstand the questions and answer them. Only use at max 50 words for complexity analysis. 
if the quiz is not at par with the cognitive and analytical abilities of the students,\
update tech quiz questions which needs to be changed  and change the tone such that it perfectly fits the student abilities
Quiz_MCQs:
{quiz}

Check from an expert English Writer of the above quiz:
"""

quiz_evaluation_prompt=PromptTemplate(input_variables=["subject", "quiz"], template=template)

review_chain=quiz_evaluation_prompt | llm | StrOutputParser()


# This is an Overall Chain where we run the two chains in Sequence
generate_evaluate_chain = (
    RunnablePassthrough.assign(quiz=quiz_chain)
    | RunnablePassthrough.assign(review=review_chain)
)