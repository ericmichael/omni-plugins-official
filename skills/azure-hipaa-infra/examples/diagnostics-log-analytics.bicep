targetScope = 'resourceGroup'

param siteName string
param keyVaultName string
param postgresName string
param storageAccountName string
param logAnalyticsWorkspaceId string
param archiveStorageAccountId string = ''

resource site 'Microsoft.Web/sites@2023-12-01' existing = {
  name: siteName
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' existing = {
  name: postgresName
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = {
  parent: storage
  name: 'default'
}

resource siteDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-logs'
  scope: site
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    storageAccountId: empty(archiveStorageAccountId) ? null : archiveStorageAccountId
    logs: [{ categoryGroup: 'allLogs', enabled: true }]
    metrics: [{ category: 'AllMetrics', enabled: true }]
  }
}

resource keyVaultDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-logs'
  scope: keyVault
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    storageAccountId: empty(archiveStorageAccountId) ? null : archiveStorageAccountId
    logs: [{ categoryGroup: 'allLogs', enabled: true }]
    metrics: [{ category: 'AllMetrics', enabled: true }]
  }
}

resource postgresDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-logs'
  scope: postgres
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    storageAccountId: empty(archiveStorageAccountId) ? null : archiveStorageAccountId
    logs: [{ categoryGroup: 'allLogs', enabled: true }]
    metrics: [{ category: 'AllMetrics', enabled: true }]
  }
}

resource blobDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-logs'
  scope: blobService
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    storageAccountId: empty(archiveStorageAccountId) ? null : archiveStorageAccountId
    logs: [
      { category: 'StorageRead', enabled: true }
      { category: 'StorageWrite', enabled: true }
      { category: 'StorageDelete', enabled: true }
    ]
    metrics: [{ category: 'Transaction', enabled: true }]
  }
}
