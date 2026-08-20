terraform {
    backend "azurerm" {
    resource_group_name  = "rg-portfolio"
    storage_account_name = "tfstatecloudportfolio"
    container_name       = "tfstate"
    key                  = "portfolio-backend.tfstate"
    use_azuread_auth     = true
  }
  
  required_version = ">= 1.3.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
}

data "azurerm_resource_group" "rg" {
  name = "rg-portfolio"
}

resource "azurerm_storage_account" "fn_storage" {
  name                     = "portfoliostoragefn"
  resource_group_name      = data.azurerm_resource_group.rg.name
  location                 = data.azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
}

resource "azurerm_service_plan" "fn_plan" {
  name                = "portfolio-consumption-plan"
  resource_group_name = data.azurerm_resource_group.rg.name
  location            = data.azurerm_resource_group.rg.location
  os_type             = "Linux"
  sku_name            = "Y1"
}

resource "azurerm_cosmosdb_account" "db" {
  name                = "cloudportfoliodb"
  resource_group_name = data.azurerm_resource_group.rg.name
  location            = "indonesiacentral"
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  capabilities {
    name = "EnableTable"
  }

  capabilities {
    name = "EnableServerless"
  }

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = "indonesiacentral"
    failover_priority = 0
  }
}

resource "azurerm_cosmosdb_table" "table" {
  name                = "VisitorCounter"
  resource_group_name = data.azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.db.name
}

resource "azurerm_linux_function_app" "fn" {
  name                       = "portfolio-api-counter"
  resource_group_name        = data.azurerm_resource_group.rg.name
  location                   = data.azurerm_resource_group.rg.location
  storage_account_name       = azurerm_storage_account.fn_storage.name
  storage_account_access_key = azurerm_storage_account.fn_storage.primary_access_key
  service_plan_id            = azurerm_service_plan.fn_plan.id

  app_settings = {
    "FUNCTIONS_WORKER_RUNTIME" = "python"
    "COSMOS_TABLE_ENDPOINT"    = "https://${azurerm_cosmosdb_account.db.name}.table.cosmos.azure.com:443/"
  }

  site_config {
    application_stack {
      python_version = "3.11"
    }
    cors {
      allowed_origins = [
        "https://cloudeadubal.online",
        "https://www.cloudeadubal.online"
      ]
    }
    minimum_tls_version = "1.2"
  }

  identity {
    type = "SystemAssigned"
  }
}

output "function_principal_id" {
  value = azurerm_linux_function_app.fn.identity[0].principal_id
}