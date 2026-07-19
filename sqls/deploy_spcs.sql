-- Generated with Cortex Code (https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code)
--
-- SPCS Infrastructure Setup for LangChain + Snowflake Cortex LLM Integration
-- Run these commands in order to deploy the containerized app.
-- Replace placeholder values (<YOUR_...>) with your actual Snowflake object names.
--
-- Prerequisites:
--   Run sqls/ddl_and_data.sql first to create the schema and load sample data.
--   The SNOWFLAKE_DATABASE and SNOWFLAKE_SCHEMA env vars in the service spec
--   must match the database/schema created by ddl_and_data.sql.

-- 1. Create image repository
CREATE IMAGE REPOSITORY IF NOT EXISTS <YOUR_DATABASE>.<YOUR_SCHEMA>.SPCS_IMAGE_REGISTRY;

-- 2. Get the repository URL (needed for docker push)
SHOW IMAGE REPOSITORIES IN SCHEMA <YOUR_DATABASE>.<YOUR_SCHEMA>;
-- Note the repository_url column — use it for docker login and push
-- Example: docker login <your-org-account>.registry.snowflakecomputing.com -u <your_user>

-- 3. Create compute pool (system pools are restricted to specific service types)
CREATE COMPUTE POOL IF NOT EXISTS LANGCHAIN_CORTEX_POOL
  MIN_NODES = 1
  MAX_NODES = 1
  INSTANCE_FAMILY = CPU_X64_XS
  AUTO_SUSPEND_SECS = 300;

-- Check pool state (must be ACTIVE or IDLE before service will start)
DESCRIBE COMPUTE POOL LANGCHAIN_CORTEX_POOL;

-- 4. Create the SPCS service (run AFTER pushing the Docker image)
-- Build and push with: docker build --platform linux/amd64 -t <repo_url>/langchain-cortex-demo:latest .
--                       docker push <repo_url>/langchain-cortex-demo:latest
CREATE SERVICE <YOUR_DATABASE>.<YOUR_SCHEMA>.LANGCHAIN_CORTEX_SVC
  IN COMPUTE POOL LANGCHAIN_CORTEX_POOL
  MIN_INSTANCES = 1
  MAX_INSTANCES = 1
  FROM SPECIFICATION $$
spec:
  containers:
    - name: langchain-cortex-container
      image: /<your_database>/<your_schema>/spcs_image_registry/langchain-cortex-demo:latest
      env:
        SNOWFLAKE_DATABASE: <YOUR_DATABASE>
        SNOWFLAKE_SCHEMA: <YOUR_SCHEMA>
        SNOWFLAKE_WAREHOUSE: <YOUR_WAREHOUSE>
      resources:
        requests:
          cpu: 1
          memory: 2Gi
        limits:
          cpu: 2
          memory: 4Gi
$$;

-- 5. Check service status
CALL SYSTEM$GET_SERVICE_STATUS('<YOUR_DATABASE>.<YOUR_SCHEMA>.LANGCHAIN_CORTEX_SVC');

-- 6. View container logs
CALL SYSTEM$GET_SERVICE_LOGS('<YOUR_DATABASE>.<YOUR_SCHEMA>.LANGCHAIN_CORTEX_SVC', '0', 'langchain-cortex-container', 500);

-- 7. Cleanup when done
-- DROP SERVICE IF EXISTS <YOUR_DATABASE>.<YOUR_SCHEMA>.LANGCHAIN_CORTEX_SVC;
-- DROP COMPUTE POOL IF EXISTS LANGCHAIN_CORTEX_POOL;
