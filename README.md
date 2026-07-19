# LangChain + Snowflake Cortex LLM Integration on SPCS

End-to-end demo of running a LangChain-powered SQL agent on Snowflake, using `langchain-snowflake` with `ChatSnowflake` for Cortex LLM inference — both locally and inside Snowpark Container Services (SPCS).

## What This Demonstrates

- **ChatSnowflake** calling Snowflake Cortex for LLM inference (claude-4-sonnet)
- **SnowflakeQueryTool** for natural-language-to-SQL via tool calling
- **SPCS deployment** with automatic authentication via `SNOWFLAKE_HOST` and injected OAuth token
- **Local execution** using environment-variable-based authentication

## Repository Structure

```
.
├── code/
│   ├── langchain-snowflake-cortex-llm-local.py   # Local execution script
│   ├── langchain-snowflake-cortex-llm-spcs.py    # SPCS container script
│   ├── requirements.txt                           # Python deps (local)
│   ├── requirements_spcs.txt                      # Python deps (container)
│   ├── Dockerfile                                 # Container image definition
│   └── service_spec.yaml                          # SPCS service specification (reference)
├── sqls/
│   ├── ddl_and_data.sql                           # Creates schema + loads sample data
│   └── deploy_spcs.sql                            # SPCS infrastructure + service creation
└── README.md
```

## Prerequisites

- A Snowflake account with Cortex enabled
- Python 3.11+
- Docker (for SPCS deployment)
- Snowflake user with permissions to create schemas, image repositories, compute pools, and services

## Part 1: Data Setup

Run `sqls/ddl_and_data.sql` in Snowsight or SnowSQL. Edit the variables at the top of the file first:

```sql
SET MY_DATABASE = 'DEMO_DB';       -- your database
SET MY_SCHEMA   = 'CLINICAL';      -- schema name to create
SET MY_WH       = 'COMPUTE_WH';   -- your warehouse
```

Then execute the full script. It creates 5 tables (patients, providers, visits, diagnoses, medications) and loads sample clinical data (~3,400 rows total).

## Part 2: Local Execution

### 2.1 Install dependencies

```bash
cd code
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2.2 Set environment variables

```bash
export SNOWFLAKE_ACCOUNT="myorg-myaccount"    # org-account format with HYPHENS (not underscores)
export SNOWFLAKE_USER="your_username"
export SNOWFLAKE_PASSWORD="your_password"
export SNOWFLAKE_WAREHOUSE="COMPUTE_WH"
export SNOWFLAKE_DATABASE="DEMO_DB"           # must match ddl_and_data.sql
export SNOWFLAKE_SCHEMA="CLINICAL"            # must match ddl_and_data.sql
```

**Important: Account identifier format**

Use the org-account format with hyphens. If your account name contains underscores (e.g., `myorg-my_account`), replace underscores with hyphens in the value you export (e.g., `myorg-my-account`). Underscores cause SSL certificate mismatches when `langchain-snowflake` constructs the Cortex REST endpoint URL.

To find your org-account identifier:
```sql
SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME();
```

### 2.3 Run

```bash
python langchain-snowflake-cortex-llm-local.py
```

Expected output:
```
============================================================
LangChain + ChatSnowflake + Cortex — SQL Agent Demo
============================================================

[1/4] Creating Snowflake session...
  Connected: account=..., region=..., warehouse=...

[2/4] Initializing ChatSnowflake with model=claude-4-sonnet...
  Cortex inference OK: hello

[3/4] Setting up tool-calling LLM with SnowflakeQueryTool...
  Tools bound to LLM.

[4/4] Running test questions...
  [Tool call] snowflake_query: {'query': 'SELECT ...'}
A1: ...

Done. All questions processed.
```

## Part 3: SPCS Deployment

### 3.1 Create image repository

Run in Snowsight:
```sql
CREATE IMAGE REPOSITORY IF NOT EXISTS DEMO_DB.CLINICAL.SPCS_IMAGE_REGISTRY;
SHOW IMAGE REPOSITORIES IN SCHEMA DEMO_DB.CLINICAL;
```

Copy the `repository_url` value from the result. It will look like:
```
myorg-myaccount.registry.snowflakecomputing.com/demo_db/clinical/spcs_image_registry
```

### 3.2 Build and push the Docker image

```bash
cd code

# Login to the Snowflake container registry
docker login myorg-myaccount.registry.snowflakecomputing.com -u your_username

# Build for linux/amd64 (required — SPCS does not support ARM images)
docker build --platform linux/amd64 \
  -t myorg-myaccount.registry.snowflakecomputing.com/demo_db/clinical/spcs_image_registry/langchain-cortex-demo:latest .

