output "resource_group_name" {
  description = "Name of deployed resource group"
  value       = azurerm_resource_group.rg.name
}

output "lakehouse_storage_account_name" {
  description = "ADLS Gen2 Storage Account name"
  value       = azurerm_storage_account.lakehouse.name
}

output "lakehouse_primary_dfs_endpoint" {
  description = "ADLS Gen2 primary DFS endpoint"
  value       = azurerm_storage_account.lakehouse.primary_dfs_endpoint
}

output "databricks_workspace_url" {
  description = "Azure Databricks Workspace URL"
  value       = azurerm_databricks_workspace.workspace.workspace_url
}

output "databricks_cluster_id" {
  description = "Lakehouse cluster ID for job orchestrations"
  value       = databricks_cluster.lakehouse_compute.id
}

output "medallion_containers" {
  description = "Active Medallion tier storage containers"
  value = [
    azurerm_storage_data_lake_gen2_filesystem.bronze.name,
    azurerm_storage_data_lake_gen2_filesystem.silver.name,
    azurerm_storage_data_lake_gen2_filesystem.gold.name,
    azurerm_storage_data_lake_gen2_filesystem.quarantine.name,
    azurerm_storage_data_lake_gen2_filesystem.checkpoints.name,
  ]
}
