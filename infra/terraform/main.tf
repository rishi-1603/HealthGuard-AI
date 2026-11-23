terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.90.0"
    }
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.35.0"
    }
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
  }
}

data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "rg" {
  name     = "rg-${var.project_name}-${var.environment}"
  location = var.azure_region

  tags = {
    Project     = "HealthGuard 360"
    Environment = var.environment
    ManagedBy   = "Terraform"
    Compliance  = "HIPAA-Ready"
  }
}

# ------------------------------------------------------------------------------
# Azure Data Lake Storage Gen2 (ADLS Gen2) Lakehouse Core
# ------------------------------------------------------------------------------
resource "azurerm_storage_account" "lakehouse" {
  name                     = "st${var.project_name}${var.environment}"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = var.adls_storage_replication
  account_kind             = "StorageV2"
  is_hns_enabled           = true # Critical: Enables Azure ADLS Gen2 Hierarchical Namespace

  enable_https_traffic_only = true
  min_tls_version           = "TLS1_2"
  allow_nested_items_to_be_public = false

  network_rules {
    default_action = "Deny"
    bypass         = ["AzureServices", "Logging", "Metrics"]
  }

  tags = {
    Tier        = "DataLake"
    StorageType = "ADLSGen2"
    Environment = var.environment
  }
}

# Medallion Architecture Containers
resource "azurerm_storage_data_lake_gen2_filesystem" "bronze" {
  name               = "bronze"
  storage_account_id = azurerm_storage_account.lakehouse.id
}

resource "azurerm_storage_data_lake_gen2_filesystem" "silver" {
  name               = "silver"
  storage_account_id = azurerm_storage_account.lakehouse.id
}

resource "azurerm_storage_data_lake_gen2_filesystem" "gold" {
  name               = "gold"
  storage_account_id = azurerm_storage_account.lakehouse.id
}

resource "azurerm_storage_data_lake_gen2_filesystem" "quarantine" {
  name               = "quarantine"
  storage_account_id = azurerm_storage_account.lakehouse.id
}

resource "azurerm_storage_data_lake_gen2_filesystem" "checkpoints" {
  name               = "checkpoints"
  storage_account_id = azurerm_storage_account.lakehouse.id
}
