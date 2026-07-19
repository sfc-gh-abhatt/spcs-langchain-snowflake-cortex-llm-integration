# Generated with Cortex Code (https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code)

FROM python:3.11-slim

WORKDIR /app

COPY requirements_spcs.txt .
RUN pip install --no-cache-dir -r requirements_spcs.txt

COPY langchain-snowflake-cortex-llm-spcs.py .

CMD ["python", "langchain-snowflake-cortex-llm-spcs.py"]
