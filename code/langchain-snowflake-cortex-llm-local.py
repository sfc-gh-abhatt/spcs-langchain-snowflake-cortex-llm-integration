# Generated with Cortex Code (https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code)

"""
Local execution: LangChain + ChatSnowflake calling Cortex for
conversational analytics over Snowflake data.

Demonstrates:
- langchain-snowflake with ChatSnowflake
- Cortex LLM inference (tool-calling path)
- SQL agent over Snowflake tables via SnowflakeQueryTool

Environment variables required:
  SNOWFLAKE_ACCOUNT   - account identifier (org-account format recommended, e.g. "myorg-myaccount")
  SNOWFLAKE_USER      - username
  SNOWFLAKE_PASSWORD  - password (or use SNOWFLAKE_PAT for PAT auth)
  SNOWFLAKE_WAREHOUSE - warehouse name
  SNOWFLAKE_DATABASE  - target database
  SNOWFLAKE_SCHEMA    - target schema

IMPORTANT: For the account identifier, use the org-account format with hyphens
(not underscores). Underscores in account names cause SSL certificate mismatches
when the library constructs the Cortex REST endpoint URL.
"""

import os
import sys

from langchain_snowflake import ChatSnowflake, create_session_from_env, SnowflakeQueryTool
from langchain_core.messages import HumanMessage, SystemMessage

# -- Configuration --
MODEL = "claude-4-sonnet"
DATABASE = os.getenv("SNOWFLAKE_DATABASE")
SCHEMA = os.getenv("SNOWFLAKE_SCHEMA")

if not DATABASE or not SCHEMA:
    print("ERROR: SNOWFLAKE_DATABASE and SNOWFLAKE_SCHEMA environment variables are required.")
    sys.exit(1)

SCHEMA_DESCRIPTION = """
You have access to a database with tables in {database}.{schema}.
You can query these tables using Snowflake SQL syntax.
Always use fully qualified table names: {database}.{schema}.<table>
Return concise, relevant results.
"""

TEST_QUESTIONS = [
    "What tables are available and how many rows does each have?",
    "Show me the first 5 rows of the largest table.",
    "What are the column names and types in each table?",
]


def main():
    print("=" * 60)
    print("LangChain + ChatSnowflake + Cortex — SQL Agent Demo")
    print("=" * 60)

    # Step 1: Create Snowflake session
    print("\n[1/4] Creating Snowflake session...")
    try:
        session = create_session_from_env()
        result = session.sql("SELECT CURRENT_ACCOUNT(), CURRENT_REGION(), CURRENT_WAREHOUSE()").collect()
        print(f"  Connected: account={result[0][0]}, region={result[0][1]}, warehouse={result[0][2]}")
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    # Step 2: Initialize ChatSnowflake with Cortex model
    print(f"\n[2/4] Initializing ChatSnowflake with model={MODEL}...")
    try:
        llm = ChatSnowflake(
            session=session,
            model=MODEL,
            temperature=0.0,
            max_tokens=1024,
        )
        # Quick smoke test — direct inference call
        test_response = llm.invoke("Say 'hello' and nothing else.")
        print(f"  Cortex inference OK: {test_response.content[:50]}")
    except Exception as e:
        print(f"  FAILED: {e}")
        print(f"  Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Step 3: Set up tool-calling LLM with SnowflakeQueryTool
    print("\n[3/4] Setting up tool-calling LLM with SnowflakeQueryTool...")
    try:
        query_tool = SnowflakeQueryTool(session=session, schema=f"{DATABASE}.{SCHEMA}")
        llm_with_tools = llm.bind_tools([query_tool])
        print("  Tools bound to LLM.")
    except Exception as e:
        print(f"  FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Step 4: Run test questions using tool-calling loop
    print("\n[4/4] Running test questions...\n")
    print("-" * 60)

    system_prompt = SCHEMA_DESCRIPTION.format(database=DATABASE, schema=SCHEMA)

    for i, question in enumerate(TEST_QUESTIONS, 1):
        print(f"\nQ{i}: {question}")
        print("-" * 40)
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=question),
            ]

            # First LLM call — may produce tool calls
            response = llm_with_tools.invoke(messages)
            messages.append(response)

            # If the LLM requested tool calls, execute them and feed back
            while response.tool_calls:
                for tool_call in response.tool_calls:
                    print(f"  [Tool call] {tool_call['name']}: {tool_call['args']}")
                    tool_result = query_tool.invoke(tool_call["args"])
                    from langchain_core.messages import ToolMessage
                    messages.append(ToolMessage(
                        content=str(tool_result),
                        tool_call_id=tool_call["id"],
                    ))
                # Follow-up LLM call with tool results
                response = llm_with_tools.invoke(messages)
                messages.append(response)

            print(f"A{i}: {response.content}")
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            print("\nStopping on first failure.")
            sys.exit(1)
        print("-" * 60)

    print("\n\nDone. All questions processed.")


if __name__ == "__main__":
    main()
