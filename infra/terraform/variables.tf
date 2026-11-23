variable "project_name" {
  description = "The prefix used for all HealthGuard 360 resources."
  type        = string
  default     = "healthguard360"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
  default     = "prod"
}

variable "azure_region" {
  description = "Azure primary region for resource deployment."
  type        = string
  default     = "eastus2"
}

variable "adls_storage_replication" {
  description = "Storage replication type for ADLS Gen2 Lakehouse (LRS, GRS, ZRS)."
  type        = string
  default     = "GRS"
}

variable "databricks_sku" {
  description = "Databricks workspace SKU tier."
  type        = string
  default     = "premium"
}

variable "spark_version" {
  description = "Databricks Runtime Spark version for healthcare pipelines."
  type        = string
  default     = "14.3.x-scala2.12"
}

variable "node_type_id" {
  description = "Virtual machine SKU for worker nodes."
  type        = string
  default     = "Standard_D8s_v5"
}

variable "autoscale_min_workers" {
  description = "Minimum workers for autoscale lakehouse cluster."
  type        = number
  default     = 2
}

variable "autoscale_max_workers" {
  description = "Maximum workers for autoscale lakehouse cluster."
  type        = number
  default     = 8
}
