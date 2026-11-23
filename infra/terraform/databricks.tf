# ------------------------------------------------------------------------------
# Azure Databricks Workspace & Unity Catalog Setup
# ------------------------------------------------------------------------------
resource "azurerm_databricks_workspace" "workspace" {
  name                        = "dbw-${var.project_name}-${var.environment}"
  resource_group_name         = azurerm_resource_group.rg.name
  location                    = azurerm_resource_group.rg.location
  sku                         = var.databricks_sku
  managed_resource_group_name = "rg-${var.project_name}-${var.environment}-db-managed"

  tags = {
    Project     = "HealthGuard 360"
    Environment = var.environment
    Service     = "Databricks"
  }
}

# Access Connector for Azure Databricks Unity Catalog
resource "azurerm_databricks_access_connector" "unity_catalog" {
  name                = "dbac-${var.project_name}-${var.environment}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location

  identity {
    type = "SystemAssigned"
  }
}

# Role Assignment: Storage Blob Data Contributor on Lakehouse Storage
resource "azurerm_role_assignment" "unity_storage_contributor" {
  scope                = azurerm_storage_account.lakehouse.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_databricks_access_connector.unity_catalog.identity[0].principal_id
}

# Databricks Lakehouse Compute Cluster
resource "databricks_cluster" "lakehouse_compute" {
  cluster_name            = "hg360-${var.environment}-lakehouse-cluster"
  spark_version           = var.spark_version
  node_type_id            = var.node_type_id
  autotermination_minutes = 20

  autoscale {
    min_workers = var.autoscale_min_workers
    max_workers = var.autoscale_max_workers
  }

  spark_conf = {
    "spark.databricks.delta.preview.enabled"                  = "true"
    "spark.sql.streaming.forceDeleteTempCheckpointLocation" = "true"
    "spark.hadoop.fs.azure.account.auth.type"                = "OAuth"
    "spark.sql.shuffle.partitions"                           = "auto"
  }

  custom_tags = {
    Workload    = "HealthGuard-Lakehouse"
    Environment = var.environment
  }
}

# Unity Catalog Schema for Medallion Tiers
resource "databricks_catalog" "healthguard_catalog" {
  name    = "healthguard_360"
  comment = "Enterprise clinical lakehouse catalog governed by Unity Catalog"
}

resource "databricks_schema" "gold_marts" {
  catalog_name = databricks_catalog.healthguard_catalog.name
  name         = "gold_clinical_marts"
  comment      = "Curated, high-performance Star Schema marts for reporting & AI copilot"
}
