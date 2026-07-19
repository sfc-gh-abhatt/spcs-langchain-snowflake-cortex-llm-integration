# Generated with Cortex Code (https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code)

"""
SPCS execution: LangChain + ChatSnowflake calling Cortex inside a Snowpark Container.

In SPCS, authentication uses the injected token file and SNOWFLAKE_HOST env var.
This script tests whether langchain-snowflake correctly uses SNOWFLAKE_HOST
for the Cortex REST endpoint when tool calling is involved.

SPCS-injected environment:
  SNOWFLAKE_HOST              - pre-resolved hostname for this account
  /snowflake/session/token    - OAuth token file for auth

User-provided environment (set in service spec):
  SNOWFLAKE_DATABASE          - target database
  SNOWFLAKE_SCHEMA            - target schema
  SNOWFLAKE_WAREHOUSE         - warehouse for queries

Falls back to env-var-based session if not running in SPCS (useful for local testing).
"""

import os
import sys

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
]


def detect_spcs_environment():
    """Check if we're running inside an SPCS container."""
    token_path = "/snowflake/session/token"
    snowflake_host = os.getenv("SNOWFLAKE_HOST")
    has_token = os.path.exists(token_path)
    print(f"  SNOWFLAKE_HOST = {snowflake_host}")
    print(f"  Token file exists = {has_token}")
    return snowflake_host is not None and has_token


def create_spcs_session():
    """Create a Snowpark session using SPCS-injected credentials."""
    from snowflake.snowpark import Session

    host = os.environ["SNOWFLAKE_HOST"]
    # Derive account from host (strip .snowflakecomputing.com)
    account = host.replace(".snowflakecomputing.com", "")

    with open("/snowflake/session/token", "r") as f:
        token = f.read().strip()

    connection_params = {
        "account": account,
        "host": host,
        "authenticator": "oauth",
        "token": token,
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        "database": DATABASE,
        "schema": SCHEMA,
    }

    print(f"  Connecting with account={account}, host={host}")
    session = Session.builder.configs(connection_params).create()
    return session


def create_env_session():
    """Create session from environment variables (partner's original pattern)."""
    from langchain_snowflake import create_session_from_env
    return create_session_from_env()


def main():
    print("=" * 60)
    print("SPCS Test: LangChain + ChatSnowflake + Cortex")
    print("=" * 60)

    # Step 1: Detect environment and create session
    print("\n[1/4] Detecting environment...")
    is_spcs = detect_spcs_environment()

    if is_spcs:
        print("  Running inside SPCS container.")
        print("\n  Creating session using SNOWFLAKE_HOST + token...")
        try:
            session = create_spcs_session()
            result = session.sql("SELECT CURRENT_ACCOUNT(), CURRENT_REGION(), CURRENT_WAREHOUSE()").collect()
            print(f"  Connected: account={result[0][0]}, region={result[0][1]}, warehouse={result[0][2]}")
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        print("  NOT running in SPCS. Using env vars.")
        try:
            session = create_env_session()
            result = session.sql("SELECT CURRENT_ACCOUNT(), CURRENT_REGION(), CURRENT_WAREHOUSE()").collect()
            print(f"  Connected: account={result[0][0]}, region={result[0][1]}, warehouse={result[0][2]}")
        except Exception as e:
            print(f"  FAILED: {e}")
            sys.exit(1)

    # Step 2: Initialize ChatSnowflake
    from langchain_snowflake import ChatSnowflake, SnowflakeQueryTool
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

    print(f"\n[2/4] Initializing ChatSnowflake with model={MODEL}...")
    try:
        llm = ChatSnowflake(
            session=session,
            model=MODEL,
            temperature=0.0,
            max_tokens=1024,
        )
        test_response = llm.invoke("Say 'hello' and nothing else.")
        print(f"  Cortex inference OK: {test_response.content[:50]}")
    except Exception as e:
        print(f"  FAILED: {e}")
        print(f"  Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Step 3: Set up tool-calling LLM
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

    # Step 4: Run test questions
    print("\n[4/4] Running test questions (tool-calling path)...\n")
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

            response = llm_with_tools.invoke(messages)
            messages.append(response)

            while response.tool_calls:
                for tool_call in response.tool_calls:
                    print(f"  [Tool call] {tool_call['name']}: {tool_call['args']}")
                    tool_result = query_tool.invoke(tool_call["args"])
                    messages.append(ToolMessage(
                        content=str(tool_result),
                        tool_call_id=tool_call["id"],
                    ))
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

    print("\n\nDone. All questions processed successfully in SPCS.")


if __name__ == "__main__":
    main()
