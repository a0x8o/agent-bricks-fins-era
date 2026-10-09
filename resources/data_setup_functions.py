"""
Helper functions for setting up Databricks Unity Catalog resources and file operations.
"""
import os
import logging
import requests
import pandas as pd
import io
from databricks.sdk import WorkspaceClient
from databricks.sdk.runtime import dbutils

logger = logging.getLogger(__name__)

def create_catalog_and_schema(spark, catalog: str, schema: str):
    """Create catalog and schema if they don't exist."""
    try:
        # spark.sql(f"CREATE CATALOG IF NOT EXISTS `{catalog}`")
        spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}`")
        logger.info(f"Catalog {catalog} and schema {schema} ensured.")
    except Exception as e:
        logger.error(f"Failed to create catalog or schema: {e}")
        raise

def create_volume(spark, catalog: str, schema: str, volume_name: str):
    """Create Unity Catalog volume if it doesn't exist."""
    try:
        spark.sql(f"""
            CREATE VOLUME IF NOT EXISTS `{catalog}`.`{schema}`.`{volume_name}`
        """)
        logger.info(f"Volume {catalog}.{schema}.{volume_name} ensured.")
    except Exception as e:
        logger.error(f"Failed to create volume: {e}")
        raise

def create_table(spark, catalog: str, schema: str, table: str):
    """Create table for storing document metadata if it doesn't exist."""
    try:
        spark.sql(f"""
            CREATE TABLE IF NOT EXISTS `{catalog}`.`{schema}`.`{table}` (
                document_id STRING,
                file_name STRING,
                file_path STRING,
                upload_timestamp TIMESTAMP,
                file_size BIGINT,
                content_type STRING
            )
            USING DELTA
        """)
        logger.info(f"Table {catalog}.{schema}.{table} ensured.")
    except Exception as e:
        logger.error(f"Failed to create table: {e}")
        raise

def upload_file_to_volume(spark, local_file_path: str, catalog: str, schema: str, volume_name: str, table: str):
    """Upload file to Unity Catalog volume and log metadata to table."""
    try:
        file_name = os.path.basename(local_file_path)
        volume_path = f"/Volumes/{catalog}/{schema}/{volume_name}/{file_name}"

        # In a real Databricks environment, you would copy the file to the volume
        # For now, we'll simulate the upload and log the metadata
        logger.info(f"Uploading {local_file_path} to {volume_path}")

        # Get file stats
        file_stats = os.stat(local_file_path)
        file_size = file_stats.st_size

        # Create metadata record
        metadata_df = spark.createDataFrame([
            (file_name.replace('.pdf', ''), file_name, volume_path,
             spark.sql("SELECT current_timestamp()").collect()[0][0],
             file_size, "application/pdf")
        ], ["document_id", "file_name", "file_path", "upload_timestamp", "file_size", "content_type"])

        # Insert metadata into table
        full_table = f"`{catalog}`.`{schema}`.`{table}`"
        metadata_df.write.mode("append").saveAsTable(full_table)

        logger.info(f"Successfully uploaded {file_name} and logged metadata to {full_table}")

    except Exception as e:
        logger.error(f"Error uploading file {local_file_path}: {e}")
        raise

    try:
        w = WorkspaceClient()
 
        local_root = local_file_path
        volume_root = f"/Volumes/{catalog}/{schema}/{volume_name}"

        for root, _, files in os.walk(local_root):
            for filename in files:
                local_file = os.path.join(root, filename)

                # Path relative to the data/ folder
                relative_path = os.path.relpath(local_file, local_root)

                # Mirror structure in the volume
                target_path = f"{volume_root}/{relative_path}"

                with open(local_file, "rb") as f:
                    w.files.upload(
                        target_path,
                        io.BytesIO(f.read()),
                        overwrite=True
                    )

                print(f"Uploaded {relative_path}")
    except Exception:
        logger.exception("Error uploading to Databricks volume")
        print("upload to volume failed")
        raise

def create_tables_from_volume_subfolders(spark, catalog, schema, volume_name, logger):
    """Create tables for each subfolder in the volume.
    
    Args:
        spark: SparkSession
        catalog: Catalog name
        schema: Schema name
        volume_name: Volume name
        logger: Logger instance
    """
    logger.info("Creating tables for volume subfolders...")
    
    volume_path = f"/Volumes/{catalog}/{schema}/{volume_name}"
    subfolders = dbutils.fs.ls(volume_path)
    
    for item in subfolders:
        if item.isDir():
            # Clean up folder name: remove trailing slash and any whitespace
            subfolder_name = item.name.rstrip('/').strip()
            
            # Debug: log the actual folder name
            logger.info(f"Raw folder name: '{item.name}' -> Clean: '{subfolder_name}'")
            
            # Don't append '_data' if the subfolder name already ends with '_data'
            if subfolder_name.endswith('_data'):
                table_name = subfolder_name
                logger.info(f"  Folder already ends with '_data', using as-is: {table_name}")
            else:
                table_name = f"{subfolder_name}_data"
                logger.info(f"  Appending '_data' suffix: {table_name}")
            
            subfolder_path = item.path
            
            logger.info(f"Processing subfolder: {subfolder_name} -> Table: {table_name}")
            
            # Check if subfolder contains CSV files
            files = dbutils.fs.ls(subfolder_path)
            csv_files = [f for f in files if f.name.endswith('.csv')]
            
            if csv_files:
                # Load CSV files from volume into table
                logger.info(f"  Found {len(csv_files)} CSV file(s), creating table {table_name}")
                csv_path = f"{subfolder_path}*.csv"
                df = spark.read.format("csv").option("header", "true").option("inferSchema", "true").load(csv_path)
                full_table_name = f"`{catalog}`.`{schema}`.`{table_name}`"
                df.write.mode("overwrite").saveAsTable(full_table_name)
                logger.info(f"  ✓ Created table {full_table_name} with {df.count()} rows")
            else:
                # For PDF/document folders, create a table with file metadata using read_files
                logger.info(f"  Found document files, creating metadata table {table_name}")
                doc_path = f"{subfolder_path}*"

                # Create table with file metadata
                df = spark.sql(f"""
                    SELECT
                        _metadata.file_path as file_path,
                        _metadata.file_name as file_name,
                        _metadata.file_size as file_size,
                        _metadata.file_modification_time as file_modification_time,
                        '{subfolder_name}' as document_category
                    FROM read_files('{doc_path}')
                """)

                full_table_name = f"`{catalog}`.`{schema}`.`{table_name}`"
                df.write.mode("overwrite").saveAsTable(full_table_name)
                logger.info(f"  ✓ Created metadata table {full_table_name} with {df.count()} files")
    
    logger.info("\n✅ All subfolder tables created successfully!")


def load_csv_to_table(spark, table: str, url: str, catalog: str, schema: str):
    """Download CSV, load into a Spark DataFrame, and save it as a Delta table."""
    try:
        logger.info(f"Loading CSV from {url} into table {catalog}.{schema}.{table}")
        resp = requests.get(url)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        spark_df = spark.createDataFrame(df)
        full_table = f"`{catalog}`.`{schema}`.`{table}`"
        spark_df.write.mode("overwrite").saveAsTable(full_table)
        logger.info(f"Successfully wrote table {full_table}")
    except Exception as e:
        logger.error(f"Error loading {table} from {url}: {e}")
        raise