# Push
docker push myorg-myaccount.registry.snowflakecomputing.com/demo_db/clinical/spcs_image_registry/langchain-cortex-demo:latest
```

### 3.3 Create compute pool

```sql
CREATE COMPUTE POOL IF NOT EXISTS LANGCHAIN_CORTEX_POOL
  MIN_NODES = 1
  MAX_NODES = 1
  INSTANCE_FAMILY = CPU_X64_XS
  AUTO_SUSPEND_SECS = 300;

-- Wait until state is ACTIVE or IDLE
DESCRIBE COMPUTE POOL LANGCHAIN_CORTEX_POOL;
```

### 3.4 Create the service

Replace `<values>` with your actual database, schema, and warehouse:

```sql
CREATE SERVICE DEMO_DB.CLINICAL.LANGCHAIN_CORTEX_SVC
  IN COMPUTE POOL LANGCHAIN_CORTEX_POOL
  MIN_INSTANCES = 1
  MAX_INSTANCES = 1
  FROM SPECIFICATION $$
spec:
  containers:
    - name: langchain-cortex-container
      image: /demo_db/clinical/spcs_image_registry/langchain-cortex-demo:latest
      env:
        SNOWFLAKE_DATABASE: DEMO_DB
        SNOWFLAKE_SCHEMA: CLINICAL
        SNOWFLAKE_WAREHOUSE: COMPUTE_WH
      resources:
        requests:
          cpu: 1
          memory: 2Gi
        limits:
          cpu: 2
          memory: 4Gi
$$;
```

### 3.5 Check status and view logs

```sql
-- Check service status (wait for DONE or FAILED)
CALL SYSTEM$GET_SERVICE_STATUS('DEMO_DB.CLINICAL.LANGCHAIN_CORTEX_SVC');

-- View container output
SELECT SYSTEM$GET_SERVICE_LOGS('DEMO_DB.CLINICAL.LANGCHAIN_CORTEX_SVC', 0, 'langchain-cortex-container');
```

The container runs the script and exits. Logs show the full output including connection details and query results.

### 3.6 Cleanup

```sql
DROP SERVICE IF EXISTS DEMO_DB.CLINICAL.LANGCHAIN_CORTEX_SVC;
DROP COMPUTE POOL IF EXISTS LANGCHAIN_CORTEX_POOL;
```

## How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Snowflake Account                                              │
│                                                                 │
│  ┌───────────────────────┐     ┌─────────────────────────────┐ │
│  │  SPCS Container       │     │  Snowflake Cortex           │ │
│  │                       │     │                             │ │
│  │  langchain-snowflake  │────>│  /api/v2/cortex/inference   │ │
│  │  + ChatSnowflake      │     │  (claude-4-sonnet)          │ │
│  │  + SnowflakeQueryTool │     │                             │ │
│  │                       │     └─────────────────────────────┘ │
│  │  SNOWFLAKE_HOST ──────│─── injected by SPCS runtime        │
│  │  /snowflake/session/  │                                     │
│  │    token              │     ┌─────────────────────────────┐ │
│  │                       │────>│  Snowflake Tables            │ │
│  └───────────────────────┘     │  (SQL queries via tool)      │ │
│                                └─────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Authentication in SPCS

Inside an SPCS container, Snowflake injects:
- `SNOWFLAKE_HOST` environment variable — the pre-resolved hostname for the account
- `/snowflake/session/token` file — an OAuth token for authentication

The SPCS script reads these automatically. No passwords or account identifiers need to be hardcoded.

### Known Issues with langchain-snowflake

**Account identifier and URL construction (v0.2.3):**

The library constructs the Cortex REST API endpoint URL from the account identifier. Two pitfalls:

1. **Underscores in org-account names** — If your account identifier contains underscores (e.g., `myorg-my_account`), the library uses it as-is to construct `myorg-my_account.snowflakecomputing.com`, which fails SSL certificate validation. Workaround: use hyphens in the exported `SNOWFLAKE_ACCOUNT` value.

2. **Short locators without region suffix** — If your account is not in the default region (`us-east-1` for AWS), a bare locator like `AB12345` won't resolve. Use `AB12345.us-east-2` or the org-account format instead.

**These issues do not affect SPCS deployment** because SPCS injects the correct `SNOWFLAKE_HOST` value (using the locator+region format), bypassing the URL construction logic.

## Cross-Region Inference

If the model you want (e.g., `claude-4-sonnet`) is not natively deployed in your account's region, enable cross-region inference:

```sql
ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'AWS_US';
```

This allows Snowflake to route inference requests to another region where the model is available.
